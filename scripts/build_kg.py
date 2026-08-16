"""Offline ETL: build the college knowledge graph into Postgres.

Ingests the finite set of US institutions from College Scorecard and upserts them into
kg_colleges / kg_offerings. Idempotent — safe to re-run on the dataset's refresh cadence.

Usage:
    make build-kg                 # offline: load data/scorecard_sample.json
    python scripts/build_kg.py --source api --states CA,OR,WA --cip 11.07,30.70
                                  # live: College Scorecard API (needs SCORECARD_API_KEY)
    python scripts/build_kg.py --source api --states all --cip <families>
                                  # national: every state + DC (see ALL_STATES)

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

# All 50 states + DC — `--states all`. Spelled out rather than typed by hand at the command
# line, where a missing or misspelled code silently yields a knowledge graph with a hole in
# it: searches in that state come back empty and look like a data gap, not a typo.
ALL_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

# The CIP families the product covers today (see app/course_search/cip_aliases.py):
# computer science, engineering, biology, math/stats, data science, physical sciences,
# psychology, social sciences, health/nursing, and business.
DEFAULT_CIP_FAMILIES = "11,14,26,27,30.70,30.71,40,42,45,51.38,51.39,52"


def _parse_states(raw: str) -> list[str]:
    if raw.strip().lower() == "all":
        return list(ALL_STATES)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


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
    total_states = len(states)
    async with httpx.AsyncClient(timeout=30) as client:
        for index, state in enumerate(states, start=1):
            before = len(colleges)
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
            # One line per state: a national build is minutes of silence otherwise, which is
            # indistinguishable from a hang. flush=True because this usually runs piped
            # (docker compose run, CI), where stdout is block-buffered.
            print(
                f"  [{index:>2}/{total_states}] {state}: "
                f"{len(colleges) - before:>4} matching colleges  (running total {len(colleges)})",
                flush=True,
            )
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
        states = _parse_states(args.states)
        print(f"Fetching {len(states)} state(s) x {len(args.cip.split(','))} CIP families...")
        source, as_of, colleges = await fetch_scorecard(
            states,
            [c.strip() for c in args.cip.split(",") if c.strip()],
        )
    else:
        source, as_of, colleges = load_sample()

    print(f"Fetched {len(colleges)} colleges. Writing to the database...", flush=True)
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
    parser.add_argument(
        "--states", default="all",
        help='Comma-separated postal codes, or "all" for the 50 states + DC (default).',
    )
    parser.add_argument(
        "--cip", default=DEFAULT_CIP_FAMILIES,
        help="Comma-separated CIP families to ingest (default: every family the app covers).",
    )
    asyncio.run(main(parser.parse_args()))
