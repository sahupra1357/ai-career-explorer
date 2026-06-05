"""Tests for the college course finder endpoint."""

import tempfile

import yaml
from httpx import ASGITransport, AsyncClient

from app.course_search.discovery import WebSearchResult
from app.course_finder import program_store
from app.main import app


def make_program(
    program_id: str,
    college_name: str,
    city: str,
    state: str,
    lat: float,
    lon: float,
    ranking_score: int,
) -> dict:
    return {
        "program_id": program_id,
        "course_name": "Computer Science",
        "aliases": ["cs", "computing"],
        "college_name": college_name,
        "city": city,
        "state": state,
        "lat": lat,
        "lon": lon,
        "ranking_score": ranking_score,
        "degree": "BS Computer Science",
        "delivery": "On campus",
        "overview": "A computing program.",
        "curriculum_summary": "Programming, math, systems, algorithms, and electives.",
        "semester_plan": [
            {"term": "Year 1", "focus": "Foundation", "courses": ["Programming", "Calculus"]},
            {"term": "Year 2", "focus": "Core", "courses": ["Data Structures", "Discrete Math"]},
        ],
        "required_papers": ["Transcript", "Application essays"],
        "admission_factors": ["Math rigor", "Academic fit"],
        "fees": {
            "in_state_tuition": {"amount": 12000, "label": "Resident tuition"},
            "out_of_state_tuition": {"amount": 30000, "label": "Nonresident tuition"},
            "mandatory_fees": {"amount": 1000, "label": "Fees"},
            "notes": "Confirm current costs.",
            "source_url": "https://example.edu/costs",
        },
        "decision_factors": ["Strong program", "Check net price"],
        "sources": [{"label": "Program page", "url": "https://example.edu/cs"}],
    }


def load_programs(*programs: dict) -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    yaml.dump({"programs": list(programs)}, tmp)
    tmp.close()
    program_store.load(tmp.name)


async def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _stub_no_live_results(monkeypatch) -> None:
    """Force live web discovery to return nothing so static-data tests stay deterministic."""
    monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")  # use the keyless path we stub here

    async def empty_search(client, query):
        return []

    monkeypatch.setattr("app.course_search.discovery._search_duckduckgo", empty_search)


class TestCourseSearch:
    def setup_method(self):
        load_programs(
            make_program("local-cs", "Local Tech", "Berkeley", "CA", 37.87, -122.26, 80),
            make_program("state-cs", "State University", "Los Angeles", "CA", 34.05, -118.24, 85),
            make_program("neighbor-cs", "Neighbor University", "Reno", "NV", 39.53, -119.81, 90),
            make_program("national-cs", "National Institute", "Urbana", "IL", 40.10, -88.22, 99),
        )

    async def test_returns_geographic_tiers(self, monkeypatch):
        _stub_no_live_results(monkeypatch)
        async with await client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "computer science",
                "city": "Berkeley",
                "state": "CA",
                "home_state": "CA",
            })

        assert r.status_code == 200
        tiers = {tier["tier"]: tier for tier in r.json()["tiers"]}
        assert set(tiers) == {"nearby", "home_state", "nearby_home_states", "best_usa"}
        assert tiers["nearby"]["programs"][0]["program"]["program_id"] == "local-cs"
        assert tiers["home_state"]["programs"][0]["program"]["program_id"] == "state-cs"
        assert tiers["nearby_home_states"]["programs"][0]["program"]["program_id"] == "neighbor-cs"
        assert tiers["best_usa"]["programs"][0]["program"]["program_id"] == "national-cs"

    async def test_includes_curriculum_fees_and_sources(self, monkeypatch):
        _stub_no_live_results(monkeypatch)
        async with await client() as c:
            r = await c.post("/api/course-search", json={"course_query": "cs", "state": "CA"})

        program = next(
            tier["programs"][0]["program"]
            for tier in r.json()["tiers"]
            if tier["programs"]
        )
        assert program["semester_plan"][0]["courses"]
        assert program["fees"]["source_url"].startswith("https://")
        assert program["sources"][0]["url"].startswith("https://")

    async def test_live_mode_uses_official_web_results(self, monkeypatch):
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        program_store._service.configure_live_only()

        async def fake_search(client, query):
            return [
                WebSearchResult(
                    title="Computer Science Undergraduate Program | Example University",
                    url="https://www.example.edu/academics/computer-science",
                    snippet="Computer Science undergraduate program curriculum, admissions, and degree requirements.",
                )
            ]

        monkeypatch.setattr("app.course_search.discovery._search_duckduckgo", fake_search)

        async with await client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "computer science",
                "city": "Berkeley",
                "state": "CA",
            })

        assert r.status_code == 200
        programs = [
            ranked["program"]
            for tier in r.json()["tiers"]
            for ranked in tier["programs"]
        ]
        assert programs
        assert programs[0]["program_id"].startswith("live-")
        assert programs[0]["sources"][0]["url"] == "https://www.example.edu/academics/computer-science"
        assert programs[0]["fees"]["in_state_tuition"] is None


class TestLivePageReader:
    """Phase 3: fetch official pages, extract facts, attach evidence, flag gaps."""

    def setup_method(self):
        load_programs(
            make_program("local-cs", "Local Tech", "Berkeley", "CA", 37.87, -122.26, 80),
        )

    def _wire_live(self, monkeypatch):
        monkeypatch.setenv("COURSE_READ_PAGES", "1")
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        program_store._service.configure_live_only()

        async def fake_search(client, query):
            return [
                WebSearchResult(
                    title="Computer Science Undergraduate Program | Example University",
                    url="https://www.example.edu/academics/computer-science",
                    snippet="Computer Science undergraduate program curriculum and admissions.",
                )
            ]

        monkeypatch.setattr("app.course_search.discovery._search_duckduckgo", fake_search)

    async def test_extracts_facts_and_attaches_evidence(self, monkeypatch):
        self._wire_live(monkeypatch)

        async def fake_fetch(url):
            return "Computer Science BS degree requirements. Year 1: Intro programming, Calculus."

        monkeypatch.setattr("app.course_search.reader._fetch_page_text", fake_fetch)

        async with await client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "computer science", "city": "Berkeley", "state": "CA",
            })

        assert r.status_code == 200
        program = next(
            ranked["program"]
            for tier in r.json()["tiers"]
            for ranked in tier["programs"]
            if ranked["program"]["program_id"].startswith("live-")
        )
        claim_types = {e["claim_type"] for e in program["evidence"]}
        assert {"curriculum", "admissions"} <= claim_types
        assert all(e["source_url"].startswith("https://") and e["as_of"] for e in program["evidence"])
        assert program["data_quality_flags"] == []
        assert program["last_checked_at"] is not None
        # Extracted course sequence replaced the Phase 2 placeholder.
        assert any("Intro to" in c for c in program["semester_plan"][0]["courses"])

    async def test_unreadable_page_is_flagged_not_invented(self, monkeypatch):
        self._wire_live(monkeypatch)

        async def fake_fetch(url):
            return None  # page could not be fetched

        monkeypatch.setattr("app.course_search.reader._fetch_page_text", fake_fetch)

        async with await client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "computer science", "state": "CA",
            })

        program = next(
            ranked["program"]
            for tier in r.json()["tiers"]
            for ranked in tier["programs"]
            if ranked["program"]["program_id"].startswith("live-")
        )
        assert "catalog_page_not_found" in program["data_quality_flags"]
        assert "requires_manual_review" in program["data_quality_flags"]
        assert program["evidence"] == []

    async def test_static_candidates_pass_through_unread(self, monkeypatch):
        # Reading enabled, but static fallback records are already sourced — no fetch.
        monkeypatch.setenv("COURSE_READ_PAGES", "1")
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        _stub_no_live_results(monkeypatch)  # keep live discovery out of this static-path test

        async def boom(url):
            raise AssertionError("static candidates must not be fetched")

        monkeypatch.setattr("app.course_search.reader._fetch_page_text", boom)

        async with await client() as c:
            r = await c.post("/api/course-search", json={"course_query": "cs", "state": "CA"})

        assert r.status_code == 200
