"""Pluggable web-search backends for official program discovery.

DESIGN.md §16 flags discovery as the weak link: scraping DuckDuckGo's HTML endpoint
rate-limits and blocks (HTTP 202 anomaly pages), so live results come back empty. This
module provides real search providers behind one interface, selected by SEARCH_PROVIDER:

    SEARCH_PROVIDER=duckduckgo  (default) free HTML scrape, no key — fragile
    SEARCH_PROVIDER=brave       Brave Search API           (BRAVE_API_KEY)
    SEARCH_PROVIDER=tavily      Tavily Search API          (TAVILY_API_KEY)
    SEARCH_PROVIDER=claude      Anthropic web_search tool  (ANTHROPIC_API_KEY)

Each backend turns a query string into WebSearchResult[]; discovery then applies the
same official-.edu filter regardless of which provider produced the results.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

log = structlog.get_logger()

SEARCH_TIMEOUT_SECONDS = 8.0
MAX_BACKEND_RESULTS = 12


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


class SearchBackend(Protocol):
    name: str

    async def search(self, query: str) -> list[WebSearchResult]:
        """Run one query and return raw web results (pre-filtering)."""


def get_search_backend() -> SearchBackend | None:
    """Return the configured backend, or None to use discovery's keyless DuckDuckGo path.

    Default is Tavily. Set SEARCH_PROVIDER=duckduckgo for the keyless fallback.
    """
    provider = (os.getenv("SEARCH_PROVIDER") or "tavily").strip().lower()
    if provider in ("duckduckgo", "ddg"):
        return None
    backends = {
        "brave": BraveBackend,
        "tavily": TavilyBackend,
        "apify": ApifyBackend,
        "claude": ClaudeWebSearchBackend,
    }
    cls = backends.get(provider)
    if cls is None:
        log.warning("unknown_search_provider", provider=provider)
        return None  # fall back to the keyless DuckDuckGo path
    return cls()


# ── Brave Search API ───────────────────────────────────────────────────────────

class BraveBackend:
    name = "brave"

    async def search(self, query: str) -> list[WebSearchResult]:
        key = os.getenv("BRAVE_API_KEY")
        if not key:
            raise RuntimeError("SEARCH_PROVIDER=brave but BRAVE_API_KEY is not set")
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": f"site:.edu {_normalize_query(query)}", "count": MAX_BACKEND_RESULTS},
                headers={"Accept": "application/json", "X-Subscription-Token": key},
            )
            resp.raise_for_status()
            return _parse_brave(resp.json())


def _parse_brave(data: dict) -> list[WebSearchResult]:
    results: list[WebSearchResult] = []
    for item in ((data.get("web") or {}).get("results") or []):
        url = item.get("url")
        if not url:
            continue
        results.append(WebSearchResult(
            title=_clean(item.get("title") or ""),
            url=url,
            snippet=_clean(item.get("description") or ""),
        ))
    return results


# ── Tavily Search API ──────────────────────────────────────────────────────────

class TavilyBackend:
    name = "tavily"

    async def search(self, query: str) -> list[WebSearchResult]:
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("SEARCH_PROVIDER=tavily but TAVILY_API_KEY is not set")
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": key,
                    "query": _normalize_query(query),
                    "max_results": MAX_BACKEND_RESULTS,
                    "search_depth": "basic",
                    # No include_domains: Tavily needs full domains (e.g. "upenn.edu"), and
                    # the .edu / college-domain restriction is enforced by the result filters.
                },
            )
            resp.raise_for_status()
            return _parse_tavily(resp.json())


def _parse_tavily(data: dict) -> list[WebSearchResult]:
    results: list[WebSearchResult] = []
    for item in (data.get("results") or []):
        url = item.get("url")
        if not url:
            continue
        results.append(WebSearchResult(
            title=_clean(item.get("title") or ""),
            url=url,
            snippet=_clean(item.get("content") or ""),
        ))
    return results


# ── Apify (run a search Actor via the REST API) ─────────────────────────────────

class ApifyBackend:
    """Run an Apify search Actor (default: Google Search Scraper) via the REST API.

    Uses run-sync-get-dataset-items (one call, no polling). Heavier/slower than Brave/
    Tavily — best when you want Google-grade coverage or already use Apify. Needs APIFY_TOKEN.
    """

    name = "apify"

    async def search(self, query: str) -> list[WebSearchResult]:
        token = os.getenv("APIFY_TOKEN")
        if not token:
            raise RuntimeError("SEARCH_PROVIDER=apify but APIFY_TOKEN is not set")
        actor = os.getenv("APIFY_ACTOR", "apify~google-search-scraper")
        url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
        payload = {
            "queries": _normalize_query(query),
            "maxPagesPerQuery": 1,
            "resultsPerPage": 10,
            "countryCode": "us",
        }
        async with httpx.AsyncClient(timeout=float(os.getenv("APIFY_TIMEOUT_S", "60"))) as client:
            resp = await client.post(url, params={"token": token}, json=payload)
            resp.raise_for_status()
            return _parse_apify(resp.json())


def _parse_apify(items) -> list[WebSearchResult]:
    """Parse Apify dataset items — Google-SERP `organicResults`, or flat `{url,...}` items."""
    results: list[WebSearchResult] = []
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        organic = item.get("organicResults")
        if isinstance(organic, list):
            for r in organic:
                url = (r or {}).get("url")
                if url:
                    results.append(WebSearchResult(
                        title=_clean(r.get("title") or ""), url=url,
                        snippet=_clean(r.get("description") or ""),
                    ))
        elif item.get("url"):
            results.append(WebSearchResult(
                title=_clean(item.get("title") or ""), url=item["url"],
                snippet=_clean(item.get("description") or item.get("text") or ""),
            ))
    return results


# ── Anthropic web_search server tool ───────────────────────────────────────────

class ClaudeWebSearchBackend:
    """Use Claude's server-side web_search tool for discovery.

    Reuses ANTHROPIC_API_KEY (no extra provider key). `max_uses` bounds cost; results
    come from `web_search_tool_result` blocks. MOCK_CLAUDE=1 returns deterministic
    results for offline dev/tests.
    """

    name = "claude_web_search"

    async def search(self, query: str) -> list[WebSearchResult]:
        natural_query = _normalize_query(query)
        if os.getenv("MOCK_CLAUDE") == "1":
            return _mock_claude_results(natural_query)

        import anthropic

        client = anthropic.AsyncAnthropic()
        # Default to the non-dynamic-filtering tool: it returns plain {url, title}
        # result items. The _20260209 version runs code-execution filtering and does
        # not expose those fields directly.
        tool_type = os.getenv("CLAUDE_WEBSEARCH_TOOL", "web_search_20250305")
        max_uses = int(os.getenv("CLAUDE_WEBSEARCH_MAX_USES", "5"))
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        prompt = (
            f"Find official university (.edu) program, department, catalog, or admissions "
            f"pages for: {natural_query}. Use web search. Prefer official institution pages "
            f"over aggregators or rankings sites."
        )
        try:
            # web_search runs several searches server-side, so it needs a longer
            # timeout than a plain completion (the agentic loop can take 60-90s).
            message = await client.messages.create(
                model=model,
                max_tokens=1024,
                tools=[{"type": tool_type, "name": "web_search", "max_uses": max_uses}],
                messages=[{"role": "user", "content": prompt}],
                timeout=float(os.getenv("CLAUDE_WEBSEARCH_TIMEOUT_S", "90")),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("claude_web_search_error", error=str(exc))
            return []
        return _parse_claude_web_search(message)


def _field(item, key: str):
    """Read a field whether the result item is a dict or an SDK object."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _parse_claude_web_search(message) -> list[WebSearchResult]:
    results: list[WebSearchResult] = []
    seen: set[str] = set()
    for block in (getattr(message, "content", None) or []):
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        items = getattr(block, "content", None)
        if not isinstance(items, list):  # an error object, not results
            continue
        for item in items:
            if _field(item, "type") != "web_search_result":
                continue
            url = _field(item, "url")
            if not url or url in seen:
                continue
            seen.add(url)
            title = _field(item, "title") or ""
            # web_search results carry no plain snippet (encrypted_content); title is
            # the only safe relevance text, and discovery re-filters on it anyway.
            results.append(WebSearchResult(title=_clean(title), url=url, snippet=_clean(title)))
    return results


def _mock_claude_results(query: str) -> list[WebSearchResult]:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-") or "program"
    return [
        WebSearchResult(
            title=f"{query} Undergraduate Program | Example University",
            url=f"https://www.example.edu/academics/{slug}",
            snippet=f"{query} undergraduate program curriculum, degree requirements, and admissions.",
        ),
        WebSearchResult(
            title=f"{query} Major | State University",
            url=f"https://www.stateuniversity.edu/programs/{slug}",
            snippet=f"Official {query} department page with degree requirements and admissions information.",
        ),
    ]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_query(query: str) -> str:
    """Strip DuckDuckGo-style operators so API backends get a natural query.

    `site:.edu "Computer Science" undergraduate program` → `Computer Science undergraduate program`.
    The official-.edu restriction is still enforced by discovery's post-filter.
    """
    cleaned = re.sub(r"\bsite:\S+", " ", query)
    cleaned = cleaned.replace('"', " ")
    return _clean(cleaned)
