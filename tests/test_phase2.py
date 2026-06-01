"""Phase 2 tests: embeddings mock, session store, explore endpoint, direct endpoint."""
import os
import pytest
from httpx import ASGITransport, AsyncClient


# ── Embeddings mock ────────────────────────────────────────────────────────────

def test_embed_text_returns_zero_vector():
    from app.embeddings import embed_text, EMBED_DIM
    import asyncio
    vec = asyncio.get_event_loop().run_until_complete(embed_text("test"))
    assert len(vec) == EMBED_DIM
    assert all(v == 0.0 for v in vec)


def test_search_similar_fields_mock_returns_results():
    from app.embeddings import search_similar_fields, EMBED_DIM
    import asyncio
    vec = [0.0] * EMBED_DIM
    results = asyncio.get_event_loop().run_until_complete(
        search_similar_fields(None, vec, ["plain_english"], top_k=3)
    )
    assert len(results) <= 3
    for r in results:
        assert "field_id" in r
        assert "score" in r


# ── Session store ──────────────────────────────────────────────────────────────

def test_session_lifecycle():
    from app.session_store import new_session, get_session, save_session, delete_session

    sid = new_session()
    assert get_session(sid) is not None

    save_session(sid, {"status": "clarifying", "messages": [], "user_interests": ["math"],
                       "clarification_turns": 1, "recommended_fields": []})
    state = get_session(sid)
    assert state["status"] == "clarifying"
    assert state["user_interests"] == ["math"]

    delete_session(sid)
    assert get_session(sid) is None


def test_new_session_returns_unique_ids():
    from app.session_store import new_session
    ids = {new_session() for _ in range(10)}
    assert len(ids) == 10


# ── /api/explore endpoint ──────────────────────────────────────────────────────

@pytest.fixture
def app_with_mocks():
    from app.main import app
    from app.explore_graph import get_graph
    app.state.db_pool = None
    app.state.explore_graph = get_graph()
    return app


@pytest.mark.asyncio
async def test_explore_new_session(app_with_mocks):
    async with AsyncClient(transport=ASGITransport(app=app_with_mocks), base_url="http://test") as client:
        res = await client.post("/api/explore", json={"message": "I love building robots and math"})
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "reply" in data
    assert data["status"] in ("intake", "clarifying", "complete")


@pytest.mark.asyncio
async def test_explore_returns_session_id(app_with_mocks):
    async with AsyncClient(transport=ASGITransport(app=app_with_mocks), base_url="http://test") as client:
        res = await client.post("/api/explore", json={"message": "I enjoy chemistry and helping people"})
    assert res.status_code == 200
    sid = res.json()["session_id"]
    assert len(sid) == 36  # UUID format


@pytest.mark.asyncio
async def test_explore_expired_session_returns_404(app_with_mocks):
    import uuid
    fake_sid = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app_with_mocks), base_url="http://test") as client:
        res = await client.post("/api/explore", json={"message": "hello", "session_id": fake_sid})
    assert res.status_code == 404
    body = res.json()
    assert "session_id" in body


# ── /api/direct endpoint ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_direct_unknown_field(app_with_mocks):
    async with AsyncClient(transport=ASGITransport(app=app_with_mocks), base_url="http://test") as client:
        res = await client.post("/api/direct", json={"field_id": "totally-made-up-field-xyz"})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_direct_known_field_mock(app_with_mocks):
    from app.kb import store
    fields = store.all()
    if not fields:
        pytest.skip("No fields loaded")
    first_id = fields[0].field_id
    async with AsyncClient(transport=ASGITransport(app=app_with_mocks), base_url="http://test") as client:
        res = await client.post("/api/direct", json={"field_id": first_id})
    assert res.status_code == 200
    data = res.json()
    assert data["field_id"] == first_id
    assert len(data["sections"]) == 5
    for s in data["sections"]:
        assert s["title"]
        assert s["content"]
