"""Tests for Pydantic models and normalize_slug."""

import pytest
from pydantic import ValidationError

from app.models import (
    CompareRequest,
    FieldEntry,
    PersonalityFit,
    normalize_slug,
)


# ── normalize_slug ─────────────────────────────────────────────────────────────

class TestNormalizeSlug:
    def test_lowercase(self):
        assert normalize_slug("Computer Science") == "computer-science"

    def test_underscores_to_hyphens(self):
        assert normalize_slug("computer_science") == "computer-science"

    def test_multiple_spaces(self):
        assert normalize_slug("computer  science") == "computer-science"

    def test_leading_trailing_whitespace(self):
        assert normalize_slug("  biomedical engineering  ") == "biomedical-engineering"

    def test_already_slugified(self):
        assert normalize_slug("data-science") == "data-science"

    def test_mixed_separators(self):
        assert normalize_slug("neural-engineering science") == "neural-engineering-science"


# ── CompareRequest ─────────────────────────────────────────────────────────────

class TestCompareRequest:
    def test_valid_two_fields(self):
        r = CompareRequest(fields=["computer-science", "data-science"])
        assert r.fields == ["computer-science", "data-science"]

    def test_valid_three_fields(self):
        r = CompareRequest(fields=["cs", "bio", "math"])
        assert len(r.fields) == 3

    def test_normalizes_display_names(self):
        r = CompareRequest(fields=["Computer Science", "Data Science"])
        assert r.fields == ["computer-science", "data-science"]

    def test_normalizes_underscores(self):
        r = CompareRequest(fields=["computer_science", "data_science"])
        assert r.fields == ["computer-science", "data-science"]

    def test_rejects_single_field(self):
        with pytest.raises(ValidationError):
            CompareRequest(fields=["computer-science"])

    def test_rejects_four_fields(self):
        with pytest.raises(ValidationError):
            CompareRequest(fields=["a", "b", "c", "d"])

    def test_rejects_empty_list(self):
        with pytest.raises(ValidationError):
            CompareRequest(fields=[])

    def test_rejects_duplicate_fields(self):
        with pytest.raises(ValidationError, match="unique"):
            CompareRequest(fields=["computer-science", "computer-science"])

    def test_rejects_duplicates_after_normalisation(self):
        # "Computer Science" and "computer-science" are the same slug
        with pytest.raises(ValidationError, match="unique"):
            CompareRequest(fields=["Computer Science", "computer-science"])

    def test_rejects_field_name_over_100_chars(self):
        long = "a" * 101
        with pytest.raises(ValidationError, match="too long"):
            CompareRequest(fields=[long, "b"])


# ── PersonalityFit intensity bounds ───────────────────────────────────────────

class TestPersonalityFit:
    def _valid(self, **overrides) -> dict:
        base = {
            "math_intensity": 3,
            "lab_intensity": 3,
            "coding_intensity": 3,
            "people_facing": 3,
            "fit_description": "A great fit.",
        }
        return {**base, **overrides}

    def test_valid_intensities(self):
        pf = PersonalityFit(**self._valid())
        assert pf.math_intensity == 3

    def test_rejects_zero_intensity(self):
        with pytest.raises(ValidationError):
            PersonalityFit(**self._valid(math_intensity=0))

    def test_rejects_six_intensity(self):
        with pytest.raises(ValidationError):
            PersonalityFit(**self._valid(coding_intensity=6))

    def test_boundary_one(self):
        pf = PersonalityFit(**self._valid(lab_intensity=1))
        assert pf.lab_intensity == 1

    def test_boundary_five(self):
        pf = PersonalityFit(**self._valid(people_facing=5))
        assert pf.people_facing == 5


# ── FieldEntry sub_areas min/max ──────────────────────────────────────────────

class TestFieldEntry:
    def _base(self) -> dict:
        return {
            "schema_version": "1.0",
            "field_id": "test-field",
            "name": "Test Field",
            "plain_english": "A test field.",
            "undergrad_path": {
                "high_school_prereqs": ["Math"],
                "common_majors": ["Test Major"],
                "key_courses": ["Course 101"],
            },
            "career_outcomes": {
                "common_roles": ["Role A", "Role B"],
                "salary_range": {
                    "min": 50000, "max": 100000,
                    "currency": "USD", "source_year": 2024,
                    "region": "US national median",
                },
                "outlook": "5% growth (BLS)",
                "outlook_pct": 5.0,
            },
            "personality_fit": {
                "math_intensity": 3, "lab_intensity": 3,
                "coding_intensity": 3, "people_facing": 3,
                "fit_description": "A good fit.",
            },
            "follow_on_questions": ["Q1?", "Q2?", "Q3?"],
        }

    def _sub_areas(self, n: int) -> list[dict]:
        return [{"name": f"Area {i}", "description": f"Desc {i}."} for i in range(1, n + 1)]

    def test_valid_three_sub_areas(self):
        entry = FieldEntry(**{**self._base(), "sub_areas": self._sub_areas(3)})
        assert len(entry.sub_areas) == 3

    def test_valid_five_sub_areas(self):
        entry = FieldEntry(**{**self._base(), "sub_areas": self._sub_areas(5)})
        assert len(entry.sub_areas) == 5

    def test_rejects_two_sub_areas(self):
        with pytest.raises(ValidationError):
            FieldEntry(**{**self._base(), "sub_areas": self._sub_areas(2)})

    def test_rejects_six_sub_areas(self):
        with pytest.raises(ValidationError):
            FieldEntry(**{**self._base(), "sub_areas": self._sub_areas(6)})

    def test_rejects_two_follow_on_questions(self):
        with pytest.raises(ValidationError):
            FieldEntry(**{**self._base(), "sub_areas": self._sub_areas(3), "follow_on_questions": ["Q1?", "Q2?"]})

    def test_adjacent_fields_defaults_to_empty(self):
        entry = FieldEntry(**{**self._base(), "sub_areas": self._sub_areas(3)})
        assert entry.adjacent_fields == []
