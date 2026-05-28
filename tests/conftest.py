"""Shared pytest fixtures."""

import os
import pytest


# Ensure MOCK_CLAUDE and a dummy API key are set for the entire test run
# so the app lifespan passes its startup check without hitting Claude.
os.environ.setdefault("MOCK_CLAUDE", "1")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi's in-memory counter before every test to prevent bleed-over."""
    from app.main import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield


def make_field(
    field_id: str = "computer-science",
    name: str = "Computer Science",
    *,
    math_intensity: int = 4,
    lab_intensity: int = 1,
    coding_intensity: int = 5,
    people_facing: int = 2,
) -> dict:
    """Return a minimal valid FieldEntry dict."""
    return {
        "schema_version": "1.0",
        "field_id": field_id,
        "name": name,
        "plain_english": f"{name} is a great field.",
        "sub_areas": [
            {"name": "Area One", "description": "First sub-area."},
            {"name": "Area Two", "description": "Second sub-area."},
            {"name": "Area Three", "description": "Third sub-area."},
        ],
        "undergrad_path": {
            "high_school_prereqs": ["Calculus", "Physics"],
            "common_majors": [name],
            "key_courses": ["Intro Course", "Advanced Course"],
        },
        "career_outcomes": {
            "common_roles": ["Role A", "Role B", "Role C"],
            "salary_range": {
                "min": 70000,
                "max": 130000,
                "currency": "USD",
                "source_year": 2024,
                "region": "US national median",
            },
            "outlook": "10% growth 2022-2032 (BLS)",
            "outlook_pct": 10.0,
        },
        "personality_fit": {
            "math_intensity": math_intensity,
            "lab_intensity": lab_intensity,
            "coding_intensity": coding_intensity,
            "people_facing": people_facing,
            "fit_description": f"People who love {name} thrive here.",
        },
        "adjacent_fields": [],
        "follow_on_questions": [
            "What does a day look like?",
            "Do I need grad school?",
            "What industries hire here?",
        ],
    }


@pytest.fixture
def cs_field() -> dict:
    return make_field("computer-science", "Computer Science")


@pytest.fixture
def bio_field() -> dict:
    return make_field("biomedical-engineering", "Biomedical Engineering", lab_intensity=4)


@pytest.fixture
def math_field() -> dict:
    return make_field("applied-mathematics", "Applied Mathematics", math_intensity=5)
