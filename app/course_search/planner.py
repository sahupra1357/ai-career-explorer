"""Query planning for course search."""
from __future__ import annotations

from app.models import CourseSearchRequest

from .models import SearchPlan


def build_search_plan(body: CourseSearchRequest) -> SearchPlan:
    query = " ".join(body.course_query.strip().split())
    state = body.state.upper() if body.state else None
    home_state = body.home_state.upper() if body.home_state else None
    return SearchPlan(
        normalized_query=query,
        city=body.city,
        state=state,
        home_state=home_state,
        user_state=state or home_state,
    )
