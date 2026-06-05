"""Knowledge-graph discovery: serve colleges from a pre-built offline index.

DESIGN.md §16 / §13: instead of running a live web search on every request (60-90s),
pre-aggregate the finite set of US institutions offline from College Scorecard and serve
course→colleges as an instant local lookup. This is the natural successor to the static
YAML fallback — same `ProgramDiscoveryProvider` interface, but real coverage, real
institution coordinates (fixes the live-result geo bug), and provenance on every figure.

Two stores behind one interface:
  • SampleKGStore   — in-memory from data/scorecard_sample.json. Zero infra; dev/tests/demo.
  • PostgresKGStore — queries the kg_* tables built by scripts/build_kg.py. Production.

Honest gaps: Scorecard gives institution-level facts (location, admission rate, tuition,
net price, grad rate, earnings) and which programs a school offers — NOT per-program
curriculum or deadlines. Those stay unavailable-with-a-flag here and are filled lazily by
the live page reader. No figure is emitted without a source label + as_of year.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

from rapidfuzz import fuzz

from urllib.parse import quote_plus

from app.models import (
    CollegeProgram,
    LicensedRanking,
    MoneyAmount,
    ProgramEvidence,
    ProgramFees,
    ProgramSource,
    RankingLink,
    SemesterPlan,
)

CARNEGIE_SOURCE_URL = "https://carnegieclassifications.acenet.edu/"

from .cip_aliases import CourseResolution, resolve_course
from .models import AgentRun, ProgramCandidate, SearchPlan

SCORECARD_SAMPLE = Path("data/scorecard_sample.json")
_MATCH_CUTOFF = 60


# ── Normalizer (pure) ───────────────────────────────────────────────────────────

def college_program_from_record(
    college: dict,
    program: dict,
    source_label: str,
    as_of_year: int,
) -> CollegeProgram:
    """Map one (institution, offered program) into a standardized CollegeProgram.

    Every figure carries `source_label` + `as_of_year`; program-level fields not present
    in the institutional dataset are flagged unavailable rather than invented.
    """
    unitid = college["unitid"]
    cip = program["cip"]
    title = program["title"]
    as_of = date(as_of_year, 1, 1)
    scorecard_url = f"https://collegescorecard.ed.gov/school/?{unitid}"
    official_url = college.get("url") or scorecard_url

    ranking_score, strength_breakdown = _composite_strength(college)

    fees = _build_fees(college, source_label, as_of_year, scorecard_url)
    admission_factors = _admission_factors(college, source_label, as_of_year)
    decision_factors = _decision_factors(college, source_label, as_of_year)
    decision_factors.append(
        f"Composite strength {ranking_score}/100 — {', '.join(strength_breakdown)} "
        f"(transparent composite from {source_label} {as_of_year}; NOT a U.S. News rank)."
    )
    evidence = _evidence(college, source_label, as_of, scorecard_url)
    evidence.append(ProgramEvidence(
        claim_type="ranking",
        claim=(
            "Composite strength score derived from open College Scorecard outcomes "
            "(graduation, earnings, selectivity, value). Not a proprietary U.S. News rank."
        ),
        source_url=scorecard_url, source_label=f"{source_label} (composite)",
        as_of=as_of, confidence="low",
    ))

    # Carnegie Classification (free, official) — always shown when present.
    carnegie = college.get("carnegie")
    if carnegie:
        carnegie_year = college.get("carnegie_year") or as_of_year
        decision_factors.append(f"Carnegie Classification: {carnegie} (Carnegie/ACE {carnegie_year}).")
        evidence.append(ProgramEvidence(
            claim_type="ranking", claim=f"Carnegie Classification: {carnegie}.",
            source_url=CARNEGIE_SOURCE_URL, source_label="Carnegie Classification",
            as_of=date(carnegie_year, 1, 1), confidence="high",
        ))

    # Licensed provider ranks (e.g. U.S. News) — emitted ONLY when licensed.
    licensed_rankings = _licensed_rankings(college, decision_factors, evidence, as_of)

    return CollegeProgram(
        program_id=f"kg-{unitid}-{cip.replace('.', '')}",
        course_name=title,
        aliases=[],
        college_name=college["name"],
        city=college["city"],
        state=college["state"],
        lat=float(college["lat"]),
        lon=float(college["lon"]),
        ranking_score=ranking_score,
        degree=f"{title} ({college.get('level', 'program')})",
        delivery="Verify on official source",
        overview=(
            f"{college['name']} reports offering {title} (CIP {cip}). "
            f"Institution-level facts below are from {source_label} {as_of_year}; "
            f"verify program specifics on the official site."
        ),
        curriculum_summary=(
            "Course sequence is not in the institutional dataset — "
            "verify the curriculum on the official program page."
        ),
        semester_plan=[
            SemesterPlan(
                term="Official source",
                focus="Program requirements",
                courses=["See the official program page for the current course sequence."],
            )
        ],
        required_papers=["Verify required application materials on the official admissions page."],
        admission_factors=admission_factors,
        fees=fees,
        decision_factors=decision_factors,
        sources=[
            ProgramSource(label=f"{source_label} institution page", url=scorecard_url),
            ProgramSource(label="Official institution site", url=official_url),
        ],
        evidence=evidence,
        data_quality_flags=["missing_curriculum_source"],
        last_checked_at=datetime.now(timezone.utc),
        rankings=_ranking_links(college["name"]),
        carnegie_classification=carnegie,
        licensed_rankings=licensed_rankings,
    )


# Transparent strength composite from open Scorecard outcomes (NOT U.S. News).
# Weights and reference ranges are explicit so the score is explainable + auditable.
_STRENGTH_WEIGHTS = {"grad": 0.35, "earnings": 0.30, "selectivity": 0.20, "value": 0.15}
_STRENGTH_LABELS = {
    "grad": "graduation rate", "earnings": "median earnings",
    "selectivity": "admission selectivity", "value": "net-price value",
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _composite_strength(college: dict) -> tuple[int, list[str]]:
    """A 1-100 strength score blended from available Scorecard metrics, plus a per-factor
    breakdown. Missing metrics are skipped and the weights renormalized (never invented)."""
    parts: dict[str, float] = {}
    if college.get("grad_rate") is not None:
        parts["grad"] = _clamp01(college["grad_rate"])
    if college.get("median_earnings") is not None:
        parts["earnings"] = _clamp01((college["median_earnings"] - 30_000) / (120_000 - 30_000))
    if college.get("admission_rate") is not None:
        parts["selectivity"] = _clamp01(1 - college["admission_rate"])
    if college.get("avg_net_price") is not None:
        parts["value"] = _clamp01((40_000 - college["avg_net_price"]) / (40_000 - 5_000))

    if not parts:
        return 50, ["strength unavailable — no outcome metrics in the dataset"]

    total_w = sum(_STRENGTH_WEIGHTS[k] for k in parts)
    composite = sum(parts[k] * _STRENGTH_WEIGHTS[k] for k in parts) / total_w
    score = max(1, min(100, round(composite * 100)))
    breakdown = [
        f"{_STRENGTH_LABELS[k]} {round(parts[k] * 100)}/100"
        for k in ("grad", "earnings", "selectivity", "value") if k in parts
    ]
    return score, breakdown


def _ranking_links(name: str) -> list[RankingLink]:
    """Verify-links to external rankings — search URLs only, no proprietary values copied."""
    q = quote_plus(name)
    return [
        RankingLink(name="U.S. News (search)", url=f"https://www.usnews.com/best-colleges/search?name={q}"),
        RankingLink(name="Niche (search)", url=f"https://www.niche.com/colleges/search/best-colleges/?q={q}"),
    ]


def rankings_licensed() -> bool:
    """True only when the operator holds a ranking data licence (RANKINGS_LICENSED=1)."""
    return os.getenv("RANKINGS_LICENSED") == "1"


def _licensed_rankings(
    college: dict,
    decision_factors: list[str],
    evidence: list[ProgramEvidence],
    as_of: date,
) -> list[LicensedRanking]:
    """Map licensed provider ranks (e.g. U.S. News) — ONLY when RANKINGS_LICENSED=1.

    Off by default: even if rank values were fetched, nothing proprietary is emitted
    without a licence. This is the single compliance gate for licensed values.
    """
    if not rankings_licensed():
        return []
    result: list[LicensedRanking] = []
    for lr in (college.get("licensed_rankings") or []):
        if lr.get("rank") is None or not lr.get("provider"):
            continue
        ranking = LicensedRanking(
            provider=lr["provider"], rank=int(lr["rank"]),
            list_name=lr.get("list_name"), year=int(lr.get("year") or as_of.year),
            source_url=lr.get("source_url"),
        )
        result.append(ranking)
        listing = f" in {ranking.list_name}" if ranking.list_name else ""
        decision_factors.append(
            f"{ranking.provider} rank #{ranking.rank}{listing} ({ranking.year}) — licensed."
        )
        evidence.append(ProgramEvidence(
            claim_type="ranking",
            claim=f"{ranking.provider} rank #{ranking.rank}{listing} ({ranking.year}).",
            source_url=ranking.source_url or "", source_label=f"{ranking.provider} (licensed)",
            as_of=date(ranking.year, 1, 1), confidence="high",
        ))
    return result


def _money(amount, label: str) -> MoneyAmount | None:
    return MoneyAmount(amount=int(amount), label=label) if amount is not None else None


def _build_fees(college: dict, source: str, year: int, url: str) -> ProgramFees:
    return ProgramFees(
        in_state_tuition=_money(
            college.get("tuition_in_state"),
            f"In-state tuition & fees ({source} {year})",
        ),
        out_of_state_tuition=_money(
            college.get("tuition_out_state"),
            f"Out-of-state tuition & fees ({source} {year})",
        ),
        mandatory_fees=None,
        notes=(
            f"Tuition from {source} {year}. Confirm the current cost of attendance on the "
            "official bursar / financial-aid page before applying."
        ),
        source_url=url,
    )


def _admission_factors(college: dict, source: str, year: int) -> list[str]:
    factors: list[str] = []
    rate = college.get("admission_rate")
    if rate is not None:
        factors.append(f"Admission rate {rate:.0%} ({source} {year})")
    factors.append("Verify current requirements and deadlines on the official admissions page.")
    return factors


def _decision_factors(college: dict, source: str, year: int) -> list[str]:
    factors: list[str] = []
    if college.get("grad_rate") is not None:
        factors.append(f"Graduation rate {college['grad_rate']:.0%} ({source} {year})")
    if college.get("median_earnings") is not None:
        factors.append(f"Median earnings ${college['median_earnings']:,} ({source} {year})")
    if college.get("avg_net_price") is not None:
        factors.append(f"Average net price ${college['avg_net_price']:,} ({source} {year})")
    if college.get("control"):
        factors.append(f"{college['control']} institution")
    return factors


def _evidence(college: dict, source: str, as_of: date, url: str) -> list[ProgramEvidence]:
    evidence = [ProgramEvidence(
        claim_type="identity",
        claim=f"{college['name']} is located in {college['city']}, {college['state']}.",
        source_url=url, source_label=source, as_of=as_of, confidence="high",
    )]
    if college.get("admission_rate") is not None:
        evidence.append(ProgramEvidence(
            claim_type="admissions",
            claim=f"Admission rate {college['admission_rate']:.0%}.",
            source_url=url, source_label=source, as_of=as_of, confidence="high",
        ))
    if college.get("tuition_in_state") is not None:
        evidence.append(ProgramEvidence(
            claim_type="fees",
            claim="In/out-of-state tuition from the institutional dataset.",
            source_url=url, source_label=source, as_of=as_of, confidence="high",
        ))
    if college.get("grad_rate") is not None or college.get("median_earnings") is not None:
        evidence.append(ProgramEvidence(
            claim_type="outcomes",
            claim="Graduation rate and median earnings from the institutional dataset.",
            source_url=url, source_label=source, as_of=as_of, confidence="high",
        ))
    return evidence


_STOPWORDS = {"and", "of", "the", "in", "for", "a", "an"}


def _program_matches(query: str, title: str) -> bool:
    """Match by covering the query's significant tokens, so "Computer Science" does not
    pull in "Data Science" just because they share the word "science"."""
    q, t = query.lower().strip(), title.lower()
    if q in t or t in q:
        return True
    q_tokens = [w for w in re.findall(r"[a-z]+", q) if len(w) >= 4 and w not in _STOPWORDS]
    if not q_tokens:  # short/abbreviated query (e.g. "cs") — fall back to fuzzy whole-string
        return fuzz.token_set_ratio(q, t) >= 80
    t_tokens = re.findall(r"[a-z]+", t)
    return all(any(fuzz.ratio(qt, tt) >= 80 for tt in t_tokens) for qt in q_tokens)


def _match_score(query: str, title: str) -> float:
    """Rank matching program titles so we can keep the best one per college."""
    q, t = query.lower().strip(), title.lower()
    if q == t:
        return 101.0
    if q in t or t in q:
        return 90.0
    return float(fuzz.token_set_ratio(q, t))


def _cip_digits(cip: str) -> str:
    return re.sub(r"\D", "", cip or "")


def _cip_hit(program_cip: str, cips: tuple[str, ...]) -> bool:
    pc = _cip_digits(program_cip)
    return any(pc.startswith(_cip_digits(c)) for c in cips if _cip_digits(c))


def _program_course_score(query: str, resolution: CourseResolution | None, program: dict) -> float | None:
    """Score a program {cip,title}; None means no match. CIP match (when the query resolves
    to a canonical course) is the strongest signal; title matching is the fallback."""
    title = program.get("title", "")
    if resolution and _cip_hit(program.get("cip", ""), resolution.cips):
        return 100.0 + _match_score(resolution.name, title) / 100.0  # CIP hit, prefer exact title
    if _program_matches(query, title):
        return _match_score(query, title)
    if resolution and _program_matches(resolution.name, title):  # e.g. "CS" → "Computer Science"
        return _match_score(resolution.name, title)
    return None


def _best_program(query: str, programs: list[dict]) -> dict | None:
    """Pick the single best-matching program for a college (course search → one row each)."""
    resolution = resolve_course(query)
    scored = [
        (p, s) for p in programs
        if (s := _program_course_score(query, resolution, p)) is not None
    ]
    return max(scored, key=lambda m: m[1])[0] if scored else None


# ── Stores ───────────────────────────────────────────────────────────────────────

class KGStore(Protocol):
    name: str

    async def find_programs(self, plan: SearchPlan) -> list[CollegeProgram]:
        """Return colleges offering a program matching the query (any tier)."""


class SampleKGStore:
    """In-memory store backed by data/scorecard_sample.json (no DB required)."""

    name = "sample"

    def __init__(self, path: str | Path = SCORECARD_SAMPLE) -> None:
        raw = json.loads(Path(path).read_text())
        self._colleges: list[dict] = raw.get("colleges", [])
        self._source = raw.get("source", "College Scorecard")
        self._as_of = int(raw.get("as_of", date.today().year))

    async def find_programs(self, plan: SearchPlan) -> list[CollegeProgram]:
        results: list[CollegeProgram] = []
        for college in self._colleges:
            best = _best_program(plan.normalized_query, college.get("programs", []))
            if best is not None:  # one row per college: its best-matching program
                results.append(college_program_from_record(
                    college, best, self._source, self._as_of,
                ))
        return results

    def __len__(self) -> int:
        return sum(len(c.get("programs", [])) for c in self._colleges)


class PostgresKGStore:
    """Query the kg_colleges / kg_offerings tables built by scripts/build_kg.py.

    Uses a lazily-created connection pool shared across requests.
    """

    name = "postgres"
    _pools: dict[str, object] = {}

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def _pool(self):
        import asyncpg

        pool = PostgresKGStore._pools.get(self._database_url)
        if pool is None:
            pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)
            PostgresKGStore._pools[self._database_url] = pool
        return pool

    async def find_programs(self, plan: SearchPlan) -> list[CollegeProgram]:
        resolution = resolve_course(plan.normalized_query)
        cip_patterns = [_cip_digits(c) + "%" for c in resolution.cips] if resolution else []

        pool = await self._pool()
        rows = await pool.fetch(
            """
            SELECT c.unitid, c.name, c.city, c.state, c.lat, c.lon, c.control,
                   c.level, c.url, c.admission_rate, c.tuition_in_state,
                   c.tuition_out_state, c.avg_net_price, c.grad_rate,
                   c.median_earnings, c.carnegie, c.carnegie_year, c.source, c.as_of,
                   o.cip, o.title
            FROM kg_offerings o
            JOIN kg_colleges c USING (unitid)
            WHERE o.course_norm % $1 OR o.course_norm ILIKE '%' || $1 || '%'
               OR o.cip LIKE ANY($2::text[])
            """,
            plan.normalized_query.lower(),
            cip_patterns,
        )

        # Group rows by college, keep the single best-matching program per college
        # (SQL is a coarse prefilter; the resolution-aware scorer decides).
        best_by_college: dict[int, tuple] = {}
        for r in rows:
            score = _program_course_score(
                plan.normalized_query, resolution, {"cip": r["cip"], "title": r["title"]}
            )
            if score is None:
                continue
            current = best_by_college.get(r["unitid"])
            if current is None or score > current[1]:
                best_by_college[r["unitid"]] = (r, score)

        # Licensed ranks: one extra query for the matched colleges, only when licensed.
        licensed_by_unitid: dict[int, list[dict]] = {}
        if rankings_licensed() and best_by_college:
            rank_rows = await pool.fetch(
                """
                SELECT unitid, provider, rank, list_name, year, source_url
                FROM kg_rankings WHERE unitid = ANY($1::int[])
                """,
                list(best_by_college.keys()),
            )
            for rr in rank_rows:
                licensed_by_unitid.setdefault(rr["unitid"], []).append(dict(rr))

        results: list[CollegeProgram] = []
        for r, _ in best_by_college.values():
            college = {
                "unitid": r["unitid"], "name": r["name"], "city": r["city"],
                "state": r["state"], "lat": r["lat"], "lon": r["lon"],
                "control": r["control"], "level": r["level"], "url": r["url"],
                "admission_rate": r["admission_rate"],
                "tuition_in_state": r["tuition_in_state"],
                "tuition_out_state": r["tuition_out_state"],
                "avg_net_price": r["avg_net_price"], "grad_rate": r["grad_rate"],
                "median_earnings": r["median_earnings"],
                "carnegie": r["carnegie"], "carnegie_year": r["carnegie_year"],
                "licensed_rankings": licensed_by_unitid.get(r["unitid"], []),
            }
            program = {"cip": r["cip"], "title": r["title"]}
            results.append(college_program_from_record(
                college, program, r["source"], r["as_of"],
            ))
        return results


def get_kg_store() -> KGStore:
    """Pick the KG store: Postgres when DATABASE_URL + KG_BACKEND=postgres, else the sample."""
    if os.getenv("KG_BACKEND") == "postgres" and os.getenv("DATABASE_URL"):
        return PostgresKGStore(os.environ["DATABASE_URL"])
    return SampleKGStore()


# ── Discovery provider ─────────────────────────────────────────────────────────

class KnowledgeGraphDiscoveryProvider:
    """Serve pre-indexed colleges instantly, as a ProgramDiscoveryProvider."""

    name = "knowledge_graph"

    def __init__(self, store: KGStore | None = None) -> None:
        self.store = store or get_kg_store()

    async def discover(self, plan: SearchPlan) -> tuple[list[ProgramCandidate], AgentRun]:
        try:
            programs = await self.store.find_programs(plan)
        except Exception as exc:  # noqa: BLE001
            return [], AgentRun(
                agent=self.name, status="error",
                message=f"Knowledge-graph lookup failed ({self.store.name}): {exc}", count=0,
            )
        candidates = [
            ProgramCandidate(
                program=program,
                provider="knowledge_graph",
                confidence=0.85,
                evidence_notes=["Pre-indexed from College Scorecard with provenance."],
            )
            for program in programs
        ]
        status = "success" if candidates else "empty"
        return candidates, AgentRun(
            agent=self.name, status=status,
            message=(
                f"Matched {len(candidates)} program(s) from the knowledge graph "
                f"({self.store.name})."
                if candidates else
                "No knowledge-graph programs matched the course query."
            ),
            count=len(candidates),
        )
