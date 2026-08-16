"""CLI: apply numbered SQL migrations from scripts/migrations/ that haven't run yet.

The container CMD runs this before uvicorn (`python scripts/db_migrate.py && uvicorn …`),
so every deploy migrates itself and a failure stops the container from serving. The
implementation lives in app/migrations.py.

    DATABASE_URL='postgresql://…' python scripts/db_migrate.py

Exit codes: 0 on success, non-zero on any failure — including an unset DATABASE_URL. The
database is a hard dependency: without it the app can only serve the offline sample data,
and serving demo rows to a student as if they were real is worse than not serving at all.
So a missing or unreachable database stops the `&&` chain and the container never starts.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # importable from any cwd

from app.migrations import apply_migrations  # noqa: E402

load_dotenv()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print(
            "Error: DATABASE_URL not set. The database is required — this app does not "
            "serve sample or mocked data in place of a real one.",
            file=sys.stderr,
        )
        sys.exit(1)
    asyncio.run(apply_migrations(db_url))
