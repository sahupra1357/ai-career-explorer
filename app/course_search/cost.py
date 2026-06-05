"""Cost and aid extraction providers."""
from __future__ import annotations

from typing import Protocol

from .models import AgentRun, ProgramCandidate, SearchPlan


class CostProvider(Protocol):
    name: str

    async def enrich_costs(
        self,
        candidates: list[ProgramCandidate],
        plan: SearchPlan,
    ) -> tuple[list[ProgramCandidate], AgentRun]:
        """Attach or validate tuition and fee details."""


class StaticCostProvider:
    """Phase 1 cost provider using fallback records with source links."""

    name = "static_cost"

    async def enrich_costs(
        self,
        candidates: list[ProgramCandidate],
        plan: SearchPlan,
    ) -> tuple[list[ProgramCandidate], AgentRun]:
        with_costs = [
            candidate for candidate in candidates
            if candidate.program.fees.source_url
        ]
        live_count = sum(1 for candidate in candidates if candidate.provider == "official_web")
        return candidates, AgentRun(
            agent=self.name,
            status="success" if with_costs else "empty",
            message=(
                "Cost amounts are not extracted for live results yet; official source links are attached."
                if live_count else
                "Validated cost source links from structured fallback records."
            ),
            count=len(with_costs),
        )
