"""Program discovery providers."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Awaitable, Callable, Protocol
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from rapidfuzz import fuzz

from app.models import CollegeProgram, ProgramFees, ProgramSource, SemesterPlan, normalize_slug

from .models import AgentRun, ProgramCandidate, SearchPlan
from .search_backends import WebSearchResult, get_search_backend
from .sources import StaticProgramRepository

SEARCH_TIMEOUT_SECONDS = 8.0
MAX_LIVE_RESULTS = 12
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)

STATE_CENTERS: dict[str, tuple[str, float, float]] = {
    "AL": ("Alabama", 32.8067, -86.7911),
    "AZ": ("Arizona", 33.7298, -111.4312),
    "CA": ("California", 36.7783, -119.4179),
    "FL": ("Florida", 27.6648, -81.5158),
    "GA": ("Georgia", 32.1656, -82.9001),
    "IL": ("Illinois", 40.6331, -89.3985),
    "MA": ("Massachusetts", 42.4072, -71.3824),
    "MD": ("Maryland", 39.0458, -76.6413),
    "MI": ("Michigan", 44.3148, -85.6024),
    "NY": ("New York", 43.2994, -74.2179),
    "TX": ("Texas", 31.9686, -99.9018),
    "WA": ("Washington", 47.7511, -120.7401),
}


class ProgramDiscoveryProvider(Protocol):
    name: str

    async def discover(self, plan: SearchPlan) -> tuple[list[ProgramCandidate], AgentRun]:
        """Return matching program candidates and an agent status record."""


class OfficialWebDiscoveryProvider:
    """Discover official college program pages from public web search results."""

    name = "official_web"

    async def discover(self, plan: SearchPlan) -> tuple[list[ProgramCandidate], AgentRun]:
        queries = _search_queries(plan)
        backend = get_search_backend()
        try:
            if backend is not None:
                results = await _collect_results(backend.search, queries, plan)
                source = backend.name
            else:
                async with httpx.AsyncClient(
                    timeout=SEARCH_TIMEOUT_SECONDS,
                    follow_redirects=True,
                    headers={"User-Agent": _BROWSER_UA},
                ) as client:
                    async def run_ddg(query: str) -> list[WebSearchResult]:
                        return await _search_duckduckgo(client, query)

                    results = await _collect_results(run_ddg, queries, plan)
                source = "duckduckgo"
        except Exception as exc:  # noqa: BLE001
            return [], AgentRun(
                agent=self.name,
                status="error",
                message=f"Live official-page discovery failed ({source_name(backend)}): {exc}",
                count=0,
            )

        candidates = [_candidate_from_result(result, plan, index) for index, result in enumerate(results)]
        status = "success" if candidates else "empty"
        return candidates, AgentRun(
            agent=self.name,
            status=status,
            message=(
                f"Discovered official .edu program pages via {source}."
                if candidates else
                f"No official .edu program pages matched the course query via {source}."
            ),
            count=len(candidates),
        )


def source_name(backend) -> str:
    return backend.name if backend is not None else "duckduckgo"


async def _collect_results(
    search_fn: Callable[[str], Awaitable[list[WebSearchResult]]],
    queries: list[str],
    plan: SearchPlan,
) -> list[WebSearchResult]:
    """Run each query through a backend, keep official .edu results, dedupe, and cap."""
    results: list[WebSearchResult] = []
    seen_urls: set[str] = set()
    for query in queries:
        page_results = await search_fn(query)
        for result in page_results:
            if result.url in seen_urls or not _is_official_program_result(result, plan):
                continue
            seen_urls.add(result.url)
            results.append(result)
            if len(results) >= MAX_LIVE_RESULTS:
                return results
    return results


class StaticFallbackDiscoveryProvider:
    name = "static_fallback"

    def __init__(self, repository: StaticProgramRepository) -> None:
        self.repository = repository

    async def discover(self, plan: SearchPlan) -> tuple[list[ProgramCandidate], AgentRun]:
        programs = _matching_programs(plan.normalized_query, self.repository.all())
        candidates = [
            ProgramCandidate(
                program=program,
                provider="static_fallback",
                confidence=0.72,
                evidence_notes=["Curated fallback record with official source links."],
            )
            for program in programs
        ]
        status = "success" if candidates else "empty"
        return candidates, AgentRun(
            agent=self.name,
            status=status,
            message="Loaded matching programs from curated fallback data.",
            count=len(candidates),
        )


def _matching_programs(query: str, programs: list) -> list:
    scored = []
    q = query.lower()
    for program in programs:
        names = [program.course_name, *program.aliases]
        score = max(fuzz.token_set_ratio(q, name.lower()) for name in names)
        if score >= 55 or any(q in name.lower() or name.lower() in q for name in names):
            scored.append((score, program))
    return [p for _, p in sorted(scored, key=lambda item: (-item[0], -item[1].ranking_score))]


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[WebSearchResult] = []
        self._in_result_link = False
        self._in_snippet = False
        self._current_url: str | None = None
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._pending_title: str | None = None
        self._pending_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        class_name = attr_map.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._in_result_link = True
            self._current_url = _clean_search_url(attr_map.get("href", ""))
            self._title_parts = []
        elif "result__snippet" in class_name:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_result_link:
            self._title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            self._in_result_link = False
            title = _collapse_ws(" ".join(self._title_parts))
            if title and self._current_url:
                self._pending_title = html.unescape(title)
                self._pending_url = self._current_url
        elif self._in_snippet and tag in {"a", "div"}:
            self._in_snippet = False
            snippet = html.unescape(_collapse_ws(" ".join(self._snippet_parts)))
            if self._pending_title and self._pending_url:
                self.results.append(WebSearchResult(self._pending_title, self._pending_url, snippet))
                self._pending_title = None
                self._pending_url = None


async def _search_duckduckgo(client: httpx.AsyncClient, query: str) -> list[WebSearchResult]:
    response = await client.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    parser = _DuckDuckGoParser()
    parser.feed(response.text)
    return parser.results


def _search_queries(plan: SearchPlan) -> list[str]:
    query = plan.normalized_query
    state_name = STATE_CENTERS.get(plan.user_state or "", ("", 0.0, 0.0))[0]
    location = " ".join(part for part in [plan.city, state_name or plan.user_state] if part)
    base_terms = [
        f'site:.edu "{query}" undergraduate program',
        f'site:.edu "{query}" degree requirements',
        f'site:.edu "{query}" curriculum admissions',
    ]
    if location:
        base_terms.insert(0, f'site:.edu "{query}" undergraduate program {location}')
    return base_terms


def _is_official_program_result(result: WebSearchResult, plan: SearchPlan) -> bool:
    parsed = urlparse(result.url)
    host = parsed.netloc.lower()
    if not host.endswith(".edu"):
        return False
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in (".pdf", ".doc", ".docx", ".ppt", ".pptx")):
        return False
    combined = f"{result.title} {result.snippet} {path}".lower()
    if fuzz.token_set_ratio(plan.normalized_query.lower(), combined) < 45:
        return False
    program_terms = ("program", "degree", "major", "department", "curriculum", "undergraduate", "admission")
    return any(term in combined for term in program_terms)


def _candidate_from_result(result: WebSearchResult, plan: SearchPlan, index: int) -> ProgramCandidate:
    state = plan.user_state or "US"
    city = plan.city or "See source"
    lat, lon = _location_point(plan)
    college_name = _college_name(result)
    url_slug = normalize_slug(urlparse(result.url).netloc + "-" + urlparse(result.url).path)
    overview = result.snippet or f"Official source page for {plan.normalized_query} at {college_name}."
    program = CollegeProgram(
        program_id=f"live-{url_slug[:80]}",
        course_name=plan.normalized_query,
        aliases=[],
        college_name=college_name,
        city=city,
        state=state[:2].upper(),
        lat=lat,
        lon=lon,
        ranking_score=max(55, 92 - index * 3),
        degree=f"{plan.normalized_query} program",
        delivery="Check source",
        overview=overview,
        curriculum_summary="Live result from an official program page. Open the source to verify current course requirements and degree maps.",
        semester_plan=[
            SemesterPlan(
                term="Official source",
                focus="Program requirements",
                courses=["Check the linked official program page for the current course sequence."],
            )
        ],
        required_papers=["Check the linked admissions page for required application materials."],
        admission_factors=["Verify direct-to-major rules, prerequisites, and deadlines on the official source."],
        fees=ProgramFees(
            in_state_tuition=None,
            out_of_state_tuition=None,
            mandatory_fees=None,
            notes="Live discovery does not estimate cost yet. Use the official source and college cost page before shortlisting.",
            source_url=result.url,
        ),
        decision_factors=[
            "Official .edu source discovered live.",
            "Review curriculum, admissions rules, and net price before deciding.",
        ],
        sources=[ProgramSource(label="Official program page", url=result.url)],
    )
    return ProgramCandidate(
        program=program,
        provider="official_web",
        confidence=max(0.55, 0.92 - index * 0.04),
        evidence_notes=[result.title, result.snippet],
    )


def _college_name(result: WebSearchResult) -> str:
    title = result.title
    separators = [" | ", " - ", " – ", " — "]
    for sep in separators:
        parts = [part.strip() for part in title.split(sep) if part.strip()]
        if len(parts) > 1:
            return parts[-1][:100]
    host = urlparse(result.url).netloc.removeprefix("www.")
    name = host.split(".edu")[0].replace("-", " ").replace(".", " ")
    return _collapse_ws(name).title()[:100]


def _location_point(plan: SearchPlan) -> tuple[float, float]:
    if plan.user_state in STATE_CENTERS:
        return STATE_CENTERS[plan.user_state][1], STATE_CENTERS[plan.user_state][2]
    return 39.8283, -98.5795


def _clean_search_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    decoded = html.unescape(raw_url)
    parsed = urlparse(decoded)
    if parsed.path == "/l/":
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(uddg)
    return decoded


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
