"""Program source repositories."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.models import CollegeProgram


class StaticProgramRepository:
    """Loads curated program records used as the current fallback provider."""

    def __init__(self) -> None:
        self._programs: list[CollegeProgram] = []

    def load(self, path: str | Path) -> None:
        raw = yaml.safe_load(Path(path).read_text()) or {}
        loaded: list[CollegeProgram] = []
        for entry in raw.get("programs") or []:
            pid = entry.get("program_id", "?")
            try:
                loaded.append(CollegeProgram(**entry))
            except ValidationError as exc:
                raise RuntimeError(f"Program validation failed for '{pid}': {exc}") from exc
        self._programs = loaded

    def all(self) -> list[CollegeProgram]:
        return list(self._programs)

    def __len__(self) -> int:
        return len(self._programs)
