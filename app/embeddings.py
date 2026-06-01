"""OpenAI embedding + pgvector similarity search with MOCK_EMBEDDINGS stub."""
from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
_MOCK = os.getenv("MOCK_EMBEDDINGS") == "1"


async def embed_text(text: str) -> list[float]:
    if _MOCK:
        return [0.0] * EMBED_DIM

    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    try:
        response = await client.embeddings.create(input=text, model=EMBED_MODEL)
        return response.data[0].embedding
    finally:
        await client.close()


async def search_similar_fields(
    pool: "asyncpg.Pool",
    query_embedding: list[float],
    dimensions: list[str],
    top_k: int = 5,
) -> list[dict]:
    """Return top_k field_ids ranked by cosine similarity across given dimensions."""
    if _MOCK:
        from app.kb import store

        fields = store.all()
        sample = random.sample(fields, min(top_k, len(fields)))
        return [{"field_id": f.field_id, "score": round(random.uniform(0.6, 0.95), 3)} for f in sample]

    rows = await pool.fetch(
        """
        SELECT field_id, AVG(1 - (embedding <=> $1::vector)) AS score
        FROM field_embeddings
        WHERE dimension = ANY($2::text[])
        GROUP BY field_id
        ORDER BY score DESC
        LIMIT $3
        """,
        str(query_embedding),
        dimensions,
        top_k,
    )
    return [{"field_id": r["field_id"], "score": float(r["score"])} for r in rows]
