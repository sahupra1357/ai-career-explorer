"""Tests for generate_summary — MOCK_CLAUDE, caching, and error handling."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import summarize as summarize_mod
from app.summarize import generate_summary, clear_cache
from tests.conftest import make_field


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the summary cache before every test so tests don't bleed."""
    clear_cache()
    yield
    clear_cache()


FIELD_A = make_field("computer-science", "Computer Science")
FIELD_B = make_field("biomedical-engineering", "Biomedical Engineering")


# ── MOCK_CLAUDE path ───────────────────────────────────────────────────────────

class TestMockClaude:
    async def test_returns_mock_string(self, monkeypatch):
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        result = await generate_summary([FIELD_A, FIELD_B], "req-1")
        assert result is not None
        assert "[MOCK]" in result

    async def test_includes_both_field_ids(self, monkeypatch):
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        result = await generate_summary([FIELD_A, FIELD_B], "req-1")
        assert "computer-science" in result
        assert "biomedical-engineering" in result

    async def test_skips_cache_lookup(self, monkeypatch):
        monkeypatch.setenv("MOCK_CLAUDE", "1")
        # Two identical calls should both return mock (not hit real cache)
        r1 = await generate_summary([FIELD_A], "req-1")
        r2 = await generate_summary([FIELD_A], "req-2")
        assert r1 is not None and r2 is not None


# ── Real Claude path: cache ────────────────────────────────────────────────────

class TestSummaryCache:
    async def test_second_call_returns_cached_result(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        call_count = 0

        async def fake_claude(prompt, request_id):
            nonlocal call_count
            call_count += 1
            return "A genuine summary."

        with patch.object(summarize_mod, "_call_claude", fake_claude):
            r1 = await generate_summary([FIELD_A, FIELD_B], "req-1")
            r2 = await generate_summary([FIELD_A, FIELD_B], "req-2")

        assert r1 == r2 == "A genuine summary."
        assert call_count == 1  # Claude called only once

    async def test_cache_key_is_order_independent(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        call_count = 0

        async def fake_claude(prompt, request_id):
            nonlocal call_count
            call_count += 1
            return "Summary."

        with patch.object(summarize_mod, "_call_claude", fake_claude):
            await generate_summary([FIELD_A, FIELD_B], "req-1")
            await generate_summary([FIELD_B, FIELD_A], "req-2")  # reversed order

        assert call_count == 1  # same sorted key → cache hit

    async def test_different_fields_get_separate_cache_entries(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        call_count = 0
        FIELD_C = make_field("data-science", "Data Science")

        async def fake_claude(prompt, request_id):
            nonlocal call_count
            call_count += 1
            return f"Summary {call_count}."

        with patch.object(summarize_mod, "_call_claude", fake_claude):
            await generate_summary([FIELD_A, FIELD_B], "req-1")
            await generate_summary([FIELD_A, FIELD_C], "req-2")

        assert call_count == 2

    async def test_clear_cache_removes_entries(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        call_count = 0

        async def fake_claude(prompt, request_id):
            nonlocal call_count
            call_count += 1
            return "Summary."

        with patch.object(summarize_mod, "_call_claude", fake_claude):
            await generate_summary([FIELD_A, FIELD_B], "req-1")
            cleared = clear_cache()
            await generate_summary([FIELD_A, FIELD_B], "req-2")

        assert cleared == 1
        assert call_count == 2  # Claude called again after cache clear


# ── Claude error handling ──────────────────────────────────────────────────────

class TestClaudeErrors:
    async def test_timeout_returns_none_via_internal_handler(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        import anthropic

        async def returning_none(prompt, request_id):
            return None  # what _call_claude returns on timeout

        with patch.object(summarize_mod, "_call_claude", returning_none):
            result = await generate_summary([FIELD_A], "req-1")

        assert result is None

    async def test_auth_error_returns_none(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)

        async def returning_none(prompt, request_id):
            return None  # what _call_claude returns on AuthenticationError

        with patch.object(summarize_mod, "_call_claude", returning_none):
            result = await generate_summary([FIELD_A], "req-1")

        assert result is None

    async def test_none_result_not_cached(self, monkeypatch):
        """A failed Claude call (None) must NOT be cached — retry on next request."""
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        call_count = 0

        async def returning_none(prompt, request_id):
            nonlocal call_count
            call_count += 1
            return None

        with patch.object(summarize_mod, "_call_claude", returning_none):
            r1 = await generate_summary([FIELD_A, FIELD_B], "req-1")
            r2 = await generate_summary([FIELD_A, FIELD_B], "req-2")

        assert r1 is None and r2 is None
        assert call_count == 2  # None not cached — Claude retried each time


# ── DEBUG_PROMPTS ──────────────────────────────────────────────────────────────

class TestDebugPrompts:
    async def test_writes_prompt_file_when_enabled(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        monkeypatch.setenv("DEBUG_PROMPTS", "1")

        async def fake_claude(prompt, request_id):
            return "Summary."

        with patch.object(summarize_mod, "_call_claude", fake_claude):
            with patch.object(summarize_mod, "_write_prompt_log") as mock_write:
                await generate_summary([FIELD_A], "req-debug")
                mock_write.assert_called_once()
                call_args = mock_write.call_args[0]
                assert call_args[0] == "req-debug"
                assert "computer-science" in call_args[1]  # prompt contains field data

    async def test_no_prompt_file_when_disabled(self, monkeypatch):
        monkeypatch.delenv("MOCK_CLAUDE", raising=False)
        monkeypatch.delenv("DEBUG_PROMPTS", raising=False)

        async def fake_claude(prompt, request_id):
            return "Summary."

        with patch.object(summarize_mod, "_call_claude", fake_claude):
            with patch.object(summarize_mod, "_write_prompt_log") as mock_write:
                await generate_summary([FIELD_A], "req-nodebug")
                mock_write.assert_not_called()
