"""AI Career Exploration — FastAPI application."""

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import structlog.stdlib
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .kb import store
from .models import (
    CompareRequest,
    CompareSuccess,
    DirectRequest,
    ExploreRequest,
    ExploreResponse,
    FieldSummary,
    NotFound,
    PartialNotFound,
    RecommendedField,
    normalize_slug,
)
from .summarize import clear_cache, generate_summary

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger()


# ── Startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Fail loudly if API key is missing (unless mocked)
    if not os.getenv("ANTHROPIC_API_KEY") and os.getenv("MOCK_CLAUDE") != "1":
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. "
            "Add it to .env or set MOCK_CLAUDE=1 for local dev. "
            "Get a key at https://console.anthropic.com"
        )

    # 2. Load and validate the knowledge base
    fields_file = os.getenv("FIELDS_FILE", "data/fields.yaml")
    store.load(fields_file)
    log.info("kb_loaded", path=fields_file, count=len(store))

    # 3. Phase 2: connect pgvector (skip when MOCK_EMBEDDINGS=1)
    app.state.db_pool = None
    if os.getenv("MOCK_EMBEDDINGS") != "1":
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            try:
                import asyncpg
                app.state.db_pool = await asyncpg.create_pool(
                    database_url, min_size=2, max_size=10
                )
                log.info("db_pool_ready")
            except Exception as exc:
                log.warning("db_pool_failed", error=str(exc))
        else:
            log.warning("database_url_missing", hint="set DATABASE_URL in .env or use MOCK_EMBEDDINGS=1")

    # 4. Phase 2: compile LangGraph explore graph
    from .explore_graph import get_graph
    app.state.explore_graph = get_graph()
    log.info("explore_graph_ready")

    yield  # app runs here

    if app.state.db_pool is not None:
        await app.state.db_pool.close()
    log.info("shutdown")


# ── App + middleware ───────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])

app = FastAPI(
    title="AI Career Exploration",
    description="STEM field comparison for high school students",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/fields", response_model=list[FieldSummary])
@limiter.limit("30/minute")
async def list_fields(request: Request):
    """Return all known field_ids and display names (used to populate autocomplete)."""
    return store.list()


@app.post("/api/compare")
@limiter.limit("10/minute")
async def compare_fields(body: CompareRequest, request: Request):
    request_id = str(uuid.uuid4())

    found = []
    not_found_ids = []
    not_found_suggestions: dict[str, list[str]] = {}

    for fid in body.fields:
        entry = store.get(fid)
        if entry:
            found.append(entry)
        else:
            not_found_ids.append(fid)
            not_found_suggestions[fid] = store.fuzzy_candidates(fid)

    # All fields unknown
    if not found:
        first = not_found_ids[0]
        return JSONResponse(
            status_code=404,
            content=NotFound(
                request_id=request_id,
                message=f"I don't have structured data on '{first}' yet.",
                suggestions=not_found_suggestions.get(first, []),
            ).model_dump(),
        )

    # Some found, some not
    if not_found_ids:
        return JSONResponse(
            status_code=422,
            content=PartialNotFound(
                request_id=request_id,
                found=[f.field_id for f in found],
                not_found=not_found_ids,
                suggestions=not_found_suggestions,
            ).model_dump(),
        )

    # All found — generate summary
    field_dicts = [f.model_dump() for f in found]
    summary = await generate_summary(field_dicts, request_id)

    log.info(
        "compare_ok",
        request_id=request_id,
        fields=[f.field_id for f in found],
        summary_status="ready" if summary else "error",
    )

    return CompareSuccess(
        request_id=request_id,
        fields=found,
        comparison_fields_used=[f.field_id for f in found],
        comparison_summary=summary,
        summary_status="ready" if summary else "error",
    )


@app.post("/api/cache/clear")
async def cache_clear():
    """Clear the in-memory comparison summary cache (dev helper)."""
    cleared = clear_cache()
    log.info("cache_cleared", entries=cleared)
    return {"cleared": cleared}


@app.post("/api/explore", response_model=ExploreResponse)
@limiter.limit("20/minute")
async def explore(body: ExploreRequest, request: Request):
    """Multi-turn explore conversation via LangGraph."""
    from .explore_graph import ExploreGraphState
    from .session_store import get_session, new_session, save_session

    mock = os.getenv("MOCK_EMBEDDINGS") == "1"
    pool = request.app.state.db_pool
    if not mock and pool is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "db_unavailable",
                "message": (
                    "pgvector is not connected. Start Postgres with 'make dev-db', "
                    "run 'make embed', then restart the server. "
                    "Or set MOCK_EMBEDDINGS=1 in .env for zero-infra dev."
                ),
            },
        )

    session_id = body.session_id
    if session_id:
        saved = get_session(session_id)
        if saved is None:
            fresh_id = new_session()
            return JSONResponse(
                status_code=404,
                content={
                    "error": "session_expired",
                    "session_id": fresh_id,
                    "message": "Session expired. Starting fresh.",
                },
            )
        state: ExploreGraphState = {**saved, "pool": pool, "field_ids": [f.field_id for f in store.all()]}
    else:
        session_id = new_session()
        state = {
            "messages": [],
            "user_interests": [],
            "clarification_turns": 0,
            "recommended_fields": [],
            "status": "intake",
            "pool": pool,
            "field_ids": [f.field_id for f in store.all()],
        }

    state["messages"].append({"role": "user", "content": body.message})

    graph = request.app.state.explore_graph
    result = await graph.ainvoke(state)

    reply = ""
    for m in reversed(result.get("messages", [])):
        if m.get("role") == "assistant":
            reply = m["content"]
            break

    serializable = {
        "messages": result.get("messages", []),
        "user_interests": result.get("user_interests", []),
        "clarification_turns": result.get("clarification_turns", 0),
        "recommended_fields": result.get("recommended_fields", []),
        "status": result.get("status", "intake"),
    }
    save_session(session_id, serializable)

    recommended_fields = [
        RecommendedField(
            field_id=r["field_id"],
            name=r["name"],
            reason=r.get("reason", ""),
            score=r.get("score"),
        )
        for r in result.get("recommended_fields", [])
    ]

    status = result.get("status", "intake")
    if status not in ("intake", "clarifying", "complete"):
        status = "clarifying"

    log.info("explore_ok", session_id=session_id, status=status, recommended=len(recommended_fields))
    return ExploreResponse(
        session_id=session_id,
        reply=reply or "Tell me more about what interests you!",
        status=status,
        recommended_fields=recommended_fields,
    )


@app.post("/api/direct")
@limiter.limit("10/minute")
async def direct(body: DirectRequest, request: Request):
    """Generate a structured deep-dive for a single STEM field."""
    from .direct import generate_deep_dive

    result = await generate_deep_dive(body.field_id)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": f"Field '{body.field_id}' not found."},
        )
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "fields_loaded": len(store)}


# ── Static files (production — React build) ───────────────────────────────────

_UI_DIR = Path(__file__).parent.parent / "ui" / "dist"

if _UI_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_UI_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes."""
        return FileResponse(_UI_DIR / "index.html")
