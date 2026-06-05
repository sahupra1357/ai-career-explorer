"""Course search orchestration."""
from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from app.models import CourseSearchRequest, CourseSearchResponse

from .discovery import (
    OfficialWebDiscoveryProvider,
    ProgramDiscoveryProvider,
    StaticFallbackDiscoveryProvider,
)
from .cost import CostProvider, StaticCostProvider
from .models import AgentRun, ProgramCandidate
from .planner import build_search_plan
from .ranking import build_ranked_tiers
from .reader import LivePageReaderProvider, ProgramReaderProvider, enrich_shown_programs
from .sources import StaticProgramRepository
from .synthesis import build_guidance

log = structlog.get_logger()


class CourseSearchService:
    """Runs the multi-agent course search pipeline.

    Phase 1 wires the agent boundary and preserves the static fallback. Future
    phases can replace `OfficialWebDiscoveryProvider` without changing the API.
    """

    def __init__(self) -> None:
        self.static_repository = StaticProgramRepository()
        self.providers: list[ProgramDiscoveryProvider] = [OfficialWebDiscoveryProvider()]
        self.reader: ProgramReaderProvider = LivePageReaderProvider()
        self.cost_provider: CostProvider = StaticCostProvider()
        self.uses_static_fallback = False

    def configure_live_only(self) -> None:
        self.providers = [OfficialWebDiscoveryProvider()]
        self.uses_static_fallback = False

    def configure_knowledge_graph(self, store=None) -> None:
        """Serve from the pre-built knowledge graph (instant), with optional live enrich."""
        from .knowledge_graph import KnowledgeGraphDiscoveryProvider

        self.providers = [KnowledgeGraphDiscoveryProvider(store)]
        self.uses_static_fallback = False

    def load_static_programs(self, path: str | Path) -> None:
        self.static_repository.load(path)
        self.providers = [
            OfficialWebDiscoveryProvider(),
            StaticFallbackDiscoveryProvider(self.static_repository),
        ]
        self.uses_static_fallback = True

    def all_static_programs(self):
        return self.static_repository.all()

    async def search(self, body: CourseSearchRequest, request_id: str) -> CourseSearchResponse:
        plan = build_search_plan(body)
        provider_results = await asyncio.gather(
            *(provider.discover(plan) for provider in self.providers),
            return_exceptions=True,
        )

        candidates: list[ProgramCandidate] = []
        agent_runs: list[AgentRun] = []
        for provider, result in zip(self.providers, provider_results):
            if isinstance(result, Exception):
                agent_runs.append(AgentRun(
                    agent=provider.name,
                    status="error",
                    message=str(result),
                    count=0,
                ))
                continue
            found, run = result
            candidates.extend(found)
            agent_runs.append(run)

        candidates, reader_run = await self.reader.read(candidates, plan, request_id)
        agent_runs.append(reader_run)
        candidates, cost_run = await self.cost_provider.enrich_costs(candidates, plan)
        agent_runs.append(cost_run)

        tiers = build_ranked_tiers(candidates, plan)
        # KG-first enrichment: read the official program page for ONLY the shown colleges,
        # in parallel, filling the curriculum gap on demand (opt-in COURSE_READ_PAGES=1).
        tiers = await enrich_shown_programs(tiers, plan, request_id)
        location_used = _location_used(plan.city, plan.user_state)
        guidance = build_guidance(plan, agent_runs)

        log.info(
            "course_search_agents",
            request_id=request_id,
            query=plan.normalized_query,
            agents=[
                {"agent": run.agent, "status": run.status, "count": run.count}
                for run in agent_runs
            ],
        )

        return CourseSearchResponse(
            request_id=request_id,
            query=plan.normalized_query,
            location_used=location_used,
            tiers=tiers,
            guidance=guidance,
        )

    def __len__(self) -> int:
        return len(self.static_repository)


def _location_used(city: str | None, user_state: str | None) -> str:
    location_bits = []
    if city:
        location_bits.append(city)
    if user_state:
        location_bits.append(user_state)
    return ", ".join(location_bits) if location_bits else "No location supplied"
