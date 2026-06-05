# Dynamic Course Search Design

## Goal

Replace the static `data/college_programs.yaml` dependency with a dynamic, evidence-backed course search workflow.

When a student searches for a course, the application should discover relevant college programs, rank them by location and quality, read official college pages where possible, and return decision-grade information:

- nearby college offerings
- home-state offerings
- nearby home-state offerings
- best options in the USA
- course structure / semester structure
- required papers and admissions materials
- tuition, fees, and cost notes
- official source links for verification
- counselor guidance that helps the student make an informed decision

The system must clearly separate verified facts from inferred guidance.

## Current State

The new Course Finder screen calls:

```txt
POST /api/course-search
```

The backend currently loads curated program data from:

```txt
data/college_programs.yaml
```

This was useful for the first working version, but it cannot scale to arbitrary courses, locations, or current college website updates.

## Target Architecture

```txt
User request
  -> Course Search API
  -> Query Planner
  -> Multi-agent research pipeline
  -> Evidence extraction
  -> Fact validation
  -> Ranking and grouping
  -> Counselor synthesis
  -> Structured API response with source links
```

## Multi-Agent Pipeline

### 1. Query Planner Agent

Responsibility:

- Normalize the user’s course query.
- Interpret location fields: city, state, home state, ZIP if added later.
- Generate search tasks for the other agents.
- Decide whether the search needs undergraduate, graduate, certificate, online, or transfer-specific results.

Inputs:

- `course_query`
- `city`
- `state`
- `home_state`
- optional future fields: `degree_level`, `budget`, `student_profile`, `distance_preference`

Outputs:

- normalized course name
- search intent
- geographic search plan
- target tiers to fill

### 2. Program Discovery Agent

Responsibility:

- Find candidate colleges offering the requested course.
- Prefer official college or department pages.
- Avoid relying only on aggregator pages.
- Return candidate URLs and basic metadata.

Search tiers:

- nearby colleges
- in home state
- nearby home states
- best in USA

Candidate source priority:

1. Official department or program page
2. Official catalog / bulletin page
3. Official admissions page
4. Official financial aid / tuition page
5. Trusted public ranking/reference page, only for ranking context

Outputs:

- candidate college name
- program name
- official program URL
- catalog URL if found
- tuition/cost URL if found
- confidence score

### 3. Page Reader Agent

Responsibility:

- Read the official pages selected by Program Discovery.
- Extract structured facts from the page text.
- Keep links attached to every major extracted fact.

Extracted facts:

- degree name
- department / school
- curriculum overview
- semester or year-by-year structure
- required core courses
- electives or specialization tracks
- admission requirements
- required documents / papers
- tuition and fees
- application deadlines if available
- accreditation or special program notes

Outputs:

- raw extracted facts
- quote-safe snippets or short evidence notes
- source URLs
- freshness metadata if available

### 4. Cost and Aid Agent

Responsibility:

- Find current cost-of-attendance and tuition pages.
- Separate tuition, mandatory fees, housing, books, and estimated total cost when possible.
- Identify resident vs nonresident cost.
- Encourage net-price calculator use.

Outputs:

- in-state tuition
- out-of-state tuition
- mandatory fees
- total cost estimate if available
- source URL
- cost warning notes

### 5. Ranking Agent

Responsibility:

- Group and sort candidates into the requested tiers.
- Deduplicate programs found by multiple agents.
- Balance proximity, residency, program fit, evidence quality, and national strength.

Ranking signals:

- distance from user location
- same-state residency advantage
- neighboring-state availability
- program relevance to query
- official-source confidence
- curriculum completeness
- ranking/reputation signal when available
- admissions competitiveness
- cost accessibility

Outputs:

- ranked `ProgramTier[]`
- match reason per program
- caveats where evidence is incomplete

### 6. Counselor Synthesis Agent

Responsibility:

- Convert verified facts into student-facing guidance.
- Explain tradeoffs clearly.
- Avoid making unsupported claims.
- Highlight what the student should verify before applying.

Outputs:

- program decision factors
- shortlist guidance
- questions to ask admissions
- next-step recommendations

## Backend Design

### New Modules

Proposed files:

```txt
app/course_search/
  __init__.py
  api.py
  models.py
  planner.py
  discovery.py
  reader.py
  cost.py
  ranking.py
  synthesis.py
  cache.py
  sources.py
```

The current `app/course_finder.py` can either be migrated into this package or kept temporarily as a fallback.

### API Endpoint

Keep the current endpoint:

```txt
POST /api/course-search
```

Request:

```json
{
  "course_query": "Computer Science",
  "city": "Berkeley",
  "state": "CA",
  "home_state": "CA"
}
```

Future request fields:

```json
{
  "degree_level": "undergraduate",
  "max_distance_miles": 150,
  "budget_preference": "cost_sensitive",
  "include_private": true,
  "include_public": true,
  "student_profile": {
    "gpa_band": "3.7-4.0",
    "test_optional": true,
    "interests": ["AI", "software engineering"]
  }
}
```

Response should remain compatible with the current Course Finder UI:

```txt
CourseSearchResponse
  request_id
  query
  location_used
  tiers[]
  guidance[]
```

Add evidence metadata later without breaking the UI:

```txt
program.evidence[]
program.confidence
program.last_checked_at
program.data_quality_flags[]
```

## Data Model Changes

### Program Evidence

Add an evidence object so every major claim can point back to a source.

```txt
ProgramEvidence
  claim_type: curriculum | admissions | fees | deadline | ranking | general
  claim: string
  source_url: string
  source_label: string
  extracted_at: datetime
  confidence: high | medium | low
```

### Data Quality Flags

Possible flags:

- `missing_curriculum_source`
- `missing_fee_source`
- `fee_estimate_only`
- `catalog_page_not_found`
- `unofficial_ranking_source`
- `program_name_ambiguous`
- `requires_manual_review`

These flags should be visible internally and optionally surfaced in the UI as caution notes.

## Search and Source Strategy

### Official Site Search

Preferred queries:

```txt
site:.edu "Computer Science" "undergraduate" "curriculum"
site:.edu "Computer Science" "degree requirements"
site:.edu "Computer Science" "tuition" "cost of attendance"
```

For a specific college:

```txt
site:college.edu "Computer Science" "degree requirements"
site:college.edu "Computer Science" "catalog"
site:college.edu "cost of attendance" "undergraduate"
```

### Location Search

The system needs a geocoding layer for real nearby search.

Options:

- use a geocoding API
- use ZIP/city-to-coordinate seed data
- start with state/city inference and add precise coordinates later

Do not rely on hard-coded college coordinates long term.

### Ranking Sources

Ranking should not be based on a single commercial list.

Possible signals:

- official accreditation
- public university flagship status
- research activity
- reputable ranking APIs/pages if available
- graduation outcomes when accessible
- program-specific reputation

Ranking claims must be labeled as ranking context, not verified curriculum facts.

## Caching Strategy

Dynamic search will be slower and may cost money. Add caching.

Cache keys:

```txt
course_query_normalized
city
state
home_state
degree_level
```

Cache layers:

1. Request cache: short-lived, avoids repeated calls in one session.
2. Search result cache: 1-7 days.
3. Source page cache: 7-30 days, with source URL and fetched timestamp.
4. Extracted fact cache: invalidated when source page content changes.

Cache storage options:

- start with in-memory cache for development
- move to Postgres for production

## Failure Behavior

The API should still return useful results when some agents fail.

Examples:

- If tuition page is missing, return curriculum details with a `missing_fee_source` flag.
- If nearby results are sparse, fill national tier and explain the gap.
- If official page cannot be read, exclude the program unless another official page confirms it.
- If multiple programs match the course name, ask for clarification or return grouped interpretations.

Never invent semester structures, fees, deadlines, or requirements.

## UI Design Changes

The current Course Finder UI can remain mostly intact.

Add later:

- source confidence indicators
- “last checked” date
- caution flags
- filters for public/private, in-state cost, distance, selectivity
- compare selected colleges
- save shortlist
- ask follow-up question about a specific program

For each program card, keep:

- college name
- degree/program name
- location and distance
- curriculum structure
- required papers
- admissions factors
- fees
- official source links
- counselor read

## Security and Compliance

- Do not scrape sites in ways that violate robots or terms.
- Avoid excessive repeated requests to college websites.
- Keep source page excerpts short.
- Cite links; do not reproduce large copyrighted page sections.
- Treat all admissions and cost information as “verify before applying.”
- Do not store sensitive student data without explicit need.

## Implementation Phases

### Phase 1: Dynamic Search Skeleton

Status: Implemented

Tasks:

- [x] Create `app/course_search/` package.
- [x] Move current static search into a fallback provider.
- [x] Add planner, ranking, and response orchestration.
- [x] Add interfaces for discovery providers.
- [x] Add page reader provider interface.
- [x] Add cost provider interface.
- [x] Keep `data/college_programs.yaml` as fallback data.

Acceptance criteria:

- `/api/course-search` still works if dynamic search is disabled.
- Static fallback and dynamic provider share the same response model.
- Tests cover fallback behavior.

### Phase 2: Official Page Discovery

Status: Implemented

Tasks:

- [x] Add web search provider abstraction.
- [x] Discover official `.edu` program pages.
- [x] Filter out weak/unofficial sources.
- [x] Return candidate programs with confidence scores.

Acceptance criteria:

- Search for a common course returns official program URLs.
- Results include source confidence.
- Unofficial-only results are flagged or excluded.

### Phase 3: Page Reading and Extraction

Status: Implemented (opt-in via `COURSE_READ_PAGES=1`)

Tasks:

- [x] Fetch selected official pages (`reader._fetch_page_text`, httpx + HTML→text).
- [x] Extract curriculum and admissions facts (`reader.extract_program_facts`, Claude,
      no-manufactured-data prompt guard; cost extraction deferred to Phase 4).
- [x] Attach evidence to extracted facts (`ProgramEvidence` on `CollegeProgram`).
- [x] Add data quality flags (`missing_curriculum_source`, `catalog_page_not_found`,
      `requires_manual_review`, …) for honest gaps.

Acceptance criteria:

- Program cards show extracted curriculum and fees from source pages.
- Every extracted section has at least one source URL.
- Missing facts are clearly marked, not invented.

### Phase 4: Multi-Agent Orchestration

Status: Not started

Tasks:

- Run discovery, page reading, cost lookup, ranking, and synthesis agents.
- Add parallel execution where safe.
- Add timeouts and partial-result handling.
- Log per-agent status for debugging.

Acceptance criteria:

- Endpoint returns partial but useful results when one agent fails.
- Logs show each agent’s input, output count, and failure reason.
- Slow searches do not block indefinitely.

### Phase 5: UI Evidence and Filters

Status: Not started

Tasks:

- Show confidence and last-checked metadata.
- Add source badges.
- Add public/private and cost filters.
- Add compare-shortlist interaction.

Acceptance criteria:

- User can see which facts are verified.
- User can filter results without rerunning the whole search.
- UI remains readable on mobile and desktop.

### Phase 6: Production Hardening

Status: Not started

Tasks:

- Add persistent cache.
- Add rate limits per user/IP.
- Add provider usage budgets.
- Add monitoring and error dashboards.
- Add manual review path for low-confidence results.

Acceptance criteria:

- Repeated searches reuse cached source facts.
- Provider failures are visible in logs.
- Cost and latency are bounded.

## Open Questions

- Which search provider should be used for official page discovery?
- Should the app support only undergraduate programs first?
- Should ZIP code be required for accurate nearby search?
- Should ranking use external rankings, internal heuristics, or both?
- Should users be able to save a shortlist?
- Should the system ask clarifying questions when the course query is broad, such as “Engineering”?

## Tracking Checklist

- [x] Choose search provider. → pluggable `SearchBackend` (DuckDuckGo/Brave/Tavily/Claude).
- [x] Choose geocoding strategy. → real institution lat/lon from College Scorecard via the
      offline knowledge graph (`app/course_search/knowledge_graph.py`, `scripts/build_kg.py`).
- [x] Define discovery provider interface.
- [x] Create dynamic course search package.
- [x] Preserve static YAML fallback.
- [x] Implement official page discovery.
- [x] Implement source page fetching.
- [x] Implement fact extraction.
- [ ] Implement cost extraction.
- [x] Add evidence metadata to response.
- [x] Add data quality flags.
- [ ] Add cache layer.
- [ ] Add partial-result behavior.
- [ ] Add UI confidence/source indicators.
- [ ] Add tests for dynamic provider mocks.
- [ ] Add production rate limits and usage logging.
