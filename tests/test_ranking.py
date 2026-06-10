"""Unit tests for course-search ranking and tier ordering.

These call build_ranked_tiers() directly, so they don't touch the agent/API
mock stack — they isolate the ranking logic.
"""
from app.course_search.models import ProgramCandidate, SearchPlan
from app.course_search.ranking import build_ranked_tiers
from app.models import CollegeProgram, ProgramFees, ProgramSource, SemesterPlan


def make_program(
    program_id: str,
    college_name: str,
    city: str,
    state: str,
    lat: float,
    lon: float,
    ranking_score: int,
) -> CollegeProgram:
    return CollegeProgram(
        program_id=program_id,
        course_name="Computer Science",
        aliases=["cs"],
        college_name=college_name,
        city=city,
        state=state,
        lat=lat,
        lon=lon,
        ranking_score=ranking_score,
        degree="BS Computer Science",
        overview="A computing program.",
        curriculum_summary="Programming, math, systems, algorithms.",
        semester_plan=[SemesterPlan(term="Year 1", focus="Foundation", courses=["Programming"])],
        required_papers=["Transcript"],
        admission_factors=["Math rigor"],
        fees=ProgramFees(notes="Confirm costs.", source_url="https://example.edu/costs"),
        decision_factors=["Strong program"],
        sources=[ProgramSource(label="Program page", url="https://example.edu/cs")],
    )


def candidate(program: CollegeProgram) -> ProgramCandidate:
    return ProgramCandidate(program=program, provider="static_fallback", confidence=1.0)


def _tier(tiers, name):
    return next(t for t in tiers if t.tier == name)


class TestNearbyTierDistanceOrdering:
    """Reproduces the Philadelphia / Computer Science bug: closer colleges must rank first,
    even when a farther college has a higher institutional ranking_score."""

    def _plan(self) -> SearchPlan:
        return SearchPlan(
            normalized_query="computer science",
            city="Philadelphia",
            state="PA",
            home_state="PA",
            user_state="PA",
        )

    def _programs(self):
        # ranking_score deliberately INVERTED vs. distance: the farthest school is the
        # most prestigious, which is exactly what used to win under composite scoring.
        upenn = make_program("upenn-cs", "University of Pennsylvania", "Philadelphia", "PA", 39.95, -75.19, 90)
        princeton = make_program("princeton-cs", "Princeton University", "Princeton", "NJ", 40.34, -74.65, 95)
        navy = make_program("navy-cs", "United States Naval Academy", "Annapolis", "MD", 38.98, -76.48, 70)
        return upenn, princeton, navy

    def test_nearby_tier_sorted_by_distance_not_prestige(self):
        upenn, princeton, navy = self._programs()
        tiers = build_ranked_tiers(
            [candidate(princeton), candidate(navy), candidate(upenn)],  # unsorted input
            self._plan(),
        )
        nearby = _tier(tiers, "nearby")
        order = [r.program.program_id for r in nearby.programs]
        assert order == ["upenn-cs", "princeton-cs", "navy-cs"]

    def test_distances_are_monotonically_increasing(self):
        upenn, princeton, navy = self._programs()
        tiers = build_ranked_tiers(
            [candidate(navy), candidate(upenn), candidate(princeton)],
            self._plan(),
        )
        nearby = _tier(tiers, "nearby")
        distances = [r.distance_miles for r in nearby.programs]
        assert distances == sorted(distances)
        # User is co-located with UPenn (matched city/state), so its distance is ~0.
        assert distances[0] < 1.0

    def test_national_tier_still_prefers_prestige(self):
        """Best-in-USA tier is not geographic — it should keep composite-score ordering,
        so the highest ranking_score program leads."""
        upenn, princeton, navy = self._programs()
        far_elite = make_program("mit-cs", "MIT", "Cambridge", "MA", 42.36, -71.09, 100)
        tiers = build_ranked_tiers(
            [candidate(upenn), candidate(princeton), candidate(navy), candidate(far_elite)],
            self._plan(),
        )
        best = _tier(tiers, "best_usa")
        assert best.programs, "national tier should not be empty"
        assert best.programs[0].program.ranking_score == 100
