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
    FieldSummary,
    NotFound,
    PartialNotFound,
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

    yield  # app runs here

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
