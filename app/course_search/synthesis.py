"""Counselor-facing synthesis for course search responses."""
from __future__ import annotations

from .cip_aliases import resolve_course
from .models import AgentRun, SearchPlan


def build_guidance(plan: SearchPlan, agent_runs: list[AgentRun]) -> list[str]:
    guidance: list[str] = []
    resolved = resolve_course(plan.normalized_query)
    if resolved:
        guidance.append(
            f"Interpreted “{plan.normalized_query}” as {resolved.name} "
            f"(CIP {', '.join(resolved.cips)})."
        )
    guidance += [
        "Use official curriculum links to verify required courses, because departments can revise degree maps.",
        "Compare net price, not only published tuition; aid can change the practical cost dramatically.",
        "For selective majors, check whether admission is direct-to-major or requires an internal application after enrollment.",
    ]
    official_run = next((run for run in agent_runs if run.agent == "official_web"), None)
    if official_run and official_run.status in {"ready", "empty", "error"}:
        fallback_run = next((run for run in agent_runs if run.agent == "static_fallback"), None)
        if fallback_run:
            guidance.append(
                "Live official-site discovery ran first; curated fallback records may fill gaps when official pages are sparse."
            )
        else:
            guidance.append(
                "Live official-site discovery is selected without curated fallback records. Try a more specific course or state if results are sparse."
            )
    if not plan.city:
        guidance.append("Add a city or ZIP code later for more accurate nearby-college distance ranking.")
    return guidance
