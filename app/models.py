from __future__ import annotations

import re
from datetime import date, datetime
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


# ── Phase 3: Course finder / college admissions research ─────────────────────

class MoneyAmount(BaseModel):
    amount: int
    currency: Literal["USD"] = "USD"
    label: str


class ProgramSource(BaseModel):
    label: str
    url: str


# Provenance per DESIGN.md §6 — every aggregated claim can point back to a real source.
ClaimType = Literal[
    "identity", "admissions", "curriculum", "fees", "aid",
    "housing", "outcomes", "ranking", "general",
]

# Honest-gap markers per DESIGN.md §6 (data_quality_flags).
DataQualityFlag = Literal[
    "missing_curriculum_source",
    "missing_fee_source",
    "fee_estimate_only",
    "catalog_page_not_found",
    "unofficial_ranking_source",
    "program_name_ambiguous",
    "requires_manual_review",
]


class ProgramEvidence(BaseModel):
    claim_type: ClaimType
    claim: str
    source_url: str
    source_label: str
    as_of: date
    confidence: Literal["high", "medium", "low"] = "medium"


class RankingLink(BaseModel):
    """A pointer to verify a college's ranking on an external site.

    We do NOT reproduce proprietary ranking values (e.g. U.S. News numbers) — only a link
    the user can open to check. Keeps us compliant with those sites' terms.
    """
    name: str
    url: str
    note: str = "Ranking value not reproduced — open to verify on the source."


class LicensedRanking(BaseModel):
    """An actual ranking *value* from a licensed provider (e.g. U.S. News).

    Only ever populated when RANKINGS_LICENSED=1 — i.e. the operator holds a data licence.
    Off by default, so no proprietary rank value is emitted without a licence.
    """
    provider: str
    rank: int
    list_name: Optional[str] = None
    year: int
    source_url: Optional[str] = None


class SemesterPlan(BaseModel):
    term: str
    focus: str
    courses: list[str]


class ProgramFees(BaseModel):
    in_state_tuition: Optional[MoneyAmount] = None
    out_of_state_tuition: Optional[MoneyAmount] = None
    mandatory_fees: Optional[MoneyAmount] = None
    notes: str
    source_url: str


class CollegeProgram(BaseModel):
    program_id: str
    course_name: str
    aliases: list[str] = []
    college_name: str
    city: str
    state: str = Field(min_length=2, max_length=2)
    lat: float
    lon: float
    ranking_score: int = Field(ge=1, le=100)
    degree: str
    delivery: str = "On campus"
    overview: str
    curriculum_summary: str
    semester_plan: list[SemesterPlan]
    required_papers: list[str]
    admission_factors: list[str]
    fees: ProgramFees
    decision_factors: list[str]
    sources: list[ProgramSource]
    # Provenance (additive, optional) — populated by the Phase 3 page reader.
    evidence: list[ProgramEvidence] = []
    data_quality_flags: list[DataQualityFlag] = []
    last_checked_at: Optional[datetime] = None
    # Ranking: verify-links only (no proprietary values copied) + see ranking_score
    # for our transparent composite from open Scorecard outcomes.
    rankings: list[RankingLink] = []
    # Carnegie Classification (free, official prestige tier) — shown when available.
    carnegie_classification: Optional[str] = None
    # Licensed provider ranks (e.g. U.S. News) — populated ONLY when RANKINGS_LICENSED=1.
    licensed_rankings: list[LicensedRanking] = []


class CourseSearchRequest(BaseModel):
    course_query: str = Field(min_length=2, max_length=120)
    city: Optional[str] = Field(default=None, max_length=80)
    state: Optional[str] = Field(default=None, max_length=2)
    home_state: Optional[str] = Field(default=None, max_length=2)

    @field_validator("course_query")
    @classmethod
    def clean_course_query(cls, v: str) -> str:
        return v.strip()

    @field_validator("state", "home_state")
    @classmethod
    def normalize_state(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        return v.strip().upper()

    @field_validator("city")
    @classmethod
    def clean_city(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


class RankedProgram(BaseModel):
    program: CollegeProgram
    distance_miles: Optional[float] = None
    match_reason: str


class ProgramTier(BaseModel):
    tier: Literal["nearby", "home_state", "nearby_home_states", "best_usa"]
    title: str
    programs: list[RankedProgram]


class CourseSearchResponse(BaseModel):
    request_id: str
    query: str
    location_used: str
    tiers: list[ProgramTier]
    guidance: list[str]
