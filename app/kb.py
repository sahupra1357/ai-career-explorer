"""Knowledge base loader — reads fields.yaml once at startup into an in-memory dict."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError
from rapidfuzz import process as fuzz_process

from .models import FieldEntry


class FieldStore:
    def __init__(self) -> None:
        self._fields: dict[str, FieldEntry] = {}

    def load(self, path: str | Path) -> None:
        """Load and validate all field entries. Raises RuntimeError on any schema error."""
        raw = yaml.safe_load(Path(path).read_text()) or {}
        entries = raw.get("fields") or []
        loaded: dict[str, FieldEntry] = {}
        for entry in entries:
            fid = entry.get("field_id", "?")
            try:
                field = FieldEntry(**entry)
            except ValidationError as e:
                raise RuntimeError(
                    f"KB validation failed for field '{fid}': {e}"
                ) from e
            loaded[field.field_id] = field
        self._fields = loaded

    def all(self) -> list[FieldEntry]:
        return list(self._fields.values())

    def list(self) -> list[dict]:
        return [{"field_id": f.field_id, "name": f.name} for f in self._fields.values()]

    def get(self, field_id: str) -> FieldEntry | None:
        return self._fields.get(field_id)

    def fuzzy_candidates(self, query: str, cutoff: int = 70) -> list[str]:
        """Return up to 3 known field_ids that fuzzy-match the query. Never auto-selects."""
        if not self._fields:
            return []
        matches = fuzz_process.extract(
            query, list(self._fields.keys()), limit=3, score_cutoff=cutoff
        )
        return [m[0] for m in matches]

    def __len__(self) -> int:
        return len(self._fields)


# Singleton — populated during app lifespan startup
store = FieldStore()
