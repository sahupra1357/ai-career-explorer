"""Dynamic course search package."""

from .service import CourseSearchService
from .sources import StaticProgramRepository

__all__ = ["CourseSearchService", "StaticProgramRepository"]
