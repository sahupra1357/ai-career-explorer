"""LangGraph multi-agent course search.

    START → seed (KG: finite candidate colleges + baseline facts, pre-ranked to the shown set)
          → fan-out: one COLLEGE SUBAGENT per college (parallel)
          → aggregate (re-rank enriched findings into tiers + synthesize guidance) → END

The knowledge graph does the orchestrator's heavy lifting: because the US college set is
finite, the KG hands the agents the *right* colleges (with real coordinates + baseline
Scorecard facts) instantly, so the subagents go straight to investigating — they don't
discover colleges from scratch. Each subagent is a genuine tool-using LLM agent (see
subagent.py).
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.models import CollegeProgram, CourseSearchRequest, CourseSearchResponse, ProgramTier

from .knowledge_graph import get_kg_store
from .models import ProgramCandidate, SearchPlan
from .planner import build_search_plan
from .ranking import build_ranked_tiers
from .subagent import investigate_college
from .synthesis import build_guidance

log = structlog.get_logger()


class AgentState(TypedDict):
    plan: SearchPlan
    request_id: str
    candidates: list[CollegeProgram]                       # KG-seeded, pre-ranked to shown set
    findings: Annotated[list[CollegeProgram], operator.add]  # subagent outputs (parallel reduce)
    tiers: list[ProgramTier]
    guidance: list[str]


def _cand(program: CollegeProgram) -> ProgramCandidate:
    return ProgramCandidate(program=program, provider="knowledge_graph", confidence=0.85)


async def seed_node(state: AgentState) -> dict:
    """Orchestrator seed: ask the KG which colleges to investigate, pre-ranked to the shown set."""
    store = get_kg_store()
    programs = await store.find_programs(state["plan"])
    tiers = build_ranked_tiers([_cand(p) for p in programs], state["plan"])
    shown = [rp.program for tier in tiers for rp in tier.programs]
    log.info("agent_seed", request_id=state["request_id"],
             matched=len(programs), investigating=len(shown))
    return {"candidates": shown}


def route_seed(state: AgentState):
    """Fan out one subagent per shown college (or skip straight to aggregate if none)."""
    if not state["candidates"]:
        return "aggregate"
    return [
        Send("subagent", {"program": p, "plan": state["plan"], "request_id": state["request_id"]})
        for p in state["candidates"]
    ]


async def subagent_node(payload: dict) -> dict:
    enriched = await investigate_college(payload["program"], payload["plan"], payload["request_id"])
    return {"findings": [enriched]}


async def aggregate_node(state: AgentState) -> dict:
    findings = state.get("findings") or state.get("candidates") or []
    tiers = build_ranked_tiers([_cand(p) for p in findings], state["plan"])
    guidance = build_guidance(state["plan"], [])
    return {"tiers": tiers, "guidance": guidance}


def build_agent_graph():
    g = StateGraph(AgentState)
    g.add_node("seed", seed_node)
    g.add_node("subagent", subagent_node)
    g.add_node("aggregate", aggregate_node)
    g.add_edge(START, "seed")
    g.add_conditional_edges("seed", route_seed, ["subagent", "aggregate"])
    g.add_edge("subagent", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


_compiled = None


def get_agent_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_agent_graph()
    return _compiled


def _location_used(plan: SearchPlan) -> str:
    bits = [b for b in (plan.city, plan.user_state) if b]
    return ", ".join(bits) if bits else "No location supplied"


async def run_agent_search(body: CourseSearchRequest, request_id: str) -> CourseSearchResponse:
    plan = build_search_plan(body)
    result = await get_agent_graph().ainvoke({
        "plan": plan, "request_id": request_id,
        "candidates": [], "findings": [], "tiers": [], "guidance": [],
    })
    return CourseSearchResponse(
        request_id=request_id,
        query=plan.normalized_query,
        location_used=_location_used(plan),
        tiers=result["tiers"],
        guidance=result["guidance"],
    )


async def run_agent_search_stream(body: CourseSearchRequest, request_id: str):
    """Yield live progress events as the graph runs, then a final 'done' with the result.

    Events: {phase:'seeded', total} → {phase:'investigating', done, total} per college →
    {phase:'done', result}. Lets the UI show a real "investigating X of N colleges" bar.
    """
    plan = build_search_plan(body)
    total = 0
    done = 0
    final: CourseSearchResponse | None = None

    async for update in get_agent_graph().astream(
        {"plan": plan, "request_id": request_id,
         "candidates": [], "findings": [], "tiers": [], "guidance": []},
        stream_mode="updates",
    ):
        if "seed" in update:
            total = len(update["seed"].get("candidates", []))
            yield {"phase": "seeded", "total": total, "done": 0}
        elif "subagent" in update:
            done += len(update["subagent"].get("findings", []))
            yield {"phase": "investigating", "total": total, "done": done}
        elif "aggregate" in update:
            agg = update["aggregate"]
            final = CourseSearchResponse(
                request_id=request_id, query=plan.normalized_query,
                location_used=_location_used(plan),
                tiers=agg["tiers"], guidance=agg["guidance"],
            )

    if final is None:
        final = CourseSearchResponse(
            request_id=request_id, query=plan.normalized_query,
            location_used=_location_used(plan), tiers=[], guidance=[],
        )
    yield {"phase": "done", "result": final.model_dump(mode="json")}
