"""TTL-backed session store for explore graph state."""
from __future__ import annotations

import uuid
from typing import Any

from cachetools import TTLCache

_SESSION_TTL = 30 * 60  # 30 minutes
_MAX_SESSIONS = 1000

_store: TTLCache = TTLCache(maxsize=_MAX_SESSIONS, ttl=_SESSION_TTL)

ExploreState = dict[str, Any]


def new_session() -> str:
    session_id = str(uuid.uuid4())
    _store[session_id] = _empty_state()
    return session_id


def get_session(session_id: str) -> ExploreState | None:
    return _store.get(session_id)


def save_session(session_id: str, state: ExploreState) -> None:
    _store[session_id] = state


def delete_session(session_id: str) -> None:
    _store.pop(session_id, None)


def _empty_state() -> ExploreState:
    return {
        "messages": [],
        "user_interests": [],
        "clarification_turns": 0,
        "recommended_fields": [],
        "status": "intake",
    }
