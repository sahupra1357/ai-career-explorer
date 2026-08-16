"""Apply numbered SQL migrations from scripts/migrations/.

Called by `scripts/db_migrate.py`, which the container CMD runs before uvicorn starts —
so every deploy migrates itself, and a failure fails the container rather than serving
against a half-built schema. Point DATABASE_URL at a brand-new database and the next deploy
brings its schema up on its own.

Idempotent: already-applied versions are skipped, and a Postgres advisory lock serializes
concurrent boots so two instances starting at once can't both apply the same file.
"""
from __future__ import annotations

import re
from pathlib import Path

import structlog

log = structlog.get_logger()

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "migrations"

# Arbitrary but fixed key — any process migrating THIS schema takes the same lock.
_ADVISORY_LOCK_KEY = 8_675_309


async def apply_migrations(database_url: str, *, echo=print) -> list[str]:
    """Apply every pending migration. Returns the versions applied this run."""
    import asyncpg

    conn = await asyncpg.connect(database_url)
    applied_now: list[str] = []
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", _ADVISORY_LOCK_KEY)
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id SERIAL PRIMARY KEY,
                    version TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT NOW()
                )
            """)

            applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
            sql_files = sorted(
                f for f in MIGRATIONS_DIR.glob("*.sql") if re.match(r"^\d+_", f.name)
            )

            for sql_file in sql_files:
                version = sql_file.stem
                if version in applied:
                    echo(f"  skip {version} (already applied)")
                    continue

                echo(f"  apply {version}...")
                sql = sql_file.read_text()
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)", version
                    )
                applied_now.append(version)
                echo(f"  ok    {version}")

            echo("Migrations complete.")
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _ADVISORY_LOCK_KEY)
    finally:
        await conn.close()

    return applied_now
