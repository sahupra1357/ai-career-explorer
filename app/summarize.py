"""Claude comparison summary generator with MOCK_CLAUDE and DEBUG_PROMPTS support."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import structlog

log = structlog.get_logger()

_PROMPT_TEMPLATE = """\
You are a structured career exploration assistant for high school students.

Given the following validated data for {n} STEM fields, write a comparison_summary:
a 2-3 sentence insight identifying the most important difference between these fields
for a student deciding which to pursue.

RULES:
- Do NOT reference specific salary figures, percentages, or any quantitative data.
  The structured table already shows numbers. Your job is qualitative insight only.
- Focus on: what kind of person thrives in each field, and when to choose one over the other.
- Do not list the field names as a bullet list. Write flowing prose.

Field data (from validated knowledge base — do not modify):
{field_data}

Return ONLY the comparison_summary. 2-3 sentences. Plain English. No markdown.
"""


def _build_prompt(field_entries: list[dict]) -> str:
    return _PROMPT_TEMPLATE.format(
        n=len(field_entries),
        field_data=json.dumps(field_entries, indent=2),
    )


@lru_cache(maxsize=256)
def _cached_summary_key(field_ids_frozen: tuple[str, ...]) -> str | None:
    # Cache key is the sorted tuple of field_ids — populated by generate_summary
    return None  # placeholder; real values stored via cache replacement below


# We bypass lru_cache directly and use a plain dict so we can store results
# from async calls. lru_cache doesn't work cleanly with async functions.
_summary_cache: dict[tuple[str, ...], str | None] = {}


async def generate_summary(
    field_entries: list[dict],
    request_id: str,
) -> str | None:
    """
    Generate the comparison_summary via Claude.

    Returns None (with summary_status='error') on Claude failure.
    Caches results keyed on sorted field_ids — bypass with MOCK_CLAUDE=1.

    Environment flags:
      MOCK_CLAUDE=1     Return a static string without calling Claude.
      DEBUG_PROMPTS=1   Write the full prompt to logs/prompts/{request_id}.txt.
    """
    field_ids = tuple(sorted(e["field_id"] for e in field_entries))

    if os.getenv("MOCK_CLAUDE") == "1":
        return (
            f"[MOCK] Comparison of {', '.join(field_ids)}. "
            "MOCK_CLAUDE is enabled — set MOCK_CLAUDE=0 in .env for real output."
        )

    if field_ids in _summary_cache:
        log.info("cache_hit", field_ids=field_ids, request_id=request_id)
        return _summary_cache[field_ids]

    prompt = _build_prompt(field_entries)

    if os.getenv("DEBUG_PROMPTS"):
        _write_prompt_log(request_id, prompt)

    result = await _call_claude(prompt, request_id)
    _summary_cache[field_ids] = result
    return result


async def _call_claude(prompt: str, request_id: str) -> str | None:
    import time

    import anthropic

    client = anthropic.AsyncAnthropic()
    timeout = float(os.getenv("CLAUDE_TIMEOUT_S", "10"))

    try:
        start = time.monotonic()
        message = await client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        )
        elapsed = time.monotonic() - start
        summary = message.content[0].text.strip()
        log.info(
            "claude_ok",
            request_id=request_id,
            elapsed_ms=round(elapsed * 1000),
            tokens=message.usage.input_tokens + message.usage.output_tokens,
        )
        return summary
    except anthropic.APITimeoutError:
        elapsed = time.monotonic() - start
        log.warning(
            "claude_timeout",
            request_id=request_id,
            elapsed_ms=round(elapsed * 1000),
            timeout_s=timeout,
        )
        return None
    except anthropic.AuthenticationError:
        log.error("claude_auth_error", request_id=request_id)
        return None
    except Exception as exc:  # noqa: BLE001
        log.error("claude_error", request_id=request_id, error=str(exc))
        return None


def clear_cache() -> int:
    """Clear the in-memory summary cache. Returns number of entries cleared."""
    count = len(_summary_cache)
    _summary_cache.clear()
    return count


def _write_prompt_log(request_id: str, prompt: str) -> None:
    try:
        log_dir = Path("logs/prompts")
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{request_id}.txt").write_text(prompt)
    except Exception:  # noqa: BLE001
        pass
