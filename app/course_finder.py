"""Compatibility facade for the dynamic course search service."""
from __future__ import annotations

import os
from pathlib import Path

from app.course_search import CourseSearchService
from app.models import CourseSearchRequest, CourseSearchResponse


class ProgramStore:
    """Preserves the previous `program_store` API while delegating to Phase 1 orchestration."""

    def __init__(self) -> None:
        self._service = CourseSearchService()

    def load(self, path: str | Path) -> None:
        mode = os.getenv("COURSE_SEARCH_MODE")
        if mode == "kg":
            self._service.configure_knowledge_graph()
            return
        if mode == "live":
            self._service.configure_live_only()
            return
        self._service.load_static_programs(path)

    def all(self):
        return self._service.all_static_programs()

    async def search(self, body: CourseSearchRequest, request_id: str) -> CourseSearchResponse:
        return await self._service.search(body, request_id)

    def __len__(self) -> int:
        return len(self._service)


program_store = ProgramStore()
