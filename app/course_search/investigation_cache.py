"""Persistent cache for college program investigations (survives restarts).

Keyed by (college domain, normalized course). Postgres-backed (table kg_investigations)
when DATABASE_URL is set and we're not mocking; in-memory otherwise (dev/tests). TTL-bounded
so stale facts get re-investigated. Shared by both the agent subagents and the kg/live page
reader, so an investigation is paid once across modes and across restarts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import structlog

from app.llm import mock_llm

log = structlog.get_logger()

# In-memory fallback: (domain, course) -> (url, findings, when)
_MEM: dict[tuple[str, str], tuple[str, dict, datetime]] = {}
_POOLS: dict[str, object] = {}


def _ttl_seconds() -> int:
    return int(os.getenv("INVESTIGATION_TTL_DAYS", "30")) * 86_400


def _use_postgres() -> bool:
    # Don't persist mock results, and only use PG when a DB is configured.
    return bool(os.getenv("DATABASE_URL")) and not mock_llm()


async def _pool():
    import asyncpg

    url = os.environ["DATABASE_URL"]
    pool = _POOLS.get(url)
    if pool is None:
        pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        _POOLS[url] = pool
    return pool


async def get_investigation(domain: str, course_norm: str) -> tuple[str, dict] | None:
    """Return (program_page_url, findings) if a fresh investigation is cached, else None."""
    if _use_postgres():
        try:
            pool = await _pool()
            row = await pool.fetchrow(
                "SELECT program_page_url, findings FROM kg_investigations "
                "WHERE domain=$1 AND course_norm=$2 "
                "AND investigated_at > NOW() - make_interval(secs => $3)",
                domain, course_norm, _ttl_seconds(),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("investigation_cache_read_failed", error=str(exc))
            return None
        if row is None:
            return None
        findings = row["findings"]
        return row["program_page_url"], (json.loads(findings) if isinstance(findings, str) else findings)

    entry = _MEM.get((domain, course_norm))
    if entry is None:
        return None
    url, findings, when = entry
    if (datetime.now(timezone.utc) - when).total_seconds() > _ttl_seconds():
        return None
    return url, findings


async def save_investigation(domain: str, course_norm: str, url: str, findings: dict) -> None:
    if _use_postgres():
        try:
            pool = await _pool()
            await pool.execute(
                "INSERT INTO kg_investigations (domain, course_norm, program_page_url, findings, investigated_at) "
                "VALUES ($1, $2, $3, $4::jsonb, NOW()) "
                "ON CONFLICT (domain, course_norm) DO UPDATE SET "
                "program_page_url=EXCLUDED.program_page_url, findings=EXCLUDED.findings, investigated_at=NOW()",
                domain, course_norm, url, json.dumps(findings),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("investigation_cache_write_failed", error=str(exc))
        return
    _MEM[(domain, course_norm)] = (url, findings, datetime.now(timezone.utc))


def clear_memory() -> int:
    n = len(_MEM)
    _MEM.clear()
    return n
