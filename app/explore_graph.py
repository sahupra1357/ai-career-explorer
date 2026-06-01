"""LangGraph explore graph: intake → clarify → recommend."""
from __future__ import annotations

import os
from typing import Any, TypedDict

import structlog
from anthropic import AsyncAnthropic
from langgraph.graph import END, StateGraph

log = structlog.get_logger()

_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
_MAX_CLARIFY = 2


class ExploreGraphState(TypedDict):
    messages: list[dict]
    user_interests: list[str]
    clarification_turns: int
    recommended_fields: list[dict]
    status: str
    # runtime-only — not persisted to session store
    pool: Any
    field_ids: list[str]


def _user_text(state: ExploreGraphState) -> str:
    for m in reversed(state["messages"]):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


async def intake_node(state: ExploreGraphState) -> dict:
    """Parse initial interests from the user's first message."""
    raw = _user_text(state)
    client = AsyncAnthropic()
    try:
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract a concise list of the student's stated interests, "
                        "hobbies, or strengths from this message. Return only a "
                        "JSON array of short phrases, e.g. [\"building things\", "
                        "\"math\", \"helping people\"]. No other text.\n\n"
                        f"<user_interest>{raw}</user_interest>"
                    ),
                }
            ],
        )
        import json
        interests = json.loads(response.content[0].text.strip())
    except Exception:
        interests = [raw[:200]]
    finally:
        await client.close()

    return {
        "user_interests": interests,
        "status": "clarifying" if len(interests) < 2 else "clarifying",
    }


async def clarify_node(state: ExploreGraphState) -> dict:
    """Ask one targeted follow-up question to sharpen field matching."""
    interests = state.get("user_interests", [])
    turns = state.get("clarification_turns", 0)

    if turns >= _MAX_CLARIFY or len(interests) >= 3:
        return {"status": "recommend"}

    client = AsyncAnthropic()
    try:
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=256,
            system=(
                "You help high school students discover STEM careers. "
                "Ask one short, friendly follow-up question to better understand "
                "their interests. Do not list options. One question only."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Student interests so far: {', '.join(interests)}.\n"
                        "Ask one clarifying question."
                    ),
                }
            ],
        )
        reply = response.content[0].text.strip()
    except Exception:
        reply = "What subjects do you enjoy most in school?"
    finally:
        await client.close()

    return {
        "messages": state.get("messages", []) + [{"role": "assistant", "content": reply}],
        "clarification_turns": turns + 1,
        "status": "clarifying",
    }


async def recommend_node(state: ExploreGraphState) -> dict:
    """Embed interests, run pgvector search, ask Claude to explain recommendations."""
    interests = state.get("user_interests", [])
    pool = state.get("pool")
    field_ids = state.get("field_ids", [])

    from app.embeddings import embed_text, search_similar_fields
    from app.kb import store as kb_store

    query = " ".join(interests)
    embedding = await embed_text(query)

    search_dims = ["plain_english", "personality_fit", "career_outcomes"]
    results = await search_similar_fields(pool, embedding, search_dims, top_k=5)

    fields = {f.field_id: f for f in kb_store.all()}

    recommended: list[dict] = []
    for r in results:
        fid = r["field_id"]
        if fid in fields:
            recommended.append({
                "field_id": fid,
                "name": fields[fid].name,
                "score": r["score"],
            })

    field_names = [r["name"] for r in recommended[:3]]
    client = AsyncAnthropic()
    try:
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=(
                "You help high school students discover STEM careers. "
                "Be warm, encouraging, and specific. 3-4 sentences max."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"A student with these interests: {', '.join(interests)}.\n"
                        f"Based on their profile, these STEM fields match best: "
                        f"{', '.join(field_names)}.\n"
                        "Write a friendly explanation of why these fields fit them. "
                        "Mention each field by name."
                    ),
                }
            ],
        )
        reply = response.content[0].text.strip()
    except Exception:
        reply = (
            f"Based on your interests, I think you'd enjoy exploring: "
            f"{', '.join(field_names)}. Each of these fields matches what you described!"
        )
    finally:
        await client.close()

    for r in recommended:
        r["reason"] = reply

    return {
        "messages": state.get("messages", []) + [{"role": "assistant", "content": reply}],
        "recommended_fields": recommended,
        "status": "complete",
    }


def _route_after_intake(state: ExploreGraphState) -> str:
    if state.get("clarification_turns", 0) >= _MAX_CLARIFY:
        return "recommend"
    return "clarify"


def _route_after_clarify(state: ExploreGraphState) -> str:
    if state.get("status") == "recommend":
        return "recommend"
    return END


def build_graph() -> Any:
    graph = StateGraph(ExploreGraphState)
    graph.add_node("intake", intake_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("recommend", recommend_node)

    graph.set_entry_point("intake")
    graph.add_conditional_edges("intake", _route_after_intake, {"clarify": "clarify", "recommend": "recommend"})
    graph.add_conditional_edges("clarify", _route_after_clarify, {"recommend": "recommend", END: END})
    graph.add_edge("recommend", END)

    return graph.compile()


_compiled_graph = None


def get_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
