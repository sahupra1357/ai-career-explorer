"""Tests for pluggable discovery search backends (Brave / Tavily / Claude)."""

from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

from app.course_finder import program_store
from app.course_search.search_backends import (
    ApifyBackend,
    BraveBackend,
    ClaudeWebSearchBackend,
    TavilyBackend,
    _parse_apify,
    _parse_brave,
    _parse_claude_web_search,
    _parse_tavily,
    get_search_backend,
)
from app.main import app


class TestBackendSelection:
    def test_default_is_tavily(self, monkeypatch):
        monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
        assert isinstance(get_search_backend(), TavilyBackend)

    def test_explicit_duckduckgo_is_none(self, monkeypatch):
        monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
        assert get_search_backend() is None

    def test_selects_each_provider(self, monkeypatch):
        monkeypatch.setenv("SEARCH_PROVIDER", "brave")
        assert isinstance(get_search_backend(), BraveBackend)
        monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
        assert isinstance(get_search_backend(), TavilyBackend)
        monkeypatch.setenv("SEARCH_PROVIDER", "apify")
        assert isinstance(get_search_backend(), ApifyBackend)
        monkeypatch.setenv("SEARCH_PROVIDER", "claude")
        assert isinstance(get_search_backend(), ClaudeWebSearchBackend)

    def test_unknown_provider_falls_back_to_none(self, monkeypatch):
        monkeypatch.setenv("SEARCH_PROVIDER", "bing")
        assert get_search_backend() is None


class TestParsers:
    def test_parse_brave(self):
        data = {"web": {"results": [
            {"url": "https://cs.example.edu/", "title": "CS  Program", "description": "Great   CS"},
            {"title": "no url"},  # dropped
        ]}}
        results = _parse_brave(data)
        assert len(results) == 1
        assert results[0].url == "https://cs.example.edu/"
        assert results[0].title == "CS Program"  # whitespace collapsed
        assert results[0].snippet == "Great CS"

    def test_parse_tavily(self):
        data = {"results": [
            {"url": "https://eng.example.edu/", "title": "Engineering", "content": "Degree requirements"},
            {"content": "no url"},  # dropped
        ]}
        results = _parse_tavily(data)
        assert len(results) == 1
        assert results[0].url == "https://eng.example.edu/"
        assert results[0].snippet == "Degree requirements"

    def test_parse_apify_organic_and_flat(self):
        # Google-SERP shape (organicResults) ...
        serp = [{"organicResults": [
            {"url": "https://cs.example.edu/", "title": "CS  Program", "description": "Great   CS"},
            {"title": "no url"},  # dropped
        ]}]
        r = _parse_apify(serp)
        assert len(r) == 1 and r[0].url == "https://cs.example.edu/" and r[0].title == "CS Program"
        # ... and flat item shape
        flat = [{"url": "https://eng.example.edu/", "title": "Eng", "description": "Reqs"}]
        assert _parse_apify(flat)[0].snippet == "Reqs"

    def test_parse_claude_web_search(self):
        message = SimpleNamespace(content=[
            SimpleNamespace(type="text", text="Here are results"),
            SimpleNamespace(type="web_search_tool_result", content=[
                SimpleNamespace(type="web_search_result", url="https://cs.example.edu/ba", title="CS BA"),
                SimpleNamespace(type="web_search_result", url="https://cs.example.edu/ba", title="dup"),  # deduped
                SimpleNamespace(type="other", url="https://x.edu/"),  # ignored
            ]),
            SimpleNamespace(type="web_search_tool_result", content={"type": "error"}),  # error object ignored
        ])
        results = _parse_claude_web_search(message)
        assert len(results) == 1
        assert results[0].url == "https://cs.example.edu/ba"
        assert results[0].title == "CS BA"


class TestClaudeBackendMock:
    async def test_mock_returns_edu_results(self, monkeypatch):
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        results = await ClaudeWebSearchBackend().search("Computer Science")
        assert results
        assert all(r.url.endswith((".edu", "-science")) or ".edu/" in r.url for r in results)
        assert any("computer science" in r.snippet.lower() for r in results)


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestEndToEndProvider:
    async def test_course_search_uses_claude_backend(self, monkeypatch):
        monkeypatch.setenv("COURSE_SEARCH_MODE", "live")
        monkeypatch.setenv("SEARCH_PROVIDER", "claude")
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        program_store._service.configure_live_only()

        async with await _client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "computer science", "city": "Berkeley", "state": "CA",
            })

        assert r.status_code == 200
        programs = [
            ranked["program"]
            for tier in r.json()["tiers"]
            for ranked in tier["programs"]
        ]
        assert programs, "expected live results discovered via the Claude web_search backend"
        assert programs[0]["program_id"].startswith("live-")
