"""Offline ETL: build the college knowledge graph into Postgres.

Ingests the finite set of US institutions from College Scorecard and upserts them into
kg_colleges / kg_offerings. Idempotent — safe to re-run on the dataset's refresh cadence.

Usage:
    make build-kg                 # offline: load data/scorecard_sample.json
    python scripts/build_kg.py --source api --states CA,OR,WA --cip 11.07,30.70
                                  # live: College Scorecard API (needs SCORECARD_API_KEY)

The serving layer (PostgresKGStore) reads these tables; nothing here is shown to a user
without a source label + as_of year (see app/course_search/knowledge_graph.py).
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()

SAMPLE_PATH = Path("data/scorecard_sample.json")
SCORECARD_API = "https://api.data.gov/ed/collegescorecard/v1/schools"


def load_sample() -> tuple[str, int, list[dict]]:
    raw = json.loads(SAMPLE_PATH.read_text())
    return raw.get("source", "College Scorecard (sample)"), int(raw.get("as_of", 2023)), raw["colleges"]


def _norm_cip(code: str) -> str:
    return str(code).replace(".", "").strip()


def _ensure_url(url: str | None, fallback: str) -> str:
    if not url:
        return fallback
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


async def fetch_scorecard(states: list[str], cips: list[str]) -> tuple[str, int, list[dict]]:
    """Pull a slice of the live College Scorecard API and normalize to our college dict.

    Fetches predominantly-bachelor's institutions per state (paginated), then keeps only
    programs whose CIP is in the requested set.
    """
    api_key = os.getenv("SCORECARD_API_KEY")
    if not api_key:
        print("Error: SCORECARD_API_KEY not set (get a free key at api.data.gov).", file=sys.stderr)
        sys.exit(1)

    cip_set = {_norm_cip(c) for c in cips}
    fields = ",".join([
        "id", "school.name", "school.city", "school.state",
        "location.lat", "location.lon", "school.ownership",
        "school.school_url", "latest.admissions.admission_rate.overall",
        "latest.cost.tuition.in_state", "latest.cost.tuition.out_of_state",
        "latest.cost.avg_net_price.overall", "latest.completion.completion_rate_4yr_150nt",
        "latest.earnings.10_yrs_after_entry.median", "latest.programs.cip_4_digit",
    ])
    colleges: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for state in states:
            page = 0
            while True:
                resp = await client.get(SCORECARD_API, params={
                    "api_key": api_key, "school.state": state,
                    "school.degrees_awarded.predominant": 3,  # predominantly bachelor's
                    "fields": fields, "per_page": 100, "page": page,
                })
                resp.raise_for_status()
                body = resp.json()
                results = body.get("results", [])
                for row in results:
                    normalized = _normalize_api_row(row, cip_set)
                    if normalized:
                        colleges.append(normalized)
                meta = body.get("metadata", {})
                page += 1
                if not results or page * meta.get("per_page", 100) >= meta.get("total", 0):
                    break
    return "College Scorecard", _latest_year(), colleges


def _normalize_api_row(row: dict, cip_set: set[str]) -> dict | None:
    lat, lon = row.get("location.lat"), row.get("location.lon")
    if lat is None or lon is None:
        return None
    # Prefix match: "11" (2-digit series) covers 1101, 1107, 1110, ...; "1107" matches itself.
    programs = [
        {"cip": str(p.get("code")), "title": p.get("title")}
        for p in (row.get("latest.programs.cip_4_digit") or [])
        if p.get("title") and any(_norm_cip(p.get("code") or "").startswith(pfx) for pfx in cip_set)
    ]
    if not programs:
        return None
    ownership = {1: "Public", 2: "Private nonprofit", 3: "Private for-profit"}.get(row.get("school.ownership"))
    scorecard_url = f"https://collegescorecard.ed.gov/school/?{row.get('id')}"
    return {
        "unitid": row.get("id"),
        "name": row.get("school.name"),
        "city": row.get("school.city"),
        "state": row.get("school.state", "US"),
        "lat": lat, "lon": lon, "control": ownership, "level": "4-year",
        "url": _ensure_url(row.get("school.school_url"), scorecard_url),
        "admission_rate": row.get("latest.admissions.admission_rate.overall"),
        "tuition_in_state": row.get("latest.cost.tuition.in_state"),
        "tuition_out_state": row.get("latest.cost.tuition.out_of_state"),
        "avg_net_price": row.get("latest.cost.avg_net_price.overall"),
        "grad_rate": row.get("latest.completion.completion_rate_4yr_150nt"),
        "median_earnings": row.get("latest.earnings.10_yrs_after_entry.median"),
        "programs": programs,
    }


async def upsert(conn: asyncpg.Connection, source: str, as_of: int, colleges: list[dict]) -> tuple[int, int]:
    n_colleges = n_offerings = 0
    for c in colleges:
        await conn.execute(
            """
            INSERT INTO kg_colleges (unitid, name, city, state, lat, lon, control, level, url,
                admission_rate, tuition_in_state, tuition_out_state, avg_net_price, grad_rate,
                median_earnings, source, as_of, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17, NOW())
            ON CONFLICT (unitid) DO UPDATE SET
                name=EXCLUDED.name, city=EXCLUDED.city, state=EXCLUDED.state, lat=EXCLUDED.lat,
                lon=EXCLUDED.lon, control=EXCLUDED.control, level=EXCLUDED.level, url=EXCLUDED.url,
                admission_rate=EXCLUDED.admission_rate, tuition_in_state=EXCLUDED.tuition_in_state,
                tuition_out_state=EXCLUDED.tuition_out_state, avg_net_price=EXCLUDED.avg_net_price,
                grad_rate=EXCLUDED.grad_rate, median_earnings=EXCLUDED.median_earnings,
                source=EXCLUDED.source, as_of=EXCLUDED.as_of, updated_at=NOW()
            """,
            c["unitid"], c["name"], c["city"], c["state"], float(c["lat"]), float(c["lon"]),
            c.get("control"), c.get("level"), c.get("url"), c.get("admission_rate"),
            c.get("tuition_in_state"), c.get("tuition_out_state"), c.get("avg_net_price"),
            c.get("grad_rate"), c.get("median_earnings"), source, as_of,
        )
        n_colleges += 1
        for p in c.get("programs", []):
            await conn.execute(
                """
                INSERT INTO kg_offerings (unitid, cip, title, course_norm)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (unitid, cip) DO UPDATE SET
                    title=EXCLUDED.title, course_norm=EXCLUDED.course_norm
                """,
                c["unitid"], p["cip"], p["title"], p["title"].lower(),
            )
            n_offerings += 1
    return n_colleges, n_offerings


async def main(args) -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set (start Postgres with 'make dev-db').", file=sys.stderr)
        sys.exit(1)

    if args.source == "api":
        source, as_of, colleges = await fetch_scorecard(
            [s.strip().upper() for s in args.states.split(",") if s.strip()],
            [c.strip() for c in args.cip.split(",") if c.strip()],
        )
    else:
        source, as_of, colleges = load_sample()

    conn = await asyncpg.connect(db_url)
    try:
        n_c, n_o = await upsert(conn, source, as_of, colleges)
    finally:
        await conn.close()
    print(f"Knowledge graph built: {n_c} colleges, {n_o} offerings (source: {source} {as_of}).")


def _latest_year() -> int:
    from datetime import date
    return date.today().year - 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the college knowledge graph into Postgres.")
    parser.add_argument("--source", choices=["sample", "api"], default="sample")
    parser.add_argument("--states", default="CA,OR,WA,NV,IL,NY,MA,TX")
    parser.add_argument("--cip", default="11.07,30.70")
    asyncio.run(main(parser.parse_args()))
