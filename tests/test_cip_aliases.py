"""Tests for course-name → CIP resolution."""

from app.course_search.cip_aliases import resolve_course


class TestResolveCourse:
    def test_exact_name(self):
        r = resolve_course("Computer Science")
        assert r is not None and r.name == "Computer Science" and "11.07" in r.cips

    def test_abbreviation(self):
        r = resolve_course("CS")
        assert r is not None and r.name == "Computer Science"

    def test_short_abbrev_exact_only(self):
        assert resolve_course("ee").name == "Electrical Engineering"
        assert resolve_course("rn").name == "Nursing"

    def test_synonym(self):
        assert resolve_course("data analytics").name == "Data Science"
        assert resolve_course("psych").name == "Psychology"

    def test_fuzzy_and_punctuation(self):
        assert resolve_course("Comp. Sci!").name == "Computer Science"
        assert resolve_course("mechanical eng").name == "Mechanical Engineering"

    def test_unknown_returns_none(self):
        assert resolve_course("underwater basket weaving") is None
        assert resolve_course("") is None
        assert resolve_course("zz") is None  # short + unknown → no false fuzzy hit
