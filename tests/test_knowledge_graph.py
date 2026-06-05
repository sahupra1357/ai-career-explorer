"""Tests for the offline knowledge-graph discovery path."""

from httpx import ASGITransport, AsyncClient

from app.course_finder import program_store
from app.course_search.knowledge_graph import (
    SampleKGStore,
    college_program_from_record,
    _program_matches,
)
from app.course_search.planner import build_search_plan
from app.main import app
from app.models import CourseSearchRequest

RECORD = {
    "unitid": 999001, "name": "Test State University", "city": "Testville", "state": "CA",
    "lat": 37.0, "lon": -122.0, "control": "Public", "level": "4-year",
    "url": "https://test.edu", "admission_rate": 0.42, "tuition_in_state": 12000,
    "tuition_out_state": 30000, "avg_net_price": 15000, "grad_rate": 0.8,
    "median_earnings": 70000,
}


class TestNormalizer:
    def test_maps_core_fields_with_provenance(self):
        p = college_program_from_record(RECORD, {"cip": "11.07", "title": "Computer Science"},
                                        "College Scorecard", 2023)
        assert p.program_id == "kg-999001-1107"
        assert p.course_name == "Computer Science"
        assert (p.lat, p.lon) == (37.0, -122.0)        # real institution coords
        assert p.fees.in_state_tuition.amount == 12000
        assert "2023" in p.fees.in_state_tuition.label  # source-dated label
        assert p.fees.source_url.startswith("https://")
        assert any(e.claim_type == "fees" and e.as_of.year == 2023 for e in p.evidence)
        # ranking_score is now a transparent composite of grad/earnings/selectivity/value:
        # 0.8*.35 + 0.444*.30 + 0.58*.20 + 0.714*.15 ≈ 0.636 → 64
        assert p.ranking_score == 64

    def test_program_level_gaps_are_flagged_not_invented(self):
        p = college_program_from_record(RECORD, {"cip": "11.07", "title": "Computer Science"},
                                        "College Scorecard", 2023)
        assert "missing_curriculum_source" in p.data_quality_flags
        assert "verify" in p.curriculum_summary.lower()  # honest placeholder, no fake courses

    def test_missing_metrics_omitted_not_zeroed(self):
        bare = {**RECORD, "tuition_in_state": None, "grad_rate": None, "admission_rate": None,
                "median_earnings": None, "avg_net_price": None}
        p = college_program_from_record(bare, {"cip": "11.07", "title": "Computer Science"},
                                        "College Scorecard", 2023)
        assert p.fees.in_state_tuition is None           # absent, not $0
        assert p.ranking_score == 50                     # neutral default, nothing fabricated


class TestRankingAndStrength:
    def _program(self, **overrides):
        return college_program_from_record({**RECORD, **overrides},
                                           {"cip": "11.07", "title": "Computer Science"},
                                           "College Scorecard", 2023)

    def test_composite_ranks_stronger_school_higher(self):
        strong = self._program(grad_rate=0.97, median_earnings=120000, admission_rate=0.05, avg_net_price=18000)
        weak = self._program(grad_rate=0.45, median_earnings=42000, admission_rate=0.90, avg_net_price=22000)
        assert strong.ranking_score > weak.ranking_score

    def test_strength_breakdown_is_labeled_not_usnews(self):
        p = self._program()
        line = next((f for f in p.decision_factors if "Composite strength" in f), None)
        assert line is not None
        assert "NOT a U.S. News rank" in line
        assert "graduation rate" in line  # inputs are shown
        assert any(e.claim_type == "ranking" for e in p.evidence)

    def test_rankings_are_verify_links_only(self):
        p = self._program()
        names = {r.name for r in p.rankings}
        assert any("U.S. News" in n for n in names) and any("Niche" in n for n in names)
        for r in p.rankings:
            assert r.url.startswith("https://")
            assert "Test+State+University" in r.url  # college name, url-encoded (quote_plus)
            assert "not reproduced" in r.note.lower()
            # RankingLink carries no numeric rank value — nothing proprietary is stored.
            assert not hasattr(r, "value") and not hasattr(r, "rank")

    def test_program_matches(self):
        assert _program_matches("computer science", "Computer Science")
        assert _program_matches("cs", "Computer Science and Engineering") or \
               _program_matches("computer science", "Computer Science and Engineering")
        assert not _program_matches("nursing", "Computer Science")


class TestSampleStore:
    async def test_finds_cs_across_states(self):
        store = SampleKGStore()
        plan = build_search_plan(CourseSearchRequest(course_query="Computer Science", state="CA"))
        programs = await store.find_programs(plan)
        states = {p.state for p in programs}
        assert {"CA", "WA", "OR", "NV", "IL", "NY", "MA"} & states
        # Real, distinct coordinates per college (the live-path geo bug does not occur here).
        coords = {(p.lat, p.lon) for p in programs}
        assert len(coords) == len(programs)

    async def test_abbreviation_resolves_via_cip(self):
        # "cs" matched nothing under title-only matching; the CIP alias map fixes it.
        store = SampleKGStore()
        plan = build_search_plan(CourseSearchRequest(course_query="cs", state="CA"))
        programs = await store.find_programs(plan)
        assert programs
        assert any("Berkeley" in p.college_name for p in programs)
        assert all("Computer Science" in p.course_name for p in programs)

    async def test_carnegie_flows_from_sample(self):
        store = SampleKGStore()
        plan = build_search_plan(CourseSearchRequest(course_query="Computer Science", state="CA"))
        programs = await store.find_programs(plan)
        berkeley = next(p for p in programs if "Berkeley" in p.college_name)
        assert berkeley.carnegie_classification and "R1" in berkeley.carnegie_classification


class TestCarnegieAndLicensed:
    def _rec(self, **overrides):
        return {**RECORD, **overrides}

    def _make(self, rec):
        return college_program_from_record(rec, {"cip": "11.07", "title": "Computer Science"},
                                           "College Scorecard", 2023)

    def test_carnegie_shown_when_present(self):
        p = self._make(self._rec(carnegie="R1: Doctoral – Very High Research", carnegie_year=2021))
        assert p.carnegie_classification == "R1: Doctoral – Very High Research"
        assert any("Carnegie Classification" in f for f in p.decision_factors)
        ev = next((e for e in p.evidence if e.source_label == "Carnegie Classification"), None)
        assert ev is not None and ev.as_of.year == 2021

    def test_licensed_ranks_hidden_by_default(self, monkeypatch):
        monkeypatch.delenv("RANKINGS_LICENSED", raising=False)
        rec = self._rec(licensed_rankings=[
            {"provider": "U.S. News", "rank": 3, "list_name": "National Universities", "year": 2025}])
        p = self._make(rec)
        assert p.licensed_rankings == []                       # gated off — nothing proprietary
        assert not any("rank #" in f for f in p.decision_factors)  # no licensed value line

    def test_licensed_ranks_shown_when_licensed(self, monkeypatch):
        monkeypatch.setenv("RANKINGS_LICENSED", "1")
        rec = self._rec(licensed_rankings=[
            {"provider": "U.S. News", "rank": 3, "list_name": "National Universities", "year": 2025}])
        p = self._make(rec)
        assert len(p.licensed_rankings) == 1
        lr = p.licensed_rankings[0]
        assert (lr.provider, lr.rank, lr.year) == ("U.S. News", 3, 2025)
        assert any("U.S. News rank #3" in f for f in p.decision_factors)
        assert any(e.source_label == "U.S. News (licensed)" for e in p.evidence)


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestKGEnrichment:
    async def test_enriches_only_shown_programs_via_pinpoint(self, monkeypatch):
        monkeypatch.setenv("COURSE_SEARCH_MODE", "kg")
        monkeypatch.setenv("KG_BACKEND", "sample")
        monkeypatch.setenv("COURSE_READ_PAGES", "1")  # opt-in enrichment
        monkeypatch.setenv("MOCK_CLAUDE", "1")        # mock the extraction
        program_store._service.configure_knowledge_graph()

        seen_domains: list[str] = []

        async def fake_find(domain, college_name, course, request_id):
            seen_domains.append(domain)               # pinpoint, per-college+course
            return [f"https://{domain}/programs/{course.lower().replace(' ', '-')}"]

        async def fake_fetch(url):
            return "Computer Science BS. Year 1: Intro programming and Calculus. Apply with transcript."

        from app.course_search.reader import clear_enrichment_cache
        clear_enrichment_cache()
        monkeypatch.setattr("app.course_search.reader._find_program_pages", fake_find)
        monkeypatch.setattr("app.course_search.reader._fetch_page_text", fake_fetch)

        async with await _client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "Computer Science", "city": "Berkeley", "state": "CA", "home_state": "CA",
            })

        prog = next(rp["program"] for t in r.json()["tiers"] for rp in t["programs"]
                    if "Berkeley" in rp["program"]["college_name"])
        # Pinpoint search was scoped to the college's own domain.
        assert "berkeley.edu" in seen_domains
        # Curriculum gap is now filled and the flag cleared.
        assert "missing_curriculum_source" not in prog["data_quality_flags"]
        assert any("Intro to" in course for course in prog["semester_plan"][0]["courses"])
        # The official program-page link is prepended as the first source.
        assert prog["sources"][0]["label"] == "Official program page"
        assert "/programs/" in prog["sources"][0]["url"]


class TestEndToEndKG:
    async def test_kg_mode_returns_geo_correct_tiers(self, monkeypatch):
        monkeypatch.setenv("COURSE_SEARCH_MODE", "kg")
        monkeypatch.setenv("KG_BACKEND", "sample")
        program_store._service.configure_knowledge_graph()

        async with await _client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "Computer Science", "city": "Berkeley", "state": "CA",
                "home_state": "CA",
            })

        assert r.status_code == 200
        tiers = {t["tier"]: t for t in r.json()["tiers"]}
        # Berkeley CS lands in the nearby tier with a real distance (not 0 for everyone).
        nearby = tiers["nearby"]["programs"]
        assert any(rp["program"]["state"] == "CA" for rp in nearby)
        # Out-of-region schools (e.g. Columbia NY, MIT MA) are NOT in nearby.
        nearby_states = {rp["program"]["state"] for rp in nearby}
        assert "NY" not in nearby_states and "MA" not in nearby_states
        # Provenance flows through to the API.
        any_prog = nearby[0]["program"]
        assert any_prog["evidence"]
        assert any_prog["fees"]["source_url"].startswith("https://")
