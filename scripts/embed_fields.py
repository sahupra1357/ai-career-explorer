"""Embed all STEM field entries into pgvector. Idempotent — skips if count matches."""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.kb import FieldStore

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

DIMENSIONS = {
    "plain_english": lambda f: f.plain_english,
    "personality_fit": lambda f: f.personality_fit.fit_description,
    "career_outcomes": lambda f: (
        f"{', '.join(f.career_outcomes.common_roles[:3])}. "
        f"{f.career_outcomes.outlook}"
    ),
    "sub_areas": lambda f: ". ".join(
        f"{s.name}: {s.description}" for s in f.sub_areas[:3]
    ),
    "undergrad_path": lambda f: (
        f"Key courses: {', '.join(f.undergrad_path.key_courses[:5])}. "
        f"Common majors: {', '.join(f.undergrad_path.common_majors[:3])}"
    ),
}


async def embed_all(database_url: str) -> None:
    fields_file = os.getenv("FIELDS_FILE", "data/fields.yaml")
    store = FieldStore()
    store.load(fields_file)
    fields = store.all()
    expected = len(fields) * len(DIMENSIONS)

    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=5)
    client = AsyncOpenAI()

    try:
        count = await pool.fetchval("SELECT COUNT(*) FROM field_embeddings")
        if count == expected:
            print(f"Already embedded: {count} rows. Nothing to do.")
            return

        print(f"Embedding {len(fields)} fields × {len(DIMENSIONS)} dimensions = {expected} rows...")

        for field in fields:
            for dim_name, extractor in DIMENSIONS.items():
                content = extractor(field)
                response = await client.embeddings.create(input=content, model=EMBED_MODEL)
                embedding = response.data[0].embedding
                assert len(embedding) == EMBED_DIM, f"Expected {EMBED_DIM} dims, got {len(embedding)}"

                await pool.execute(
                    """
                    INSERT INTO field_embeddings (field_id, dimension, content, embedding, model_name)
                    VALUES ($1, $2, $3, $4::vector, $5)
                    ON CONFLICT (field_id, dimension) DO UPDATE
                        SET content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            model_name = EXCLUDED.model_name
                    """,
                    field.field_id, dim_name, content, str(embedding), EMBED_MODEL,
                )
            print(f"  embedded: {field.field_id}")

        final_count = await pool.fetchval("SELECT COUNT(*) FROM field_embeddings")
        print(f"Done. {final_count} rows in field_embeddings.")
    finally:
        await pool.close()
        await client.close()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(embed_all(db_url))
