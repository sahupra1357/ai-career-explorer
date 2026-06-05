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

    @staticmethod
    def _mode() -> str:
        # Default: the LangGraph multi-agent workflow (orchestrator + per-college subagents,
        # seeded by the knowledge graph). Other modes use the deterministic service.
        return os.getenv("COURSE_SEARCH_MODE", "agent")

    def load(self, path: str | Path) -> None:
        mode = self._mode()
        if mode == "kg":
            self._service.configure_knowledge_graph()
            return
        if mode == "live":
            self._service.configure_live_only()
            return
        # agent + fallback keep the curated static repo loaded (the agent path queries the
        # KG directly at request time; static is the deterministic fallback + /health count).
        self._service.load_static_programs(path)

    def all(self):
        return self._service.all_static_programs()

    async def search(self, body: CourseSearchRequest, request_id: str) -> CourseSearchResponse:
        if self._mode() == "agent":
            from app.course_search.agent_graph import run_agent_search
            return await run_agent_search(body, request_id)
        return await self._service.search(body, request_id)

    def __len__(self) -> int:
        return len(self._service)


program_store = ProgramStore()
