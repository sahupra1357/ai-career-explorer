"""Internal models for dynamic course search orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.models import CollegeProgram


ProviderName = Literal["static_fallback", "official_web", "knowledge_graph"]


@dataclass(frozen=True)
class SearchPlan:
    normalized_query: str
    city: str | None
    state: str | None
    home_state: str | None
    user_state: str | None
    nearby_radius_miles: int = 150
    degree_level: str = "undergraduate"


@dataclass(frozen=True)
class ProgramCandidate:
    program: CollegeProgram
    provider: ProviderName
    confidence: float
    evidence_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRun:
    agent: str
    status: Literal["ready", "success", "empty", "error"]
    message: str
    count: int = 0


@dataclass(frozen=True)
class SearchContext:
    request_id: str
    plan: SearchPlan
    agent_runs: list[AgentRun]
