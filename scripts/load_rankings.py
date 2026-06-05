"""Load LICENSED provider ranks (e.g. U.S. News) into kg_rankings.

Only run this with data you are licensed to use — U.S. News and most major rankings are
copyrighted. The `--license` argument records the licence holder/agreement for audit. These
values are served ONLY when RANKINGS_LICENSED=1.

Input CSV columns (override with flags): unitid, provider, rank, list_name, year, source_url

Usage:
    python scripts/load_rankings.py --file usnews_2025.csv --license "USN Academic Insights #1234"
"""
import argparse
import asyncio
import csv
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()


def read_rows(path: str):
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                unitid, rank = int(row["unitid"]), int(row["rank"])
            except (KeyError, ValueError):
                continue
            provider = (row.get("provider") or "").strip()
            if not provider:
                continue
            yield {
                "unitid": unitid, "provider": provider, "rank": rank,
                "list_name": (row.get("list_name") or None),
                "year": int(row["year"]) if row.get("year") else None,
                "source_url": (row.get("source_url") or None),
            }


async def main(args) -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set (start Postgres with 'make dev-db').", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(db_url)
    loaded = skipped = 0
    try:
        for r in read_rows(args.file):
            if r["year"] is None:
                r["year"] = args.year
            # FK to kg_colleges — skip ranks for institutions not in the graph.
            exists = await conn.fetchval("SELECT 1 FROM kg_colleges WHERE unitid=$1", r["unitid"])
            if not exists:
                skipped += 1
                continue
            await conn.execute(
                """
                INSERT INTO kg_rankings (unitid, provider, rank, list_name, year, source_url, license)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (unitid, provider, list_name, year) DO UPDATE SET
                    rank=EXCLUDED.rank, source_url=EXCLUDED.source_url,
                    license=EXCLUDED.license, loaded_at=NOW()
                """,
                r["unitid"], r["provider"], r["rank"], r["list_name"], r["year"],
                r["source_url"], args.license,
            )
            loaded += 1
    finally:
        await conn.close()
    print(f"Licensed rankings loaded: {loaded} rows ({skipped} skipped — unitid not in kg_colleges).")
    print("Reminder: set RANKINGS_LICENSED=1 to serve these values.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Load licensed provider ranks into kg_rankings.")
    p.add_argument("--file", required=True)
    p.add_argument("--license", required=True, help="Licence holder / agreement id (audit trail).")
    p.add_argument("--year", type=int, default=2025)
    asyncio.run(main(p.parse_args()))
