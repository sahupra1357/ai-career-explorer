# DESIGN — Course-Driven College Aggregator ("10 searches at once")

> Build-ready design document. Authored from the dual perspective of (1) an independent
> college admissions counselor and (2) a senior software product architect.
>
> **Status:** Living design. Phase 1–2 of the course-search engine are implemented in
> `app/course_search/`; later phases are specified below.
> **Supersedes / extends:** `docs/dynamic-course-search-design.md` (the engineering
> sketch this document formalizes) and reuses the no-manufactured-data discipline,
> provenance model, and "comparison is secondary" positioning established during the
> `/office-hours` review of the sibling field-exploration product.
> **Last updated:** 2026-06-03

---

## 0. How to read this document

This product has two halves that share one repo:

| Half | Question it answers | Status |
|------|--------------------|--------|
| **Field Exploration** (existing) | "Which *field* should I study — biomedical eng vs. bioinformatics?" | Shipped (Phase 1–2) |
| **College Aggregator** (this doc) | "Which *colleges* offer the course I picked, and what are the finer details?" | Engine built, hardening in progress |

This document specifies the **College Aggregator**. It is the natural next step after a
student has chosen a field: they now have a course in mind and need to decide *where* to
study it. The two halves connect at one seam — a field's deep-dive page links into a
course search pre-populated with that field's typical major (see §10).

The non-negotiable product constraints (no manufactured data, 10-searches aggregation,
course-driven, geographic tiering, aggregator-not-comparator, honest gaps) are carried
through every section below and are restated where they bind a design decision.

---

## 1. Executive summary & problem statement

**Problem.** A student who knows *what* they want to study still faces a fragmented,
unreliable research process to decide *where*. The finer facts that actually drive the
choice between College A and College B — acceptance criteria, semester structure, real
tuition for *their* residency tier, housing cost, commute, outcomes — live scattered
across dozens of official `.edu` pages, bursar PDFs, and federal datasets. Getting a
consistent read on even five colleges means ~10 searches per college, ~50 tabs, and hours
of manual normalization. The student ends up comparing colleges on *different* fields
because they never found the same data point for each.

**Product.** A web app where the primary input is a **course/program** and the primary
output is the **list of colleges that offer it**, organized in expanding geographic rings
from the student, with a **standardized A–I finer-detail field set** aggregated per
college in real time from **real, citable sources**. It compresses "10 searches at once"
into one consolidated, sourced view. Optional 2–3 college comparison is a *secondary*
view; the product's identity is **search + aggregation + decision support**, not
comparison.

**The hard rule that shapes everything: no manufactured data.** Every tuition figure,
deadline, GPA cutoff, or housing cost shown to a user is retrieved from a real source and
displayed with that source and an "as-of" date. When a field cannot be verified for a
college, it is shown as *"Unavailable — verify on official site"* with a link. The system
never blanks a field in a way that implies a value, and never guesses one.

---

## 2. Objective & the "80% informed-decision" target

**Goal.** A student who uses the app should be able to make an *informed* decision and
meet their objective **≥ 80% of the time.**

We refuse to leave "informed" vague. We define it measurably and instrument it.

### 2.1 Definition — Decision Confidence Score (DCS)

For a given search, define per shortlisted college a **Field Coverage Ratio**:

```
FieldCoverage(college) = (# of A–I fields VERIFIED from a real source)
                         / (# of A–I fields the student marked as "matters to me")
```

A field is **VERIFIED** when it carries a `source_url` + `as_of` date and is not flagged
`*_estimate_only` or `*_source_not_found`. A student reaches a **confident decision** when:

1. They have ≥ 3 colleges in their shortlist, **and**
2. Each shortlisted college has `FieldCoverage ≥ 0.8` on the student's *priority* fields
   (the A–I fields they explicitly ranked as important), **and**
3. Every *priority* field that is unverified is explicitly surfaced as a gap with a
   verify-link (so the student knows what they still don't know — an honest 0.8, not a
   hidden one).

**The 80% objective** = ≥ 80% of students who run a real search and engage with results
reach state (1)+(2)+(3) within the session (or knowingly stop with documented gaps). This
is a *coverage-and-honesty* target, not an accuracy guarantee about the world — we promise
the student knows what they know and what they don't.

### 2.2 How we track it

The response model carries the raw material for DCS today: each `CollegeProgram` has
`sources[]`, `fees.source_url`, and structured fields that are either present or absent.
We add (see §6) per-field provenance and a `data_quality_flags[]` list. The frontend
computes `FieldCoverage` from the response; the backend logs an anonymized
`decision_confidence` event with `priority_fields`, `verified_count`, `gap_count`, and
`shortlist_size`. §15 turns this into the post-launch validation metric.

---

## 3. Goals and non-goals

**Goals**
- Course-driven discovery: course in → colleges out, ranked by geographic tier.
- One standardized A–I field set for every college, so results are genuinely comparable.
- Real-time aggregation over real sources with caching for freshness and cost.
- Provenance on every fact; honest, linked gaps where data is missing.
- A decision-support layer that tells the student what's missing to decide.

**Non-goals (stated plainly)**
- **Not a comparator.** Comparison of 2–3 colleges is an optional secondary view. IA,
  positioning, and copy must read as a *search/aggregation* tool.
- **No manufactured data.** We never invent a figure to fill a cell. A missing fee is
  shown as missing, with a link — never as `$0`, "N/A," or a plausible-looking guess.
- **Not an application manager.** We don't submit applications, store SSNs/financial-aid
  PII, or act as a CRM.
- **Not a ranking authority.** We surface ranking *context* with its source label; we do
  not publish our own prestige ranking as if it were fact. **Proprietary ranks (U.S. News,
  etc.) are never scraped/stored** — they're copyrighted and licence-encumbered. Instead the
  KG carries (a) `ranking_score`: a **transparent composite** from open Scorecard outcomes
  (grad rate 0.35 · earnings 0.30 · selectivity 0.20 · value 0.15), with the per-factor
  breakdown shown and labelled "not U.S. News"; (b) `rankings[]`: **verify-links only**
  (U.S. News / Niche search URLs — no value copied); and (c) `carnegie_classification`: the
  **free, official Carnegie tier** (R1/R2…) loaded via `make load-carnegie`, shown when
  present. A literal U.S. News *number* is supported but **gated**: `licensed_rankings[]` is
  served only when `RANKINGS_LICENSED=1` (operator holds a licence; rows loaded into the
  `kg_rankings` table via `make load-rankings`, which records the licence id for audit).
  Default off → no proprietary rank value is ever emitted without a licence.
- **Not international (MVP).** US institutions only at launch (see §16 assumptions).

---

## 4. User personas & key user stories

| Persona | Situation | Primary need |
|---------|-----------|--------------|
| **Maya — HS senior** | 17, knows she wants "Computer Science," lives in Berkeley, CA, cost-sensitive | "Show me CS programs near me first, then the rest, with real tuition for a CA resident." |
| **Devon — community-college transfer** | Wants to finish a BS, residency in TX, needs transfer-friendly programs | "Which in-state and adjacent-state colleges take transfers and what are the credit/term requirements?" |
| **Priya — international applicant** | Abroad, targeting MS Data Science, no US residency | "Show out-of-state/international tuition, TOEFL/GRE requirements, and deadlines — and tell me what you couldn't verify." |
| **A parent** | Paying, wants the sourced numbers to trust the shortlist | "Where did this $50,400 come from, and as of when?" |

**Representative user stories**
- *As Maya,* I enter "Computer Science" and my city/state, and I get colleges grouped
  **local city → home state → adjacent states → rest of USA**, each with the same finer
  details, so I'm comparing apples to apples.
- *As any user,* when a college's housing cost can't be verified, I see
  *"Housing — unavailable, verify on official site →"* rather than a blank or a guess.
- *As a parent,* I can click any number and reach the official source page and its as-of
  date.
- *As Maya,* after browsing, I can select 2–3 colleges to see a focused side-by-side
  *(secondary)* — but I never had to start there.

---

## 5. Core features (each with acceptance criteria)

### 5.1 Course-driven search
Input is a course/program string (free text with fuzzy normalization); output is colleges
offering it. Implemented: `POST /api/course-search` → `CourseSearchService.search()`
(`app/course_search/service.py`).

**Acceptance criteria**
- A common course ("Computer Science", "MS Data Science") returns ≥ 1 college per
  available tier when data exists.
- Course matching tolerates synonyms/aliases (`aliases[]` on each program;
  `rapidfuzz.token_set_ratio` in ranking).
- A broad/ambiguous query ("Engineering") returns grouped interpretations or a
  clarification prompt rather than a noisy dump (see §9, §16-Q).
- No result is fabricated: every returned college traces to a discovery source.

### 5.2 Geographic tiering
Results expand outward from the user: **local city → home state → adjacent state(s) →
rest of USA.** Implemented in `app/course_search/ranking.py`.

- **Location capture:** the request takes `city`, `state`, `home_state` (optional). MVP
  asks the user explicitly via the Course Finder form (no silent geolocation). Roadmap:
  optional browser geolocation → reverse-geocode to city/state with consent; ZIP entry as
  a precise alternative.
- **Distance:** Haversine (`_distance`) from an inferred user point; `nearby` tier =
  within `nearby_radius_miles` (default 150).
- **Adjacency:** a US **state-adjacency map** (`NEIGHBORING_STATES`) defines the
  "adjacent states" ring. MVP ships a partial map (high-traffic states); §14 tracks
  completing all 50 + DC.

**Acceptance criteria**
- With `city=Berkeley, state=CA`, Berkeley-area programs appear in **Nearby**, other CA
  programs in **Home state**, AZ/NV/OR programs in **Nearby home states**, the rest in
  **Best in the USA**.
- A program never appears in two tiers (`used_ids` dedupe across tiers).
- With no location supplied, tiers gracefully collapse to a single national list and
  `location_used = "No location supplied"`.

### 5.3 Per-college finer-detail aggregation (A–I field set)
Every college is standardized on the **same** fields so results are comparable.

| Group | Fields | Carried in model today |
|-------|--------|------------------------|
| A. Identity | college, location, program name, degree level, accreditation, intake terms | `college_name, city, state, course_name, degree`; accreditation/intake → roadmap |
| B. Acceptance | GPA/%, test reqs & cutoffs, prerequisites, acceptance rate, deadlines | `admission_factors[]`, `required_papers[]`; rate/deadlines → roadmap |
| C. Structure | duration, #terms, credits, core vs electives, specializations, internship, delivery | `semester_plan[]`, `curriculum_summary`, `delivery` |
| D. Tuition & fees | per year/semester, total, mandatory fees, residency tier | `fees{in_state, out_of_state, mandatory_fees, notes, source_url}` |
| E. Financial aid | scholarships, merit/need, assistantships, net cost | roadmap (College Scorecard `NPT4_*`) |
| F. Housing | on-campus availability & cost, off-campus rent, meal plans | roadmap |
| G. Commuting | distance from user, transit, parking, neighborhood | `distance_miles` (computed); transit/parking → roadmap |
| H. Outcomes | grad/retention rate, placement, avg starting salary, employers | roadmap (Scorecard `C150_4`, `MD_EARN_WNE_*`) |
| I. Other | class size, student-faculty ratio, facilities, rankings | `ranking_score` (context only), `decision_factors[]` |

**Acceptance criteria**
- Every college in a result exposes the *same* field keys; missing values are present as
  `null` + a quality flag, never silently dropped.
- Each populated D/E/H field carries a `source_url` and as-of date.
- Unverifiable fields render as "Unavailable — verify on official site →".

### 5.4 Optional 2–3 college comparison (secondary)
After browsing, the user may select 2–3 colleges from results for a focused side-by-side
on the A–I fields. Reuses the existing comparison-card patterns
(`ui/src/components/ComparisonResult.tsx`).

**Acceptance criteria**
- Comparison is reachable only *from* a result set (never a landing entry point).
- It shows the same A–I rows for each college, gaps included.
- It adds no new data — it re-renders already-aggregated, already-sourced facts.

### 5.5 Counselor / decision-support layer
Converts verified facts into guidance: priorities, tradeoffs, and *what's missing to
decide*. Implemented as `build_guidance()` (`synthesis.py`) returning `guidance[]`.

**Acceptance criteria**
- Guidance is generated only from verified facts + flags; it never asserts an unsourced
  number (enforced by prompt rules, §7.4).
- Guidance explicitly names the top unverified priority fields ("Before you apply,
  confirm Berkeley's current cost of attendance and CS admission rate").
- Guidance includes concrete next steps (questions to ask admissions, net-price
  calculator links).

---

## 6. Data model / entity schema (with provenance baked in)

Authoritative models live in `app/models.py`. Core entities:

```
CollegeProgram
  program_id, course_name, aliases[], college_name, city, state, lat, lon,
  ranking_score(1–100, context only), degree, delivery,
  overview, curriculum_summary,
  semester_plan: [SemesterPlan{term, focus, courses[]}],
  required_papers[], admission_factors[],
  fees: ProgramFees{in_state_tuition?, out_of_state_tuition?, mandatory_fees?,
                    notes, source_url},
  decision_factors[],
  sources: [ProgramSource{label, url}]

MoneyAmount{amount, currency=USD, label}      # every figure is labeled
RankedProgram{program, distance_miles?, match_reason}
ProgramTier{tier ∈ [nearby|home_state|nearby_home_states|best_usa], title, programs[]}
CourseSearchResponse{request_id, query, location_used, tiers[], guidance[]}
```

**Provenance extension (specified, partially built).** To enforce no-manufactured-data at
the field level, every aggregated claim attaches evidence:

```
ProgramEvidence
  claim_type ∈ [identity|admissions|curriculum|fees|aid|housing|outcomes|ranking|general]
  claim: str
  source_url: str
  source_label: str
  as_of: date            # the page's stated date or fetch date
  confidence ∈ [high|medium|low]

# Added to CollegeProgram (non-breaking, additive):
  evidence: ProgramEvidence[]
  data_quality_flags: str[]    # see below
  last_checked_at: datetime
```

**Data-quality flags** (internal, optionally surfaced as caution chips):
`missing_curriculum_source`, `missing_fee_source`, `fee_estimate_only`,
`catalog_page_not_found`, `unofficial_ranking_source`, `program_name_ambiguous`,
`requires_manual_review`.

**Design rule:** a field with no backing `ProgramEvidence` (or an `*_estimate_only` flag)
is treated as *unverified* by the DCS calculation in §2 and rendered as a gap in §10.

---

## 7. Data sourcing & ingestion strategy

### 7.1 Real, citable sources (named, with field mapping)

| Source | Real? | Provides | Maps to A–I |
|--------|-------|----------|-------------|
| **U.S. Dept. of Education — College Scorecard API** | Yes (public API, free key) | Institution identity, acceptance rate, net price (`NPT4_PUB/PRIV`), grad rate (`C150_4`), median earnings (`MD_EARN_WNE_*`), in/out-of-state tuition (`TUITIONFEE_IN/OUT`) | A, B(rate), D, E, H |
| **IPEDS** (NCES) | Yes (bulk datasets) | Enrollment, retention, student-faculty ratio, residency tuition, housing/board charges | C, D, F, I |
| **Official `.edu` program/catalog pages** | Yes | Curriculum, semester structure, core vs electives, specializations, prerequisites, deadlines | A, B, C |
| **Official bursar / financial-aid `.edu` pages** | Yes | Current tuition, mandatory fees, cost of attendance, net-price calculator | D, E |
| **Official housing `.edu` pages** | Yes | On-campus availability & cost, meal plans | F |
| **Web search (discovery)** — DuckDuckGo HTML today; pluggable | Yes | *Discovery only* — find the official pages above | (discovery) |
| **Transit/geocoding API** (roadmap) | Yes | Commute distance, transit options | G |

> **Honesty note:** Scorecard/IPEDS reliably cover D/E/H at the *institution* level but
> **not** per-program curriculum or per-program deadlines. Those come only from `.edu`
> pages. Where a per-program figure can't be verified, we show the institution-level value
> *labeled as such* (e.g., "institution-wide net price, not CS-specific") or mark it
> unavailable — we do **not** present an institution number as a program number.

### 7.2 The "10 searches at once" orchestration
A real-time multi-agent pipeline, already wired (`service.py`), one agent per concern:

```
CourseSearchRequest
  → Query Planner        (planner.py: normalize course, build geo plan, pick tiers)
  → Program Discovery    (discovery.py: OfficialWebDiscovery + StaticFallback, async)
  → Page Reader          (reader.py: extract A/B/C facts from official pages + evidence)
  → Cost & Aid           (cost.py: tuition/fees/net-price, residency tiers + evidence)
  → Ranking & Grouping   (ranking.py: dedupe, distance, tiers, match reasons)
  → Counselor Synthesis  (synthesis.py: guidance from verified facts only)
  → CourseSearchResponse (tiers[] + guidance[], evidence attached)
```

Discovery providers run concurrently (`asyncio.gather(..., return_exceptions=True)`); a
failing provider degrades to a logged `AgentRun(status="error")` without sinking the
request. Each agent emits an `AgentRun{agent, status, message, count}` for observability
and partial-result handling.

### 7.3 Caching, freshness, rate limits, legality
- **Freshness cadence:** Scorecard/IPEDS refreshed on their annual cycle; `.edu`
  fee/deadline pages re-checked on a **7–30 day** TTL; discovery results cached **1–7
  days**. Every cached fact stores `last_checked_at`; the UI shows the as-of date.
- **Cache layers:** (1) per-request memo, (2) search-result cache (1–7d), (3) source-page
  cache (7–30d), (4) extracted-fact cache invalidated on page-content change. MVP =
  in-memory; production = Postgres/pgvector (already in the stack from the field side).
- **Rate limits & ToS:** respect `robots.txt`; throttle per-domain; cache aggressively to
  avoid hammering `.edu` sites; keep excerpts short and link out (no bulk reproduction of
  copyrighted catalog text). Use official APIs (Scorecard) in preference to scraping
  wherever the API has the field.
- **Fallback when a field is unavailable:** emit the relevant `*_source_not_found` /
  `*_estimate_only` flag, leave the field `null`, and render the verify-link. Never fill.

### 7.4 Prompt-level guard (counselor synthesis)
Synthesis/guidance prompts receive **only validated structured facts + flags**, never raw
user input, and are instructed: *do not state any tuition figure, deadline, GPA, or rate
not present in the provided facts; for any priority field marked unverified, tell the
student to confirm it on the official source.* This is the LLM-side enforcement of
no-manufactured-data (mirrors the no-salary-in-summary rule already used on the field
side).

---

## 8. System architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  BROWSER — React + Vite + TypeScript + Tailwind                    │
│  CourseFinder.tsx ─ search form (course, city, state, home_state) │
│     │  results grouped by tier · per-college A–I cards · gaps      │
│     │  select 2–3 → ComparisonResult.tsx (secondary)              │
└─────┼──────────────────────────────────────────────────────────────┘
      │ POST /api/course-search        (FastAPI, app/main.py)
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  FastAPI backend                                                   │
│   /api/course-search → CourseSearchService.search()                │
│     Planner → Discovery(async) → Reader → Cost&Aid → Ranking →     │
│     Synthesis → CourseSearchResponse                               │
│   slowapi rate limit · request_id (UUID4) · structlog JSON logs    │
└─────┬───────────────────────┬───────────────────────┬─────────────┘
      │                       │                       │
      ▼                       ▼                       ▼
┌─────────────┐   ┌───────────────────────┐   ┌──────────────────────┐
│ Cache/Store │   │ External integrations │   │ Static fallback KB   │
│ in-mem MVP →│   │ • College Scorecard   │   │ data/college_        │
│ Postgres +  │   │ • IPEDS datasets      │   │   programs.yaml      │
│ pgvector    │   │ • .edu pages (reader) │   │ (seed + offline dev) │
│ source-page │   │ • Web search (disc.)  │   │ shares CollegeProgram│
│ + fact cache│   │ • Geocoding (roadmap) │   │ response model       │
└─────────────┘   └───────────────────────┘   └──────────────────────┘
```

The **static YAML fallback** (`StaticFallbackDiscoveryProvider`) shares the exact same
`CollegeProgram`/`CourseSearchResponse` models as the live path, so the UI and tests are
identical whether data is live or seeded — and the API still returns useful results when
live providers fail.

---

## 9. Search & ranking logic

1. **Course matching.** Normalize the query (`build_search_plan`). For the KG, a
   **course→CIP alias map** (`cip_aliases.resolve_course`) maps what students type — "CS",
   "comp sci", "data analytics", "nursing" — to canonical CIP codes; matching then prefers
   a **CIP hit** (precise, on `kg_offerings.cip`) and falls back to title token matching, so
   abbreviations resolve and an imperfect/absent code degrades gracefully. The resolved
   interpretation is surfaced in `guidance` ("Interpreted 'cs' as Computer Science (CIP
   11.07)"). For other providers, match `course_name` + `aliases[]` via `token_set_ratio`.
2. **De-duplication.** `_dedupe_candidates` keys on `program_id`, keeping the
   highest-confidence candidate when multiple providers find the same program.
3. **Geographic tier ordering.** Compute Haversine distance from an inferred user point
   (`_infer_user_point`: exact city match → else state centroid). Assign tiers in order
   **nearby (≤ radius) → home_state → nearby_home_states (adjacency map) → best_usa**, with
   `used_ids` preventing cross-tier duplication.
4. **Within-tier relevance score** (`_ranked`):
   `score = ranking_score + distance_bonus + token_set_ratio(query, course_name)/10`,
   where `distance_bonus = max(0, 30 − distance/20)`. Tier caps: nearby/home/adjacent = 3,
   best_usa = 4 (tunable).
5. **Match reasons & caveats.** Each `RankedProgram` carries a human `match_reason`
   ("within ~150 miles of your location", "in your home state (CA)"). Incomplete-evidence
   programs carry caveats from their quality flags.

> Ranking uses `ranking_score` only as *context*, surfaced with a source label — never
> presented as an authoritative prestige verdict (non-goal §3).

---

## 10. UX flows & screen-by-screen

Positioning everywhere reads **"search & aggregate,"** not "compare."

1. **Search (entry).** `CourseFinder.tsx`: one prominent course field (placeholder
   "e.g., Computer Science, MS Data Science"), plus city / state / home-state inputs with
   a one-line rationale ("so we can show colleges near you first"). Primary CTA: **Search
   colleges**.
2. **Results by tier.** Four labeled sections in expanding-ring order: **Nearby colleges →
   In your home state → Nearby home states → Best in the USA.** Each college renders as a
   card with the standardized A–I summary, distance, and a **source/as-of footer**.
   Unverified priority fields render inline as *"Unavailable — verify on official site
   →."* A persistent **Decision Confidence** strip shows coverage on the student's
   priority fields.
3. **College detail.** Full A–I expansion: semester plan, required papers, admission
   factors, full fee breakdown by residency tier, housing, outcomes — each with its
   source link and date. A "What to verify before applying" panel lists the gaps.
4. **Select to compare (secondary).** Checkbox on 2–3 result cards reveals a **Compare**
   affordance — clearly secondary, reachable only from results.
5. **Comparison view.** `ComparisonResult.tsx`: same A–I rows side-by-side, gaps included;
   no new data fetched.
6. **Decision support.** The `guidance[]` panel: prioritized tradeoffs, the named missing
   fields, and next steps (questions for admissions, net-price calculator links).

**Cross-product seam:** a field deep-dive page (`DeepDivePage.tsx`) offers "Find colleges
for this" → opens Course Finder pre-filled with the field's typical major.

---

## 11. Accuracy & trust design

- **Source labels everywhere.** Every figure shows its `source_label` and links to
  `source_url`; `MoneyAmount.label` forces a human description on every number
  ("Estimated annual tuition and fees for nonresidents").
- **As-of dates.** Each fact shows `as_of` / `last_checked_at`; stale facts (TTL exceeded)
  get a "may be outdated — re-checking" badge.
- **Honest gaps.** Missing = explicit "Unavailable, verify →" chip, never a blank, `$0`,
  or a guess.
- **Conflicting data.** When two official sources disagree (e.g., catalog vs. bursar fee),
  show both with their labels/dates and flag `requires_manual_review`; prefer the bursar
  for fees, the catalog for curriculum, Scorecard/IPEDS for outcomes — and say which won.
- **Estimate labeling.** Any non-program-specific value (institution-wide net price used as
  a proxy) is badged "institution-wide, not program-specific."
- **No-LLM-numbers rule.** Generated guidance never originates a figure (§7.4).

---

## 12. Tech stack recommendation

| Layer | Choice | Rationale | Alternatives |
|-------|--------|-----------|--------------|
| Backend | **FastAPI + Python 3.13** | Async orchestration fits the multi-agent fan-out; already in repo | Node/Express |
| Models/validation | **Pydantic v2** | Validates every fact at the boundary; provenance enforced in-schema | dataclasses-only |
| LLM | **Claude (Anthropic SDK)** — `claude-sonnet-4-6` for synthesis/extraction; `claude-opus-4-8` where reasoning depth matters | Committed to Claude; structured output + strong instruction-following for the no-numbers guard | — |
| Discovery | **Pluggable `SearchBackend`** — Tavily (default), Brave, Apify (Google Search Scraper via REST), Claude `web_search`, or DuckDuckGo (keyless), selected by `SEARCH_PROVIDER` | Tavily/Brave are fast single-call search APIs (cheap, no Anthropic tokens) — the right fit for the per-college pinpoint search. Apify gives Google-grade coverage but is heavier/slower. Claude `web_search` is token-heavy (429s on low tiers). DuckDuckGo is keyless but rate-limited | each other |
| Structured data | **College Scorecard API + IPEDS** | Real, free, federal; covers D/E/H at institution level | — |
| Cache/store | **In-memory → Postgres + pgvector** | pgvector already present for the field side; reuse for fact cache + semantic course matching at scale | Redis for hot cache |
| Frontend | **React + Vite + TS + Tailwind** | Already in repo; fast iteration | — |
| Geocoding (roadmap) | **A real geocoding API / ZIP seed data** | Accurate nearby search without hard-coded college coords | — |

---

## 13. MVP scope vs. later phases

The course-search engine mirrors the phased plan in `docs/dynamic-course-search-design.md`:

| Phase | Scope | Status |
|-------|-------|--------|
| **1 — Dynamic skeleton** | Multi-agent boundary, static YAML fallback, shared response model, tests | **Done** |
| **2 — Official page discovery** | Web-search provider, `.edu` filtering, candidate confidence | **Done** |
| **3 — Page reading & extraction** | Fetch official pages; extract A/B/C facts; attach `ProgramEvidence`; quality flags | **Done** (opt-in `COURSE_READ_PAGES=1`) |
| **3.5 — Offline knowledge graph** | Pre-aggregate the finite US institution set from College Scorecard into `kg_*` tables (offline ETL), serve course→colleges as an **instant** local lookup with real coords + provenance; new `KnowledgeGraphDiscoveryProvider` | **Done** (`COURSE_SEARCH_MODE=kg`; sample store offline, Postgres via `make build-kg`) |
| **4 — Cost & aid + Scorecard/IPEDS** | Extend KG with bursar net-price + IPEDS housing; residency tiers; live reader fills program-level detail on demand | Next |
| **5 — UI evidence & filters** | Source/as-of badges, gap chips, public/private + cost + distance filters, compare-shortlist, DCS strip | Planned |
| **6 — Production hardening** | Postgres cache, per-IP rate limits, provider budgets, monitoring, manual-review queue | Planned |

**MVP definition (ship-worthy):** Phases 1–4 for a handful of high-demand courses (CS, Data
Science, Nursing, Business) with real Scorecard cost/outcomes + `.edu`-extracted
curriculum, full provenance, honest gaps, geographic tiering, and the guidance panel.
Comparison + advanced filters follow in Phase 5.

---

## 14. Risks, edge cases, mitigations

| Risk / edge case | Impact | Mitigation |
|------------------|--------|-----------|
| **Data gaps** — no official page found for a program | Sparse cards | Quality flags + "verify →" links; fall back to Scorecard institution data, clearly labeled; exclude rather than invent |
| **Source ToS / scraping** | Legal/ethical | Prefer Scorecard API; respect robots; throttle per-domain; short excerpts + links only |
| **Stale fees/deadlines** | Wrong decision | 7–30d TTL; as-of dates; "re-checking" badge; bursar-wins conflict rule |
| **Location accuracy** | Wrong tiering | Ask explicitly (no silent geo); ZIP option; state centroid fallback; never guess city |
| **Incomplete adjacency map** | Missing adjacent-state tier | §5.2 ships partial; tracked task to complete all 50 + DC; absent state → that ring empty, not wrong |
| **Colleges with no online data** | Can't include | Exclude with a logged reason; never fabricate to fill a tier |
| **Ambiguous course ("Engineering")** | Noisy results | Clarification prompt / grouped interpretations (§9) |
| **Provider/LLM failure** | Partial results | `asyncio.gather(return_exceptions=True)`, per-agent `AgentRun`, partial-success responses, timeouts |
| **Cost/latency of live search** | Slow, expensive | Four-layer cache; provider budgets; mock/offline mode for dev |
| **KG enrichment rate limits** | Reading the shown colleges' program pages fans out N parallel calls; Claude `web_search` is input-token-heavy, so a low Anthropic tier (e.g. 30K tok/min) 429s even at low concurrency | Run enrichment after ranking (only ~10-13 colleges); cache per (college,course); `KG_ENRICH_CONCURRENCY` cap; **use a dedicated search API (Brave/Tavily) for the pinpoint discovery so Anthropic tokens are spent on extraction only** — or raise the Anthropic tier |
| **LLM inventing a number** | Breaks core rule | Facts-only prompt context + explicit no-numbers instruction (§7.4) + post-gen validation |

---

## 15. Success metrics & validating the 80% objective

**Primary (the objective).** % of engaged searches reaching a **confident decision** per
§2.1 (shortlist ≥ 3, priority-field `FieldCoverage ≥ 0.8`, gaps disclosed). Target ≥ 80%.
Computed from logged `decision_confidence` events.

**Supporting metrics**
- **Field-verification rate:** share of displayed A–I fields that are VERIFIED (sourced +
  fresh) vs. flagged unavailable — directly measures the no-manufactured-data promise.
- **Provenance completeness:** % of shown figures carrying `source_url` + `as_of` (target
  100%).
- **Tier coverage:** % of searches returning ≥ 1 college in each *applicable* tier.
- **Source freshness:** median age of displayed fee/deadline facts vs. TTL.
- **Funnel:** search → detail-view → shortlist → (optional) compare.
- **Qualitative gate (carried from the field side):** the real proximate test user can
  reach a confident shortlist in one session and says the sourced numbers are something
  they'd show a parent.

---

## 16. Open questions & assumptions

**Assumptions made (per working-style rule)**
1. **US-only, English, undergraduate-first** at MVP; grad programs (MS Data Science) are
   in-model but content-seeded later.
2. **Location is user-provided** (form), not silently geolocated, for trust + accuracy.
3. **Discovery starts keyless** (DuckDuckGo HTML) and swaps to a paid search API behind the
   same Protocol when volume/quality demands.
4. **Institution-level Scorecard/IPEDS values are acceptable proxies** for E/H *only when
   labeled as institution-wide*; program-specific fields require `.edu` extraction.
5. **`ranking_score` is context, not verdict** — sourced and labeled, never authoritative.
6. The **static YAML KB is seed/fallback/dev data**, not the product's data source; the
   product is a real-time aggregator (core constraint).

**Open questions (non-blocking, tracked)**
- ~~Which search provider for official-page discovery?~~ **Resolved:** pluggable
  `SearchBackend` (DuckDuckGo / Brave / Tavily / Claude `web_search`) via `SEARCH_PROVIDER`.
  Sub-question: production default — Claude `web_search` works off the existing Anthropic
  key but is slow (~60–90s/query); Brave/Tavily are faster but need their own key.
- **Live-result geocoding.** ~~Discovered *live-web* programs are stamped with the user's
  coords, so out-of-area colleges land in the wrong tier.~~ **Resolved for the KG path**
  (`COURSE_SEARCH_MODE=kg`): the knowledge graph carries each institution's real Scorecard
  lat/lon, so tiering is correct (verified: Berkeley 0 mi, MIT 2680 mi). Still open *only*
  for the raw live-web discovery path — prefer KG-first, and have the live reader enrich KG
  hits rather than geocode raw web results.
- Geocoding strategy: third-party API vs. ZIP→coordinate seed — and is ZIP required for
  accurate nearby search?
- Should ranking blend an external ranking signal, or stay purely internal heuristic +
  Scorecard outcomes?
- Clarification UX for broad course queries: inline disambiguation vs. grouped result
  sections?
- Save/share a shortlist — and does that imply lightweight accounts (and the privacy
  scope that comes with them)?
- Complete the `NEIGHBORING_STATES` map to all 50 states + DC (currently partial).

---

## Appendix A — API surface (implemented)

```
POST /api/course-search    → CourseSearchResponse{request_id, query, location_used,
                                                  tiers[], guidance[]}
  body: CourseSearchRequest{course_query, city?, state?, home_state?}

# Sibling field-exploration endpoints (shared app):
GET  /api/fields           GET  /health
POST /api/compare          POST /api/explore        POST /api/direct
POST /api/cache/clear
```

## Appendix B — Source-to-field provenance map (quick reference)

```
A Identity      → Scorecard (school.*) + official .edu program page
B Acceptance    → .edu admissions page (deadlines/prereqs) + Scorecard ADM_RATE
C Structure     → .edu catalog/bulletin (curriculum, terms, credits)  [LLM-extracted]
D Tuition/fees  → .edu bursar page (current) + Scorecard TUITIONFEE_IN/OUT (proxy)
E Financial aid → Scorecard NPT4_* (net price) + .edu financial-aid page
F Housing       → .edu housing page + IPEDS room/board charges
G Commuting     → computed distance (Haversine) + geocoding/transit API (roadmap)
H Outcomes      → Scorecard C150_4 (grad), MD_EARN_WNE_* (earnings)
I Other         → IPEDS (student-faculty ratio) + ranking context (labeled)
```
