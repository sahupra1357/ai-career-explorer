"""Integration tests for all FastAPI endpoints.

Uses httpx.AsyncClient + ASGITransport — no real network, no real Claude.
The KB is populated via store.load() against a temp YAML file before each test class.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.kb import store
from app.summarize import clear_cache
from tests.conftest import make_field


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_store(*field_dicts: dict) -> None:
    """Write field dicts to a temp YAML and reload the singleton store."""
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    yaml.dump({"fields": list(field_dicts)}, tmp)
    tmp.close()
    store.load(tmp.name)


async def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealth:
    async def test_returns_ok(self):
        load_store(make_field("cs", "Computer Science"))
        async with await client() as c:
            r = await c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    async def test_reports_correct_field_count(self):
        load_store(make_field("cs", "CS"), make_field("bio", "Bio"))
        async with await client() as c:
            r = await c.get("/health")
        assert r.json()["fields_loaded"] == 2


# ── GET /api/fields ───────────────────────────────────────────────────────────

class TestListFields:
    async def test_returns_200_list(self):
        load_store(make_field("cs", "Computer Science"))
        async with await client() as c:
            r = await c.get("/api/fields")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_returns_field_id_and_name(self):
        load_store(make_field("cs", "Computer Science"))
        async with await client() as c:
            r = await c.get("/api/fields")
        assert r.json() == [{"field_id": "cs", "name": "Computer Science"}]

    async def test_empty_kb_returns_empty_list(self):
        load_store()
        async with await client() as c:
            r = await c.get("/api/fields")
        assert r.json() == []

    async def test_returns_all_loaded_fields(self):
        load_store(make_field("cs", "CS"), make_field("bio", "Bio"), make_field("math", "Math"))
        async with await client() as c:
            r = await c.get("/api/fields")
        ids = {f["field_id"] for f in r.json()}
        assert ids == {"cs", "bio", "math"}


# ── POST /api/compare — happy paths ──────────────────────────────────────────

class TestCompareSuccess:
    def setup_method(self):
        clear_cache()
        load_store(
            make_field("computer-science", "Computer Science"),
            make_field("biomedical-engineering", "Biomedical Engineering"),
            make_field("applied-mathematics", "Applied Mathematics"),
        )

    async def test_two_fields_returns_200(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
        assert r.status_code == 200

    async def test_response_contains_request_id(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
        assert "request_id" in r.json()
        assert len(r.json()["request_id"]) == 36  # UUID format

    async def test_response_contains_both_fields(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
        data = r.json()
        returned_ids = {f["field_id"] for f in data["fields"]}
        assert returned_ids == {"computer-science", "biomedical-engineering"}

    async def test_three_fields_returns_200(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={
                "fields": ["computer-science", "biomedical-engineering", "applied-mathematics"]
            })
        assert r.status_code == 200
        assert len(r.json()["fields"]) == 3

    async def test_summary_status_ready_with_mock(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
        assert r.json()["summary_status"] == "ready"

    async def test_mock_summary_contains_mock_tag(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
        assert "[MOCK]" in r.json()["comparison_summary"]

    async def test_comparison_fields_used_matches_input(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
        assert set(r.json()["comparison_fields_used"]) == {"computer-science", "biomedical-engineering"}

    async def test_display_names_are_accepted(self):
        """Field names like 'Computer Science' should be normalised to slugs."""
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["Computer Science", "Biomedical Engineering"]})
        assert r.status_code == 200

    async def test_summary_status_error_when_claude_fails(self, monkeypatch):
        from app import summarize as summarize_mod
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        clear_cache()

        async def returning_none(prompt, request_id):
            return None

        with patch.object(summarize_mod, "_call_claude", returning_none):
            async with await client() as c:
                r = await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})

        assert r.status_code == 200
        assert r.json()["summary_status"] == "error"
        assert r.json()["comparison_summary"] is None


# ── POST /api/compare — not-found paths ──────────────────────────────────────

class TestCompareNotFound:
    def setup_method(self):
        clear_cache()
        load_store(make_field("computer-science", "Computer Science"))

    async def test_all_unknown_returns_404(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["unknown-a", "unknown-b"]})
        assert r.status_code == 404

    async def test_404_body_has_not_found_error(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["unknown-a", "unknown-b"]})
        assert r.json()["error"] == "not_found"

    async def test_404_body_has_message_mentioning_field(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["unknown-a", "unknown-b"]})
        assert "unknown-a" in r.json()["message"]

    async def test_404_suggestions_is_list(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["unknown-a", "unknown-b"]})
        assert isinstance(r.json()["suggestions"], list)

    async def test_partial_not_found_returns_422(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "unknown-field"]})
        assert r.status_code == 422

    async def test_422_body_has_partial_not_found_error(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "unknown-field"]})
        assert r.json()["error"] == "partial_not_found"

    async def test_422_body_has_found_and_not_found_lists(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "unknown-field"]})
        data = r.json()
        assert "computer-science" in data["found"]
        assert "unknown-field" in data["not_found"]

    async def test_422_suggestions_is_dict(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-science", "unknown-field"]})
        assert isinstance(r.json()["suggestions"], dict)

    async def test_fuzzy_suggestions_returned_for_close_typo(self):
        """'computer-sciences' (with trailing s) should suggest 'computer-science'."""
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["computer-sciences", "unknown-b"]})
        data = r.json()
        # Both are unknown → 404; suggestions for first field should contain the close match
        if data.get("error") == "not_found":
            assert "computer-science" in data["suggestions"]


# ── POST /api/compare — validation errors ─────────────────────────────────────

class TestCompareValidation:
    def setup_method(self):
        load_store(make_field("cs", "CS"))

    async def test_single_field_returns_422(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["cs"]})
        assert r.status_code == 422

    async def test_four_fields_returns_422(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["a", "b", "c", "d"]})
        assert r.status_code == 422

    async def test_empty_fields_returns_422(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": []})
        assert r.status_code == 422

    async def test_duplicate_fields_returns_422(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={"fields": ["cs", "cs"]})
        assert r.status_code == 422

    async def test_missing_fields_key_returns_422(self):
        async with await client() as c:
            r = await c.post("/api/compare", json={})
        assert r.status_code == 422


# ── POST /api/cache/clear ─────────────────────────────────────────────────────

class TestCacheClear:
    async def test_returns_cleared_count_zero_when_empty(self):
        clear_cache()
        async with await client() as c:
            r = await c.post("/api/cache/clear")
        assert r.status_code == 200
        assert r.json()["cleared"] == 0

    async def test_returns_cleared_count_after_compare(self, monkeypatch):
        # MOCK_CLAUDE bypasses the cache entirely — disable it and use a patched _call_claude
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        clear_cache()
        load_store(
            make_field("computer-science", "Computer Science"),
            make_field("biomedical-engineering", "Biomedical Engineering"),
        )
        from app import summarize as summarize_mod

        async def fake_claude(prompt, request_id):
            return "A real summary."

        with patch.object(summarize_mod, "_call_claude", fake_claude):
            async with await client() as c:
                await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
                r = await c.post("/api/cache/clear")
        assert r.json()["cleared"] >= 1

    async def test_cache_empty_after_clear(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        clear_cache()
        load_store(
            make_field("computer-science", "Computer Science"),
            make_field("biomedical-engineering", "Biomedical Engineering"),
        )
        from app import summarize as summarize_mod
        call_count = 0

        async def counting_claude(prompt, request_id):
            nonlocal call_count
            call_count += 1
            return "Summary."

        with patch.object(summarize_mod, "_call_claude", counting_claude):
            async with await client() as c:
                await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})
                await c.post("/api/cache/clear")
                await c.post("/api/compare", json={"fields": ["computer-science", "biomedical-engineering"]})

        assert call_count == 2  # Claude called twice because cache was cleared between
