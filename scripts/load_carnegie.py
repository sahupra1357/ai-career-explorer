"""Load Carnegie Classification (free, official) into kg_colleges.

The Carnegie data file (carnegieclassifications.acenet.edu) is keyed by IPEDS UNITID. Map
it to a simple CSV — `unitid,classification[,year]` — or point the column flags at the raw
download's column names. Updates existing kg_colleges rows by unitid (run build-kg first).

Usage:
    python scripts/load_carnegie.py --file carnegie.csv --year 2025
    python scripts/load_carnegie.py --file raw.csv --col-unitid UNITID --col-class BASIC2021 --year 2021
"""
import argparse
import asyncio
import csv
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()


def read_rows(path: str, col_unitid: str, col_class: str, col_year: str | None, default_year: int):
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw_id, classification = row.get(col_unitid), (row.get(col_class) or "").strip()
            if not raw_id or not classification:
                continue
            try:
                unitid = int(str(raw_id).strip())
            except ValueError:
                continue
            year = int(row[col_year]) if col_year and row.get(col_year) else default_year
            yield unitid, classification, year


async def main(args) -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set (start Postgres with 'make dev-db').", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(db_url)
    updated = missing = 0
    try:
        for unitid, classification, year in read_rows(
            args.file, args.col_unitid, args.col_class, args.col_year, args.year
        ):
            result = await conn.execute(
                "UPDATE kg_colleges SET carnegie=$2, carnegie_year=$3 WHERE unitid=$1",
                unitid, classification, year,
            )
            if result.endswith("0"):
                missing += 1
            else:
                updated += 1
    finally:
        await conn.close()
    print(f"Carnegie loaded: {updated} colleges updated, {missing} unitids not in kg_colleges.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Load Carnegie Classification into kg_colleges.")
    p.add_argument("--file", required=True)
    p.add_argument("--col-unitid", default="unitid")
    p.add_argument("--col-class", default="classification")
    p.add_argument("--col-year", default=None)
    p.add_argument("--year", type=int, default=2025)
    asyncio.run(main(p.parse_args()))
