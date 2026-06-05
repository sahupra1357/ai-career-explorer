"""College subagent — a genuine tool-using LLM agent that investigates ONE college live.

Given a KG-seeded candidate (real college + baseline facts), the subagent reasons with two
tools — search_web (Tavily/Brave/Apify, no Anthropic tokens) and fetch_page — to find that
college's official program page, read it, and report structured curriculum/admissions
findings. It decides what to search, which page to read, and when it has enough.

Tier-safe: search burns no Anthropic tokens; only the agent's reasoning does. Bounded by
AGENT_MAX_ROUNDS and a module-wide concurrency semaphore so a fan-out of ~10 subagents
doesn't blow a low input-token-per-minute limit. MOCK_CLAUDE=1 short-circuits with a
deterministic result for offline dev/tests.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlparse

import structlog

from app.models import CollegeProgram

from .agent_llm import run_subagent_loop
from .models import SearchPlan
from .reader import (
    MAX_PAGE_CHARS,
    _apply_extraction,
    _fetch_page_text,
    _flag_program,
    _official_domain,
    _search,
)

log = structlog.get_logger()

_SEM: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(int(os.getenv("AGENT_CONCURRENCY", "3")))
    return _SEM


_TOOLS = [
    {
        "name": "search_web",
        "description": "Search the web for this college's program/curriculum pages. "
                       "Returns a list of {title, url}. Prefer the college's own .edu site.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": "Fetch the visible text of a URL — use on an official program/catalog page.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "report",
        "description": "Report your final findings for this college's program. Use ONLY facts "
                       "from pages you read; leave a field empty if the page didn't state it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "program_page_url": {"type": "string", "description": "The official page you used."},
                "degree": {"type": "string"},
                "curriculum_summary": {"type": "string"},
                "semester_plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "term": {"type": "string"},
                            "focus": {"type": "string"},
                            "courses": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "required_papers": {"type": "array", "items": {"type": "string"}},
                "admission_factors": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["program_page_url"],
        },
    },
]

_SYSTEM = """\
You are a college-research subagent. Investigate ONE college's program and report what its \
official pages actually say — never invent facts.

College: {college} ({city}, {state})
Official site domain: {domain}
Program the student wants: {course}

Use search_web to find this college's program / degree-requirements / curriculum page on its \
own domain ({domain}), then fetch_page to read it. If the first page lacks the course list, \
search or fetch another. Within {max_rounds} tool rounds, call `report` with the curriculum \
summary, the course structure (year-by-year if given, else grouped core/elective courses with \
real course codes), required application materials, and admission factors — using only what \
the pages state. If you cannot verify something, leave it out rather than guessing."""


async def investigate_college(program: CollegeProgram, plan: SearchPlan, request_id: str) -> CollegeProgram:
    domain = _official_domain(program)
    if os.getenv("MOCK_LLM") == "1" or os.getenv("MOCK_CLAUDE") == "1":
        return _mock_investigation(program, domain)
    if not domain:
        return program

    async with _semaphore():
        return await _run_agent(program, plan, domain, request_id)


async def _run_agent(program: CollegeProgram, plan: SearchPlan, domain: str, request_id: str) -> CollegeProgram:
    max_rounds = int(os.getenv("AGENT_MAX_ROUNDS", "4"))
    system = _SYSTEM.format(
        college=program.college_name, city=program.city, state=program.state,
        domain=domain, course=program.course_name, max_rounds=max_rounds,
    )

    async def execute(name: str, tool_input: dict) -> str:
        return await _run_tool(name, tool_input, domain)

    report = await run_subagent_loop(
        system,
        f"Investigate {program.college_name} — {program.course_name}.",
        _TOOLS, execute, max_rounds=max_rounds, final_tool="report",
    )

    if not report or not report.get("program_page_url"):
        log.info("subagent_no_report", request_id=request_id, college=program.college_name)
        return _flag_program(program, ["catalog_page_not_found"])

    log.info("subagent_reported", request_id=request_id, college=program.college_name,
             page=report.get("program_page_url"))
    return _apply_extraction(program, report, report["program_page_url"],
                             source_label="Official program page", add_source=True)


async def _run_tool(name: str, tool_input: dict, domain: str) -> str:
    if name == "search_web":
        try:
            results = await _search(tool_input.get("query", ""))
        except Exception as exc:  # noqa: BLE001
            return f"search failed: {exc}"
        on_domain, other = [], []
        for r in results:
            host = urlparse(r.url).netloc.lower().removeprefix("www.")
            (on_domain if host.endswith(domain) else other).append({"title": r.title, "url": r.url})
        ranked = (on_domain + other)[:8]
        return json.dumps(ranked) if ranked else "no results"
    if name == "fetch_page":
        text = await _fetch_page_text(tool_input.get("url", ""))
        return (text or "fetch failed (page unreachable or empty)")[:MAX_PAGE_CHARS]
    if name == "report":
        return "reported"
    return f"unknown tool: {name}"


def _mock_investigation(program: CollegeProgram, domain: str | None) -> CollegeProgram:
    extracted = {
        "curriculum_summary": f"[MOCK agent] {program.course_name} curriculum investigated at {program.college_name}.",
        "semester_plan": [
            {"term": "Core courses", "focus": "Foundations", "courses": ["Intro to " + program.course_name, "Data Structures"]},
        ],
        "required_papers": ["Official transcript", "Application essay"],
        "admission_factors": ["GPA and course rigor"],
    }
    url = f"https://{domain or 'example.edu'}/programs/{program.course_name.lower().replace(' ', '-')}"
    return _apply_extraction(program, extracted, url,
                             source_label="Official program page", add_source=True)
