"""Ranking and tier grouping for course search candidates."""
from __future__ import annotations

import math

from rapidfuzz import fuzz

from app.models import CollegeProgram, ProgramTier, RankedProgram

from .models import ProgramCandidate, SearchPlan


# US state land adjacency (postal codes), all 50 + DC. AK and HI have no land neighbors.
NEIGHBORING_STATES: dict[str, set[str]] = {
    "AL": {"FL", "GA", "MS", "TN"},
    "AK": set(),
    "AZ": {"CA", "CO", "NV", "NM", "UT"},
    "AR": {"LA", "MO", "MS", "OK", "TN", "TX"},
    "CA": {"AZ", "NV", "OR"},
    "CO": {"AZ", "KS", "NE", "NM", "OK", "UT", "WY"},
    "CT": {"MA", "NY", "RI"},
    "DC": {"MD", "VA"},
    "DE": {"MD", "NJ", "PA"},
    "FL": {"AL", "GA"},
    "GA": {"AL", "FL", "NC", "SC", "TN"},
    "HI": set(),
    "ID": {"MT", "NV", "OR", "UT", "WA", "WY"},
    "IL": {"IA", "IN", "KY", "MO", "WI"},
    "IN": {"IL", "KY", "MI", "OH"},
    "IA": {"IL", "MN", "MO", "NE", "SD", "WI"},
    "KS": {"CO", "MO", "NE", "OK"},
    "KY": {"IL", "IN", "MO", "OH", "TN", "VA", "WV"},
    "LA": {"AR", "MS", "TX"},
    "ME": {"NH"},
    "MD": {"DC", "DE", "PA", "VA", "WV"},
    "MA": {"CT", "NH", "NY", "RI", "VT"},
    "MI": {"IN", "OH", "WI"},
    "MN": {"IA", "ND", "SD", "WI"},
    "MS": {"AL", "AR", "LA", "TN"},
    "MO": {"AR", "IA", "IL", "KS", "KY", "NE", "OK", "TN"},
    "MT": {"ID", "ND", "SD", "WY"},
    "NE": {"CO", "IA", "KS", "MO", "SD", "WY"},
    "NV": {"AZ", "CA", "ID", "OR", "UT"},
    "NH": {"MA", "ME", "VT"},
    "NJ": {"DE", "NY", "PA"},
    "NM": {"AZ", "CO", "OK", "TX", "UT"},
    "NY": {"CT", "MA", "NJ", "PA", "VT"},
    "NC": {"GA", "SC", "TN", "VA"},
    "ND": {"MN", "MT", "SD"},
    "OH": {"IN", "KY", "MI", "PA", "WV"},
    "OK": {"AR", "CO", "KS", "MO", "NM", "TX"},
    "OR": {"CA", "ID", "NV", "WA"},
    "PA": {"DE", "MD", "NJ", "NY", "OH", "WV"},
    "RI": {"CT", "MA"},
    "SC": {"GA", "NC"},
    "SD": {"IA", "MN", "MT", "ND", "NE", "WY"},
    "TN": {"AL", "AR", "GA", "KY", "MO", "MS", "NC", "VA"},
    "TX": {"AR", "LA", "NM", "OK"},
    "UT": {"AZ", "CO", "ID", "NM", "NV", "WY"},
    "VT": {"MA", "NH", "NY"},
    "VA": {"DC", "KY", "MD", "NC", "TN", "WV"},
    "WA": {"ID", "OR"},
    "WV": {"KY", "MD", "OH", "PA", "VA"},
    "WI": {"IA", "IL", "MI", "MN"},
    "WY": {"CO", "ID", "MT", "NE", "SD", "UT"},
}


def build_ranked_tiers(candidates: list[ProgramCandidate], plan: SearchPlan) -> list[ProgramTier]:
    programs = _dedupe_candidates(candidates)
    user_point = _infer_user_point(plan.city, plan.user_state, programs)
    home_state = plan.home_state or plan.state

    used_ids: set[str] = set()
    nearby = _ranked(
        [
            p for p in programs
            if user_point and _distance(user_point[0], user_point[1], p.lat, p.lon) <= plan.nearby_radius_miles
        ],
        plan.normalized_query,
        user_point,
        f"within roughly {plan.nearby_radius_miles} miles of your location",
        used_ids,
        3,
        sort_by_distance=True,
    )
    home = _ranked(
        [p for p in programs if home_state and p.state == home_state],
        plan.normalized_query,
        user_point,
        f"in your home state ({home_state})",
        used_ids,
        3,
        sort_by_distance=True,
    )
    neighbors = NEIGHBORING_STATES.get(home_state or "", set())
    nearby_states = _ranked(
        [p for p in programs if p.state in neighbors],
        plan.normalized_query,
        user_point,
        "in a nearby home state",
        used_ids,
        3,
        sort_by_distance=True,
    )
    best = _ranked(
        programs,
        plan.normalized_query,
        user_point,
        "nationally strong fit for this course",
        used_ids,
        4,
    )

    return [
        ProgramTier(tier="nearby", title="Nearby colleges", programs=nearby),
        ProgramTier(tier="home_state", title="In your home state", programs=home),
        ProgramTier(tier="nearby_home_states", title="Nearby home states", programs=nearby_states),
        ProgramTier(tier="best_usa", title="Best in the USA", programs=best),
    ]


def _dedupe_candidates(candidates: list[ProgramCandidate]) -> list[CollegeProgram]:
    by_id: dict[str, ProgramCandidate] = {}
    for candidate in candidates:
        existing = by_id.get(candidate.program.program_id)
        if existing is None or candidate.confidence > existing.confidence:
            by_id[candidate.program.program_id] = candidate
    return [candidate.program for candidate in by_id.values()]


def _ranked(
    programs: list[CollegeProgram],
    query: str,
    user_point: tuple[float, float] | None,
    reason: str,
    used_ids: set[str],
    limit: int,
    sort_by_distance: bool = False,
) -> list[RankedProgram]:
    ranked: list[tuple[float, float | None, RankedProgram]] = []
    for program in programs:
        if program.program_id in used_ids:
            continue
        distance = _distance(user_point[0], user_point[1], program.lat, program.lon) if user_point else None
        distance_bonus = max(0, 30 - (distance or 9999) / 20) if distance is not None else 0
        score = program.ranking_score + distance_bonus + fuzz.token_set_ratio(query, program.course_name) / 10
        ranked.append((
            score,
            distance,
            RankedProgram(
                program=program,
                distance_miles=round(distance, 1) if distance is not None else None,
                match_reason=reason,
            ),
        ))
    if sort_by_distance:
        # Geographic tiers: closest first; unknown-distance programs last, score as tiebreak.
        ranked.sort(key=lambda row: (row[1] is None, row[1] if row[1] is not None else 0.0, -row[0]))
    else:
        # National tier: best composite fit first.
        ranked.sort(key=lambda row: -row[0])
    results = [item for _, _, item in ranked][:limit]
    for result in results:
        used_ids.add(result.program.program_id)
    return results


def _infer_user_point(
    city: str | None,
    state: str | None,
    programs: list[CollegeProgram],
) -> tuple[float, float] | None:
    if not state:
        return None
    if city:
        city_lower = city.lower()
        for program in programs:
            if program.state == state and program.city.lower() == city_lower:
                return program.lat, program.lon

    same_state = [p for p in programs if p.state == state]
    if not same_state:
        return None
    return (
        sum(p.lat for p in same_state) / len(same_state),
        sum(p.lon for p in same_state) / len(same_state),
    )


def _distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
