from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def normalize_slug(s: str) -> str:
    """'Biomedical Engineering' → 'biomedical-engineering'"""
    return re.sub(r"[-\s_]+", "-", s.strip().lower())


# ── Knowledge base models ──────────────────────────────────────────────────────

class SubArea(BaseModel):
    name: str
    description: str


class UndergradPath(BaseModel):
    high_school_prereqs: list[str]
    common_majors: list[str]
    key_courses: list[str]


class SalaryRange(BaseModel):
    min: int
    max: int
    currency: Literal["USD"] = "USD"
    source_year: int
    region: str = "US national median"


class CareerOutcomes(BaseModel):
    common_roles: list[str]
    salary_range: SalaryRange
    outlook: str
    outlook_pct: Optional[float] = None


class PersonalityFit(BaseModel):
    math_intensity: int = Field(ge=1, le=5)
    lab_intensity: int = Field(ge=1, le=5)
    coding_intensity: int = Field(ge=1, le=5)
    people_facing: int = Field(ge=1, le=5)
    fit_description: str


class FieldEntry(BaseModel):
    schema_version: str = "1.0"
    field_id: str
    name: str
    plain_english: str
    sub_areas: list[SubArea] = Field(min_length=3, max_length=5)
    undergrad_path: UndergradPath
    career_outcomes: CareerOutcomes
    personality_fit: PersonalityFit
    adjacent_fields: list[str] = []
    follow_on_questions: list[str] = Field(min_length=3, max_length=5)


# ── API request / response models ─────────────────────────────────────────────

class CompareRequest(BaseModel):
    fields: list[str] = Field(min_length=2, max_length=3)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, v: list[str]) -> list[str]:
        normalized = [normalize_slug(f) for f in v]
        if len(set(normalized)) < len(normalized):
            raise ValueError("fields must be unique")
        for f in normalized:
            if len(f) > 100:
                raise ValueError(f"field name too long: {f!r}")
        return normalized


class FieldSummary(BaseModel):
    field_id: str
    name: str


class CompareSuccess(BaseModel):
    request_id: str
    fields: list[FieldEntry]
    comparison_fields_used: list[str]
    comparison_summary: Optional[str]
    summary_status: Literal["ready", "error"]


class PartialNotFound(BaseModel):
    request_id: str
    error: Literal["partial_not_found"] = "partial_not_found"
    found: list[str]
    not_found: list[str]
    suggestions: dict[str, list[str]]


class NotFound(BaseModel):
    request_id: str
    error: Literal["not_found"] = "not_found"
    message: str
    suggestions: list[str]


# ── Phase 2: Explore mode ──────────────────────────────────────────────────────

class ExploreRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()


class RecommendedField(BaseModel):
    field_id: str
    name: str
    reason: str
    score: Optional[float] = None


class ExploreResponse(BaseModel):
    session_id: str
    reply: str
    status: Literal["intake", "clarifying", "complete"]
    recommended_fields: list[RecommendedField] = []


# ── Phase 2: Direct (deep dive) mode ──────────────────────────────────────────

class DirectRequest(BaseModel):
    field_id: str = Field(min_length=1, max_length=100)

    @field_validator("field_id")
    @classmethod
    def normalize_field_id(cls, v: str) -> str:
        return normalize_slug(v)


class DeepDiveSection(BaseModel):
    title: str
    content: str


class DirectResponse(BaseModel):
    field_id: str
    name: str
    sections: list[DeepDiveSection]
