# AI Career Exploration

A decision-support tool for high-school students choosing a STEM path and the colleges that
teach it. Two halves share one app:

1. **Field exploration** — compare STEM fields, chat your way to a shortlist, deep-dive one field.
2. **Course-driven college aggregator** — search a *course*, get the colleges that offer it,
   grouped in expanding geographic rings, with standardized finer details and a citation on
   every fact.

The governing rule for the aggregator is **no manufactured data**. Nothing shown to a student
is invented: every figure carries a source label and an as-of date, and a field that cannot be
verified is rendered as "unavailable — verify on the official site" with a link, never as a
blank that implies a value. The same rule governs failure: if the database is missing or
unreachable, the app **fails to start** rather than quietly serving sample data in its place.

---

## Quick start

```bash
cp .env.example .env      # add OPENAI_API_KEY (or ANTHROPIC_API_KEY) + TAVILY_API_KEY
make up                   # Postgres → migrations → API + built UI on :8000
```

Open http://localhost:8000. `make logs` to follow, `make down` to stop.

Then run the **initial setup** below — on a fresh database the app starts, but every search
returns empty until the knowledge graph is loaded.

<details>
<summary>Host dev loop (hot reload, no Docker for the app)</summary>

```bash
make install     # python3.13 venv + deps
make dev-db      # Postgres only, on :5433 — required, the app will not start without it
make dev-kg      # backend on :8000 (or `make dev` / `make dev-real`)
make dev-ui      # Vite on :5173, proxies /api → :8000
```
</details>

---

## Initial setup (once per database)

Migrations run themselves — the container `CMD` applies them before uvicorn starts, so a new
database gets its schema on the next deploy. **Data is not automatic.** These two loads pull
from external APIs, so they are deliberately manual rather than running on every container
start; without them the app serves honestly empty results.

Run both against whichever database you are setting up — local, or a deployed one via its
**External** URL. Nothing needs restarting afterwards; the app reads the tables live.

### 1. Knowledge graph — every state

```bash
cd ~/AICareerExploration

# Local (Postgres from `make dev-db` / `make up`)
DATABASE_URL='postgresql://dev:dev@localhost:5433/career_explorer' \
  .venv/bin/python scripts/build_kg.py --source api --states all

# Deployed database (external URL — this is what that URL is for)
DATABASE_URL='postgresql://<user>:<pass>@<host>/career_explorer?sslmode=require' \
  .venv/bin/python scripts/build_kg.py --source api --states all
```

`--states all` covers the **50 states + DC** (`ALL_STATES` in the script), and `--cip`
defaults to every CIP family the product supports — so the command above is the full national
build. Both defaults exist so nobody hand-types 51 postal codes: one missing code produces a
knowledge graph with a silent hole in it, where searches in that state look like a data gap
rather than a typo.

`SCORECARD_API_KEY` is read from `.env` (free from api.data.gov). The ETL upserts, so it is
safe to re-run — that is also how you refresh when College Scorecard publishes a new year.

No local Python? Run the same thing through Docker:

```bash
# ...against the compose database
make docker-build-kg ARGS="--source api --states all"

# ...against a remote database — DATABASE_URL is forwarded into the container
DATABASE_URL='postgresql://<user>:<pass>@<host>/career_explorer?sslmode=require' \
  make docker-build-kg ARGS="--source api --states all"
```

The `make` target forwards `DATABASE_URL` with `-e` deliberately: `docker compose run` does
**not** inherit the shell environment, so a bare `DATABASE_URL=… docker compose run kg-build`
loads the *local* database while reporting success.

> **Rebuild the image after changing `scripts/` or `app/`.** `docker compose run` uses the
> image as last built and never rebuilds, so an edited script has no effect until you run
> `docker compose build app` (or `make up-build`). This fails quietly: an image predating
> `--states all` treats `all` as a literal postal code, matches no institutions, and reports
> `Knowledge graph built: 0 colleges, 0 offerings`. The venv commands above read the working
> tree directly and never need a rebuild.

Either way the ETL reports progress as it goes — one line per state, then the write:

```
Fetching 51 state(s) x 12 CIP families...
  [ 1/51] AL:   47 matching colleges  (running total 47)
  [ 2/51] AK:    4 matching colleges  (running total 51)
  ...
Fetched 1715 colleges. Writing to the database...
Knowledge graph built: 1715 colleges, 60090 offerings (source: College Scorecard 2025).
```

Narrow it only if you want a faster partial load:

```bash
.venv/bin/python scripts/build_kg.py --source api --states PA,NJ,NY --cip 11,51.38
```

### 2. Field embeddings (Explore mode)

Deployments set `MOCK_EMBEDDINGS=0`, so Explore runs a real pgvector search. Without this load
its recommendations come back empty:

```bash
DATABASE_URL='<same URL>' OPENAI_API_KEY='<your key>' \
  .venv/bin/python scripts/embed_fields.py
```

Loads 20 fields x 5 dimensions = 100 rows.

### 3. Verify

```bash
psql '<same URL>' \
  -c 'select count(*) from kg_colleges;' \
  -c 'select count(*) from kg_offerings;' \
  -c 'select count(*) from field_embeddings;'
```

A national build takes **about 2-3 minutes** (measured: 141s to a fresh database) and lands
roughly **1,715 colleges / 35,100 offerings across all 51 states / 100 embedding rows**. Note
the ETL's closing line reports rows *processed* (~60k), which is higher than rows *stored* —
`kg_offerings` is unique on `(unitid, cip)`, so an institution appearing under several CIP
queries collapses to one row.

Then search for a course you know exists nearby — populated tiers mean the graph is live. Four
empty tiers after this means `DATABASE_URL` points somewhere other than the database you just
loaded.

---

## The multi-agent core

The aggregator is not a scraper on a cron and not a curated database. It is a **LangGraph
multi-agent workflow**: an orchestrator seeds the candidate set, then one investigator agent
per college goes and reads that college's own website, in parallel. This is the default
request path (`COURSE_SEARCH_MODE=agent`).

The design turns on one observation: **the set of US colleges is finite and already published**.
So the agents never waste turns discovering *which* colleges exist — the knowledge graph hands
them the right ~13 institutions instantly, with real coordinates and baseline federal facts.
Agent budget goes entirely to the part that genuinely requires judgment: finding and reading
the program page for *this* college and *this* course.

### The graph

```mermaid
flowchart TB
    START(["POST /api/course-search"]) --> PLAN[build_search_plan<br/>course → CIP, city/state → tiers]
    PLAN --> SEED

    subgraph ORCH ["Orchestrator — agent_graph.py"]
        SEED["<b>seed</b><br/>KG: 1,731 colleges / 35k offerings<br/>pre-rank to the shown set"]
        ROUTE{"route_seed<br/>any candidates?"}
        AGG["<b>aggregate</b><br/>re-rank enriched findings<br/>into 4 tiers + guidance"]
    end

    SEED --> ROUTE
    ROUTE -->|"no"| AGG
    ROUTE -->|"Send() fan-out, one per college"| S1 & S2 & S3

    subgraph FANOUT ["College subagents — parallel, bounded by AGENT_CONCURRENCY"]
        S1["subagent<br/>Drexel"]
        S2["subagent<br/>Penn"]
        S3["subagent<br/>… n"]
    end

    S1 & S2 & S3 -->|"findings: Annotated[list, operator.add]"| AGG
    AGG --> OUT(["tiers + guidance + provenance"])
```

`findings` is an `Annotated[list, operator.add]` channel, so LangGraph reduces the parallel
subagent returns into one list without the nodes coordinating.

### Inside one college subagent

Each subagent is a real tool-use loop — it decides what to search, which page to read, and
when it has enough. It is not a prompt template with a fixed pipeline.

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Subagent (LLM)
    participant C as Investigation cache
    participant W as search_web (Tavily)
    participant P as fetch_page

    O->>A: CollegeProgram + plan (KG-seeded)
    A->>C: (domain, course) cached & fresh?
    C-->>A: hit → return findings, no LLM spend
    Note over A: miss → acquire semaphore, run loop
    loop ≤ AGENT_MAX_ROUNDS
        A->>W: "Drexel BS computer science degree requirements"
        W-->>A: results, own-domain hits ranked first
        A->>P: fetch chosen .edu URL
        P-->>A: visible text (≤ MAX_PAGE_CHARS)
        Note over A: enough? else search/fetch again
    end
    A->>O: report(program_page_url, curriculum,<br/>semester_plan, admission_factors)
    A->>C: persist to kg_investigations (TTL 30d)
```

**Three tools, one of them terminal.** `search_web` and `fetch_page` gather; `report` ends the
loop with a typed payload. On the final round the loop forces `tool_choice = report`, so an
agent that keeps browsing still yields something structured instead of timing out.

**Anti-fabrication is built into the loop, not bolted on after.** The system prompt instructs
the agent to leave a field out rather than guess, `report`'s schema makes every finding except
the page URL optional, and a subagent that never calls `report` returns the program flagged
`catalog_page_not_found` — an honest gap, not a filled-in guess. Findings are attached with the
URL the agent actually read, so the UI can cite it.

**Cost and rate-limit control** — the practical constraints that shaped the design:

| Control | Mechanism | Why |
|---|---|---|
| Fan-out width | KG pre-ranks to the ~13 shown colleges | Investigate only what a student will see |
| Concurrency | module-level `asyncio.Semaphore(AGENT_CONCURRENCY)` | A 13-wide fan-out otherwise 429s a low tier |
| Loop depth | `AGENT_MAX_ROUNDS` (default 4), forced report on the last | Bounds worst-case spend per college |
| Search tokens | Tavily/Brave, not the LLM's own web-search tool | Search burns **zero** LLM tokens; reasoning only |
| Repeat work | `kg_investigations`, keyed `(domain, course)`, TTL 30d | Survives restarts; paid once across modes |
| Page size | truncation at `MAX_PAGE_CHARS` | One catalog page can't blow the context |

**Provider-agnostic agents.** `agent_llm.py` takes neutral tool specs — `{name, description,
input_schema}` — and adapts them to OpenAI function calling or Anthropic tool use. `LLM_PROVIDER`
flips both the agent loop and every other LLM feature (`app/llm.py`), so the whole app moves
providers with one variable. `MOCK_LLM=1` / `MOCK_CLAUDE=1` short-circuits to deterministic
findings for offline dev and tests.

**Live progress.** `POST /api/course-search/stream` runs the same graph under `astream`, turning
node updates into SSE: `seeded{total}` → `investigating{done,total}` per college → `done{result}`.
The progress bar reports real agent completions, not a fake timer.

### A second, simpler graph

Explore mode (`/api/explore`) is its own LangGraph: `intake → clarify (≤2 turns) → recommend`,
where `recommend` embeds the student's interests and runs a pgvector similarity search over the
20-field knowledge base. Conversation state is checkpointed per session.

---

## System architecture

```mermaid
flowchart TB
    subgraph CLIENT ["Browser — React 19 + Vite + Tailwind"]
        UI["App.tsx — 4 tabs<br/>Course Finder · Compare · Explore · Deep Dive"]
    end

    UI -->|"JSON / SSE"| API

    subgraph BACK ["FastAPI (app/main.py) — serves ui/dist in prod"]
        API["Routes + slowapi rate limits<br/>/api/course-search · /stream · /compare<br/>/api/explore · /api/direct · /health"]
        MODE{"COURSE_SEARCH_MODE"}
        AGENTG["agent_graph.py<br/><b>multi-agent (default)</b>"]
        SVC["service.py<br/>deterministic pipeline<br/>kg · live · fallback"]
        EXPG["explore_graph.py<br/>intake→clarify→recommend"]
        LLM["llm.py + agent_llm.py<br/>LLM_PROVIDER switch"]
    end

    API --> MODE
    MODE -->|agent| AGENTG
    MODE -->|kg / live / fallback| SVC
    API --> EXPG
    AGENTG --> LLM
    SVC --> LLM
    EXPG --> LLM

    AGENTG --> KG
    SVC --> KG
    AGENTG --> SEARCH
    SVC --> SEARCH

    subgraph DATA ["Postgres 16 + pgvector (:5433)"]
        KG["kg_colleges · kg_offerings<br/>kg_rankings · kg_investigations<br/>field_embeddings"]
    end

    subgraph EXT ["External"]
        SEARCH["Search: Tavily · Brave · Apify · DDG"]
        EDU[".edu program pages"]
        SC["College Scorecard API"]
        LLMP["OpenAI / Anthropic"]
    end

    SEARCH -.-> EDU
    LLM --> LLMP
    SC -->|"scripts/build_kg.py ETL, offline"| KG
```

### Request flow, end to end

```mermaid
flowchart LR
    Q["'cs' + Philadelphia, PA"] --> R["resolve_course()<br/>→ Computer Science<br/>CIP 11.07"]
    R --> KGQ["KG query<br/>CIP prefix + trigram title"]
    KGQ --> D["dedupe by program_id"]
    D --> T["tier + rank"]
    T --> INV["subagents investigate<br/>only the shown set"]
    INV --> RE["re-rank with enriched facts"]
    RE --> G["guidance + honest gaps"]
```

**Geographic tiering** (`ranking.py`) — four expanding rings, each capped, no college repeated
across rings:

| Tier | Rule | Cap | Sort |
|---|---|---|---|
| `nearby` | haversine ≤ `nearby_radius_miles` (150) | 3 | distance |
| `home_state` | `state == home_state` | 3 | distance |
| `nearby_home_states` | `NEIGHBORING_STATES[home_state]` — a hand-built 50-state + DC land-adjacency map | 3 | distance |
| `best_usa` | everything else | 4 | composite score |

**Ranking is transparent and explicitly not U.S. News.** `ranking_score` is a composite of open
College Scorecard outcomes — graduation .35, earnings .30, selectivity .20, value .15 — with the
breakdown shown in the UI. Metrics a college lacks are skipped and the remaining weights
renormalized — never backfilled. Proprietary ranking numbers are never scraped; `rankings[]` holds
verify-links only. Licensed ranks load into `kg_rankings` and serve only when `RANKINGS_LICENSED=1`.

---

## Course search modes

| Mode | Path | Latency | LLM cost | Use |
|---|---|---|---|---|
| `agent` *(default)* | KG seed → per-college subagents → aggregate | 30–60s cold, cached after | per college | Full product experience |
| `kg` | KG → rank → optional `enrich_shown_programs` | ~50ms (+enrichment) | none unless `COURSE_READ_PAGES=1` | Fast, deterministic, cheap |
| `live` | Web discovery only, no KG | slow | extraction only | Debugging discovery |
| `fallback` | `data/college_programs.yaml` | instant | none | Tests, offline demos |

`kg` and `agent` need a populated Postgres KG — that is the default, and a missing
`DATABASE_URL` now raises at startup rather than degrading. The 8-college demo file is served
only when explicitly requested with `KG_BACKEND=sample`. Note that `live` mode drops the KG
entirely and returns thin stubs — if results look empty or placeholder-ish, check that mode
isn't exported in your shell.

---

## Data sourcing

| Field group | Source | Freshness |
|---|---|---|
| Institution identity, location, control, level | College Scorecard (IPEDS-derived) | ETL re-run; `as_of` year stored |
| Admission rate, tuition, net price, grad rate, median earnings | College Scorecard | same |
| Carnegie classification | Carnegie (free file) via `make load-carnegie` | manual load |
| Curriculum, semester plan, admission factors, deadlines | The college's **own .edu page**, read live by a subagent | `kg_investigations` TTL 30d |
| Licensed ranks | Your licensed file via `make load-rankings` | off unless `RANKINGS_LICENSED=1` |

Discovery search is pluggable via `SEARCH_PROVIDER`: `tavily` (default), `brave`, `apify`,
`claude`, `duckduckgo`.

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/course-search` | Course → colleges in 4 geographic tiers |
| `POST /api/course-search/stream` | Same, as SSE with live agent progress |
| `POST /api/compare` | Compare 2–3 STEM fields (422 on partial not-found) |
| `POST /api/explore` | Multi-turn explore chat (LangGraph + pgvector) |
| `POST /api/direct` | Deep-dive one field |
| `GET /api/fields` · `GET /health` · `POST /api/cache/clear` | Support |

```bash
curl -s -X POST localhost:8000/api/course-search \
  -H 'content-type: application/json' \
  -d '{"course_query":"nursing","city":"Philadelphia","state":"PA"}'
```

Request fields are flat: `course_query` (required), `city`, `state`, `home_state`. Each tier
returns `{tier, title, programs[]}`, and each entry is `{program, distance_miles, match_reason}`.

---

## Layout

```
app/
  main.py                    FastAPI routes, lifespan, static UI mount
  llm.py                     provider-agnostic completion (LLM_PROVIDER)
  explore_graph.py           LangGraph: intake → clarify → recommend
  course_search/
    agent_graph.py           ★ orchestrator graph + SSE streaming
    subagent.py              ★ per-college investigator agent (tools, prompt, guards)
    agent_llm.py             ★ provider-agnostic tool-use loop
    investigation_cache.py   ★ persistent findings cache (kg_investigations)
    knowledge_graph.py       KG stores + Scorecard → CollegeProgram mapping
    cip_aliases.py           "cs" → Computer Science, CIP 11.07
    ranking.py               state adjacency, haversine, tiers, composite score
    reader.py                page fetch + LLM extraction + KG enrichment path
    search_backends.py       Tavily / Brave / Apify / Claude / DuckDuckGo
    service.py               deterministic kg/live/fallback pipeline
scripts/                     migrations, build_kg ETL, embeddings, loaders
ui/src/components/           CourseFinder · ComparisonResult · ChatInterface · DeepDivePage
docs/DESIGN.md               full 16-section design document
```

---

## Testing

```bash
COURSE_SEARCH_MODE=fallback KG_BACKEND=sample make test     # 144 passing
```

Those two variables matter: the suite loads `.env`, so a developer whose `.env` points at a
running Postgres KG will see `test_course_finder.py` fail — it asserts on the curated fixture
but gets real KG rows instead. Run tests with the fallback repo as shown.

---

## Deployment

`Dockerfile` is a two-stage build (Node builds the React app; Python serves it and the API from
one process on `:8000`). `render.yaml` deploys it to Render. `docker-compose.yml` runs the full
local stack — `db` → `app` (which migrates itself on start), plus a profile-gated `kg-build`
for the ETL.

### Deploying to Render (free tier, own database on an existing instance)

The blueprint deliberately does **not** declare a database, so a deploy never creates or
touches one. You point it at a database you own.

**Use a separate logical database on your existing Postgres instance** — not a second instance,
and not shared tables. Render's free tier allows only *one* free Postgres instance per
workspace, so a second instance isn't an option; but one instance can host many databases, and
Render supports creating them. A dedicated database gives full isolation — its own
`schema_migrations`, its own extensions, its own backups-by-name — with no `search_path`
juggling and no chance of adopting another project's tables.

Steps 1–4 run from your laptop, because the database must have its schema and knowledge graph
before the web service is worth deploying.

**1. Create the database on the existing instance.** Take the instance's *External Database URL*
from the Render dashboard (your DB → *Connections*) and connect with `psql`:

```bash
psql 'postgresql://<user>:<pass>@<host>/<existing_db>?sslmode=require' \
  -c 'CREATE DATABASE career_explorer;'
```

If that returns `permission denied to create database`, the role lacks `CREATEDB` — fall back to
a dedicated schema in the existing database (`CREATE SCHEMA career_explorer;` plus
`?options=-csearch_path%3Dcareer_explorer,public` on every connection string below; the
`,public` part is required, or migration 001 fails with `type "vector" does not exist`).

**2. Build the connection string** for the new database. Every database on one instance shares
the same host and credentials — only the database name changes:

```
postgresql://<user>:<pass>@<host>/career_explorer?sslmode=require
```

- Use the **External URL** form (with `sslmode=require`) for the local steps below.
- For Render's `DATABASE_URL`, prefer the **Internal URL** host if the web service is in the
  same region as the database — swap the database name the same way. Otherwise keep the
  external form. `asyncpg` reads `sslmode` straight from the DSN.

**3. Migrations — automatic.** The image's `CMD` is
`python scripts/db_migrate.py && uvicorn app.main:app …`, so every container start applies
pending migrations before the server comes up. Nothing to run here on the first deploy, and
nothing to remember when the schema changes later: **point `DATABASE_URL` at a new empty
database, redeploy, and it builds its own schema** (`schema_migrations`, `field_embeddings`,
`kg_colleges`, `kg_offerings`, `kg_rankings`, `kg_investigations`, plus the `vector` and
`pg_trgm` extensions). Already-applied versions are skipped, and an advisory lock keeps
concurrent starts from racing.

Baking it into the image rather than an env var or a platform hook means it cannot be
forgotten, and it behaves identically on Render, `docker compose`, and a bare `docker run` —
which matters here because Render's free tier offers neither `preDeployCommand` nor shell
access. If a migration fails, `&&` short-circuits, the container exits non-zero, and Render
keeps the previous deploy live instead of serving a half-built schema.

There is no degraded mode. An unset or unreachable `DATABASE_URL` fails the migration step,
and the app's own startup fails too if the pool can't be created — the container never serves.
Showing a student the 8-college demo file dressed up as the real national graph is worse than
showing nothing, so the sample store is reachable only by asking for it by name
(`KG_BACKEND=sample`, for tests and offline development).

To apply migrations by hand — against a remote database, or during local host development:

```bash
DATABASE_URL='postgresql://…/career_explorer?sslmode=require' \
  .venv/bin/python scripts/db_migrate.py     # or: make migrate
```

**4. Populate the knowledge graph** — the one step that is *not* automatic, because it
pulls tens of thousands of rows from the College Scorecard API and shouldn't run on every
boot. Without it, course search has nothing to search:

```bash
DATABASE_URL='postgresql://…/career_explorer?sslmode=require' \
  .venv/bin/python scripts/build_kg.py --source api --states all
```

That is the full national build — `--states all` is the 50 states + DC, and `--cip` defaults
to every family the app covers. About 2-3 minutes, ~1,715 colleges and ~35k offerings. `SCORECARD_API_KEY` comes
from `.env`; the key is free from api.data.gov. Re-run any time; the ETL upserts. See
[Initial setup](#initial-setup-once-per-database) for the full walkthrough. Verify before
deploying:

```bash
psql 'postgresql://…/career_explorer?sslmode=require' \
  -c 'select count(*) from kg_colleges;' -c 'select count(*) from kg_offerings;'
```

**4b. Embed the STEM fields** — `render.yaml` sets `MOCK_EMBEDDINGS=0`, so Explore runs a real
pgvector search instead of returning a random sample. Without this the table is empty and Explore
returns no recommendations (honestly empty, but empty):

```bash
DATABASE_URL='postgresql://…/career_explorer?sslmode=require' OPENAI_API_KEY='…' \
  .venv/bin/python scripts/embed_fields.py
```

**5. Create the service.** Render dashboard → *New* → *Blueprint* → pick this repo. Render reads
`render.yaml` and creates the `ai-career-explorer` Docker web service.

**6. Set the secrets** — every `sync: false` var, in the service's *Environment* tab:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the step-2 URL for `career_explorer` (Internal host if same region) |
| `OPENAI_API_KEY` | required when `LLM_PROVIDER=openai` (the default) |
| `ANTHROPIC_API_KEY` | required instead when `LLM_PROVIDER=anthropic` |
| `TAVILY_API_KEY` | subagent web search |

The missing-key check runs at startup and raises, so a wrong provider/key pairing fails the
deploy loudly rather than at first request.

**7. Deploy and verify:**

```bash
curl -s https://<your-service>.onrender.com/health
curl -s -X POST https://<your-service>.onrender.com/api/course-search \
  -H 'content-type: application/json' \
  -d '{"course_query":"nursing","city":"Philadelphia","state":"PA"}'
```

`/health` returning `fields_loaded: 20` only proves the app booted — it does **not** touch the
database. Confirm the DB wiring with a real course search: populated tiers mean the KG is
connected; four empty tiers mean `DATABASE_URL`/`KG_BACKEND` didn't take, or step 4 hasn't run.

**Notes for later deploys**

- **Migrations run themselves** from the container `CMD` — no `preDeployCommand`, no shell,
  no env var to set. This mirrors the migrate-then-serve pattern used by the sibling
  ContractReviewSystem deployment.
- **Free instances sleep** after ~15 minutes idle, so the first request after a nap pays a cold
  start on top of the 30–60s agent fan-out. `AGENT_CONCURRENCY` is set to 2 for the free
  instance's memory; raise it on a paid plan.
- **Explore mode** ships with `MOCK_EMBEDDINGS=1`, which returns a random KB sample instead of a
  real pgvector search. For genuine recommendations set it to `0` and run
  `DATABASE_URL=… .venv/bin/python scripts/embed_fields.py` (costs OpenAI embedding calls).
- **If the instance is a *free* Render Postgres, it expires 30 days after creation** (then a
  14-day grace period before deletion) — and that clock belongs to the instance, so a new
  database inside it inherits the same deadline and takes both projects down together.
  Recovery is two steps: create the database on the new instance, update `DATABASE_URL`, and
  redeploy — the schema rebuilds itself; then re-run step 4 to reload the knowledge graph.
- **Cost control:** the agent path caches investigations in `kg_investigations` for
  `INVESTIGATION_TTL_DAYS` (30), so repeat searches on the same course don't re-pay the LLM.
