-- Migration 003: Ranking signals for the knowledge graph
--   • Carnegie Classification (free, official) — a prestige TIER, stored on the college.
--   • Licensed provider ranks (e.g. U.S. News) — actual rank VALUES, served only when
--     RANKINGS_LICENSED=1. Kept in a separate table so licensed data is opt-in and auditable.

ALTER TABLE kg_colleges ADD COLUMN IF NOT EXISTS carnegie      TEXT;
ALTER TABLE kg_colleges ADD COLUMN IF NOT EXISTS carnegie_year INTEGER;

CREATE TABLE IF NOT EXISTS kg_rankings (
    id         SERIAL PRIMARY KEY,
    unitid     INTEGER NOT NULL REFERENCES kg_colleges (unitid) ON DELETE CASCADE,
    provider   TEXT NOT NULL,          -- e.g. "U.S. News"
    rank       INTEGER NOT NULL,       -- the licensed numeric rank
    list_name  TEXT,                   -- e.g. "National Universities"
    year       INTEGER NOT NULL,
    source_url TEXT,
    license    TEXT NOT NULL,          -- licence holder / agreement id, for audit
    loaded_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (unitid, provider, list_name, year)
);

CREATE INDEX IF NOT EXISTS kg_rankings_unitid_idx ON kg_rankings (unitid);
