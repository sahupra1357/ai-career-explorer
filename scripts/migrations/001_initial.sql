-- Migration 001: Initial Phase 2 schema
-- Creates pgvector extension, field_embeddings table, and schema_migrations tracker

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    version TEXT UNIQUE NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS field_embeddings (
    id SERIAL PRIMARY KEY,
    field_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    model_name TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(field_id, dimension)
);

-- hnsw index: correct at small row counts; ivfflat needs ~3000+ rows
CREATE INDEX IF NOT EXISTS field_embeddings_embedding_idx
    ON field_embeddings USING hnsw (embedding vector_cosine_ops);
