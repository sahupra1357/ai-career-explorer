"""Apply numbered SQL migrations from scripts/migrations/ that haven't run yet."""
import asyncio
import os
import re
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def migrate(database_url: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        # Bootstrap: create migrations table if it doesn't exist yet
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                version TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """)

        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}

        sql_files = sorted(
            f for f in MIGRATIONS_DIR.glob("*.sql")
            if re.match(r"^\d+_", f.name)
        )

        for sql_file in sql_files:
            version = sql_file.stem
            if version in applied:
                print(f"  skip {version} (already applied)")
                continue

            print(f"  apply {version}...")
            sql = sql_file.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )
            print(f"  ok    {version}")

        print("Migrations complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(migrate(db_url))
