-- Migration 002: Knowledge-graph tables for course-driven college discovery
-- Pre-aggregated, sourced slice of College Scorecard. Built offline by scripts/build_kg.py.
-- The "graph" is colleges (nodes) + offerings (College-OFFERS-Program edges); state
-- adjacency lives in code (NEIGHBORING_STATES). This is the denormalized serving view.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS kg_colleges (
    unitid            INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    city              TEXT NOT NULL,
    state             CHAR(2) NOT NULL,
    lat               DOUBLE PRECISION NOT NULL,
    lon               DOUBLE PRECISION NOT NULL,
    control           TEXT,
    level             TEXT,
    url               TEXT,
    admission_rate    DOUBLE PRECISION,
    tuition_in_state  INTEGER,
    tuition_out_state INTEGER,
    avg_net_price     INTEGER,
    grad_rate         DOUBLE PRECISION,
    median_earnings   INTEGER,
    source            TEXT NOT NULL,        -- provenance: where the row came from
    as_of             INTEGER NOT NULL,     -- provenance: dataset year
    updated_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS kg_colleges_state_idx ON kg_colleges (state);

-- College-OFFERS-Program edges (one row per program a college reports offering).
CREATE TABLE IF NOT EXISTS kg_offerings (
    id          SERIAL PRIMARY KEY,
    unitid      INTEGER NOT NULL REFERENCES kg_colleges (unitid) ON DELETE CASCADE,
    cip         TEXT NOT NULL,              -- CIP code, e.g. 11.07
    title       TEXT NOT NULL,              -- program title, e.g. Computer Science
    course_norm TEXT NOT NULL,              -- lowercased title for matching
    UNIQUE (unitid, cip)
);

-- Trigram index makes course matching (the `%` similarity operator) fast.
CREATE INDEX IF NOT EXISTS kg_offerings_course_trgm_idx
    ON kg_offerings USING gin (course_norm gin_trgm_ops);
