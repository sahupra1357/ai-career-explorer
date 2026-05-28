"""Tests for the FieldStore knowledge base loader."""

import tempfile
from pathlib import Path

import pytest
import yaml

from app.kb import FieldStore
from tests.conftest import make_field


def write_yaml(fields: list[dict]) -> Path:
    """Write a temp fields.yaml and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    yaml.dump({"fields": fields}, tmp)
    tmp.close()
    return Path(tmp.name)


# ── load() ────────────────────────────────────────────────────────────────────

class TestLoad:
    def test_loads_valid_entry(self):
        path = write_yaml([make_field("cs", "CS")])
        store = FieldStore()
        store.load(path)
        assert len(store) == 1

    def test_loads_multiple_entries(self):
        fields = [make_field("cs", "CS"), make_field("bio", "Bio")]
        path = write_yaml(fields)
        store = FieldStore()
        store.load(path)
        assert len(store) == 2

    def test_empty_fields_list(self):
        path = write_yaml([])
        store = FieldStore()
        store.load(path)
        assert len(store) == 0

    def test_raises_on_invalid_schema(self):
        bad = {"field_id": "bad", "name": "Bad"}  # missing required fields
        path = write_yaml([bad])
        store = FieldStore()
        with pytest.raises(RuntimeError, match="KB validation failed for field 'bad'"):
            store.load(path)

    def test_raises_includes_field_id_in_message(self):
        bad = {**make_field("target-field", "Target"), "sub_areas": []}  # too few sub_areas
        path = write_yaml([bad])
        store = FieldStore()
        with pytest.raises(RuntimeError, match="target-field"):
            store.load(path)

    def test_last_writer_wins_on_duplicate_id(self):
        first = make_field("cs", "Computer Science")
        second = {**make_field("cs", "Computer Science"), "name": "CS (updated)"}
        path = write_yaml([first, second])
        store = FieldStore()
        store.load(path)
        assert store.get("cs").name == "CS (updated)"  # type: ignore[union-attr]


# ── get() ─────────────────────────────────────────────────────────────────────

class TestGet:
    def setup_method(self):
        self.store = FieldStore()
        path = write_yaml([make_field("cs", "Computer Science")])
        self.store.load(path)

    def test_returns_entry_for_known_id(self):
        entry = self.store.get("cs")
        assert entry is not None
        assert entry.name == "Computer Science"

    def test_returns_none_for_unknown_id(self):
        assert self.store.get("unknown-field") is None

    def test_case_sensitive(self):
        assert self.store.get("CS") is None  # slugs are lowercase


# ── list() ───────────────────────────────────────────────────────────────────

class TestList:
    def test_returns_field_id_and_name(self):
        store = FieldStore()
        path = write_yaml([make_field("cs", "Computer Science")])
        store.load(path)
        result = store.list()
        assert result == [{"field_id": "cs", "name": "Computer Science"}]

    def test_empty_store_returns_empty_list(self):
        store = FieldStore()
        path = write_yaml([])
        store.load(path)
        assert store.list() == []


# ── fuzzy_candidates() ────────────────────────────────────────────────────────

class TestFuzzyCandidates:
    def setup_method(self):
        self.store = FieldStore()
        fields = [
            make_field("computer-science", "Computer Science"),
            make_field("data-science", "Data Science"),
            make_field("neuroscience", "Neuroscience"),
        ]
        path = write_yaml(fields)
        self.store.load(path)

    def test_returns_close_match(self):
        results = self.store.fuzzy_candidates("computer-sciences")  # typo with trailing s
        assert "computer-science" in results

    def test_returns_at_most_three(self):
        results = self.store.fuzzy_candidates("science")
        assert len(results) <= 3

    def test_returns_empty_for_garbage_query(self):
        results = self.store.fuzzy_candidates("xyzzy123")
        assert results == []

    def test_empty_store_returns_empty(self):
        empty_store = FieldStore()
        path = write_yaml([])
        empty_store.load(path)
        assert empty_store.fuzzy_candidates("science") == []

    def test_never_auto_selects_below_cutoff(self):
        # A very different string should return nothing (cutoff=70)
        results = self.store.fuzzy_candidates("aaaa")
        assert results == []
