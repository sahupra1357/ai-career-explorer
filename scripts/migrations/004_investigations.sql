-- Migration 004: persistent cache for college program investigations.
-- A subagent's investigation of (college domain, course) — the extracted curriculum/
-- admissions findings + the program-page URL — so repeat searches reuse prior agent work
-- instead of re-running LLM + web calls. TTL-bounded by investigated_at.

CREATE TABLE IF NOT EXISTS kg_investigations (
    id               SERIAL PRIMARY KEY,
    domain           TEXT NOT NULL,        -- college's registrable domain (e.g. upenn.edu)
    course_norm      TEXT NOT NULL,        -- lowercased course name
    program_page_url TEXT,
    findings         JSONB NOT NULL,       -- the report: curriculum/semester/admissions/...
    investigated_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (domain, course_norm)
);

CREATE INDEX IF NOT EXISTS kg_investigations_lookup ON kg_investigations (domain, course_norm);
