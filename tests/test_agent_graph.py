"""Tests for the LangGraph multi-agent course search (orchestrator + college subagents)."""

import json

from httpx import ASGITransport, AsyncClient

from app.course_search import subagent
from app.course_search.knowledge_graph import SampleKGStore
from app.course_search.planner import build_search_plan
from app.course_search.search_backends import WebSearchResult
from app.main import app
from app.models import CourseSearchRequest


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Fake OpenAI client for the provider-loop test ───────────────────────────────
class _FakeFn:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments


class _FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id, self.function = id, _FakeFn(name, arguments)


class _FakeMsg:
    def __init__(self, tool_calls, content=None):
        self.tool_calls, self.content = tool_calls, content


class _FakeResp:
    def __init__(self, msg):
        self.choices = [type("C", (), {"message": msg})()]


class _FakeOpenAI:
    scripted: list = []

    def __init__(self, *a, **k):
        idx = {"i": 0}

        async def create(**kwargs):
            msg = _FakeOpenAI.scripted[idx["i"]]
            idx["i"] += 1
            return _FakeResp(msg)

        self.chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(create)})()})()


class TestProviderLoop:
    async def test_openai_loop_runs_tools_then_reports(self, monkeypatch):
        import app.course_search.agent_llm as agent_llm

        _FakeOpenAI.scripted = [
            _FakeMsg([_FakeToolCall("c1", "fetch_page", '{"url": "https://x.edu/cs"}')]),
            _FakeMsg([_FakeToolCall("c2", "report",
                                    '{"program_page_url": "https://x.edu/cs", "curriculum_summary": "Real CS curriculum."}')]),
        ]
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setattr("openai.AsyncOpenAI", _FakeOpenAI)

        calls: list[str] = []

        async def execute(name, tool_input):
            calls.append(name)
            return "page text"

        tools = [
            {"name": "fetch_page", "description": "d", "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}}},
            {"name": "report", "description": "d", "input_schema": {"type": "object", "properties": {"program_page_url": {"type": "string"}}}},
        ]
        report = await agent_llm.run_subagent_loop("sys", "go", tools, execute, max_rounds=4, final_tool="report")
        assert report["program_page_url"] == "https://x.edu/cs"
        assert report["curriculum_summary"] == "Real CS curriculum."
        assert "fetch_page" in calls               # the agent used a tool before reporting

    def test_default_provider_is_openai(self, monkeypatch):
        import app.course_search.agent_llm as agent_llm
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        assert agent_llm.llm_provider() == "openai"


class TestSubagent:
    async def test_mock_investigation_fills_curriculum(self, monkeypatch):
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        plan = build_search_plan(CourseSearchRequest(course_query="Computer Science", state="CA"))
        program = (await SampleKGStore().find_programs(plan))[0]
        enriched = await subagent.investigate_college(program, plan, "t1")
        assert "missing_curriculum_source" not in enriched.data_quality_flags
        assert enriched.semester_plan[0].courses                  # course grid filled
        assert enriched.sources[0].label == "Official program page"

    async def test_search_tool_keeps_on_domain_first(self, monkeypatch):
        async def fake_search(query):
            return [
                WebSearchResult("Other", "https://other.edu/y", "s"),
                WebSearchResult("Penn CS", "https://cs.upenn.edu/x", "s"),
            ]
        monkeypatch.setattr("app.course_search.subagent._search", fake_search)
        out = await subagent._run_tool("search_web", {"query": "q"}, "upenn.edu")
        urls = [r["url"] for r in json.loads(out)]
        assert urls[0] == "https://cs.upenn.edu/x"               # the college's own domain ranks first


class TestAgentMode:
    async def test_agent_graph_end_to_end(self, monkeypatch):
        monkeypatch.setenv("COURSE_SEARCH_MODE", "agent")
        monkeypatch.setenv("KG_BACKEND", "sample")
        monkeypatch.setenv("MOCK_CLAUDE", "1")                   # mock the subagent investigations

        async with await _client() as c:
            r = await c.post("/api/course-search", json={
                "course_query": "Computer Science", "city": "Berkeley",
                "state": "CA", "home_state": "CA",
            })

        assert r.status_code == 200
        body = r.json()
        progs = [rp["program"] for t in body["tiers"] for rp in t["programs"]]
        assert progs, "KG seeded candidate colleges and subagents reported back"
        # Geographic tiering still holds (KG seed → ranked tiers).
        tiers = {t["tier"] for t in body["tiers"]}
        assert {"nearby", "home_state", "nearby_home_states", "best_usa"} == tiers
        # Every shown college was investigated by a subagent (curriculum filled, gap cleared).
        for p in progs:
            assert "missing_curriculum_source" not in p["data_quality_flags"]
            assert "[MOCK agent]" in p["curriculum_summary"]
            assert p["sources"][0]["label"] == "Official program page"
