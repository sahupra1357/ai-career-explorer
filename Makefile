.PHONY: install dev dev-live dev-kg dev-ui dev-real dev-db dev-phase2 migrate embed build-kg load-carnegie load-rankings new-migration test validate-kb add-field clear-cache lint build run run-live run-mock

# ── Setup ─────────────────────────────────────────────────────────────────────

install:
	python3.13 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "Done. Copy .env.example to .env and set your ANTHROPIC_API_KEY."
	@echo "  cp .env.example .env"

# ── Development ───────────────────────────────────────────────────────────────

# Start the FastAPI backend with MOCK_CLAUDE enabled (no API cost, instant responses).
dev:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run: cp .env.example .env"; exit 1; \
	fi
	MOCK_CLAUDE=1 .venv/bin/uvicorn app.main:app --reload --port 8000

# Start the backend with live official .edu course discovery.
dev-live:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run: cp .env.example .env"; exit 1; \
	fi
	COURSE_SEARCH_MODE=live MOCK_CLAUDE=1 .venv/bin/uvicorn app.main:app --reload --port 8000

# Start the backend serving course search from the pre-built knowledge graph (instant).
# Offline by default (sample store); set KG_BACKEND=postgres + DATABASE_URL for the DB.
dev-kg:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run: cp .env.example .env"; exit 1; \
	fi
	COURSE_SEARCH_MODE=kg MOCK_CLAUDE=1 .venv/bin/uvicorn app.main:app --reload --port 8000

# Start the React frontend (run in a second terminal alongside make dev)
dev-ui:
	cd ui && npm run dev

# Start with real Claude (costs money — use for final testing only)
dev-real:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run: cp .env.example .env"; exit 1; \
	fi
	MOCK_CLAUDE=0 .venv/bin/uvicorn app.main:app --reload --port 8000

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	.venv/bin/pytest tests/ -v

test-watch:
	.venv/bin/pytest tests/ -v --tb=short -f

# ── Knowledge base ────────────────────────────────────────────────────────────

# Interactive wizard to add a new STEM field entry
add-field:
	.venv/bin/python scripts/add_field.py

# Validate all field entries against the Pydantic schema
validate-kb:
	.venv/bin/python scripts/add_field.py --validate

# Print a blank YAML template to stdout for copy-paste editing
field-template:
	.venv/bin/python scripts/add_field.py --template

# ── Phase 2: Database ─────────────────────────────────────────────────────────

# Start Postgres via Docker Compose (requires Docker Desktop running)
dev-db:
	@if ! docker info > /dev/null 2>&1; then \
		echo "Error: Docker is not running. Start Docker Desktop and try again."; exit 1; \
	fi
	docker compose up -d
	@echo "Waiting for Postgres to be healthy..."
	@until docker compose exec db pg_isready -U dev -d career_explorer > /dev/null 2>&1; do sleep 1; done
	@echo "Postgres is ready."

# Start backend with Phase 2 features enabled (real pgvector — needs make dev-db first)
dev-phase2:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run: cp .env.example .env"; exit 1; \
	fi
	MOCK_EMBEDDINGS=0 .venv/bin/uvicorn app.main:app --reload --port 8000

# Apply all pending SQL migrations
migrate:
	@if [ -z "$$DATABASE_URL" ]; then \
		if [ -f .env ]; then \
			export $$(grep -v '^#' .env | grep DATABASE_URL | xargs); \
		fi; \
	fi
	.venv/bin/python scripts/db_migrate.py

# Embed all STEM fields into pgvector (idempotent; skips if already complete)
embed: migrate
	@if [ -z "$$DATABASE_URL" ]; then \
		if [ -f .env ]; then \
			export $$(grep -v '^#' .env | grep -E 'DATABASE_URL|OPENAI_API_KEY' | xargs); \
		fi; \
	fi
	.venv/bin/python scripts/embed_fields.py

# Build the college knowledge graph into Postgres (offline sample by default; idempotent).
# Live Scorecard slice: make build-kg ARGS="--source api --states CA,OR --cip 11.07,30.70"
# 2. national CS + Data Science build (replaces sample rows in Postgres):
# make build-kg ARGS="--source api --states CA,OR,WA,NV,AZ,TX,NY,MA,IL,GA --cip 11.07,30.70"
# (or all states — just extend the --states list)
build-kg: migrate
	@if [ -z "$$DATABASE_URL" ]; then \
		if [ -f .env ]; then \
			export $$(grep -v '^#' .env | grep -E 'DATABASE_URL|SCORECARD_API_KEY' | xargs); \
		fi; \
	fi
	.venv/bin/python scripts/build_kg.py $(ARGS)

# Load Carnegie Classification (free) into kg_colleges (run build-kg first).
# Usage: make load-carnegie FILE=carnegie.csv [ARGS="--year 2021 --col-class BASIC2021"]
load-carnegie: migrate
	@if [ -z "$$DATABASE_URL" ]; then \
		if [ -f .env ]; then export $$(grep -v '^#' .env | grep DATABASE_URL | xargs); fi; \
	fi
	.venv/bin/python scripts/load_carnegie.py --file $(FILE) $(ARGS)

# Load LICENSED provider ranks (e.g. U.S. News) into kg_rankings. Only with licensed data.
# Usage: make load-rankings FILE=usnews.csv LICENSE="USN Academic Insights #1234"
load-rankings: migrate
	@if [ -z "$$DATABASE_URL" ]; then \
		if [ -f .env ]; then export $$(grep -v '^#' .env | grep DATABASE_URL | xargs); fi; \
	fi
	.venv/bin/python scripts/load_rankings.py --file $(FILE) --license "$(LICENSE)" $(ARGS)

# Create a new numbered migration file (usage: make new-migration NAME=002_add_sessions)
new-migration:
	@if [ -z "$(NAME)" ]; then \
		echo "Usage: make new-migration NAME=002_add_sessions"; exit 1; \
	fi
	@touch scripts/migrations/$(NAME).sql
	@echo "Created scripts/migrations/$(NAME).sql"

# ── Runtime helpers ───────────────────────────────────────────────────────────

# Clear the in-memory LRU cache (dev server must be running)
clear-cache:
	curl -s -X POST http://localhost:8000/api/cache/clear | python3 -m json.tool

# ── Build (production) ────────────────────────────────────────────────────────

# Build the React frontend into ui/dist (picked up by FastAPI static file serving)
build:
	cd ui && npm run build
	@echo "Built. Run 'make run' to serve the full app on :8000."

# Serve the built React app through FastAPI. Requires ui/dist from `make build`.
run:
	@if [ ! -d ui/dist ]; then \
		echo "Error: ui/dist not found. Run: make build"; exit 1; \
	fi
	.venv/bin/uvicorn app.main:app --port 8000

# Serve the built app without loading curated course-search fallback data.
# Course search uses live official .edu discovery only.
run-live:
	@if [ ! -d ui/dist ]; then \
		echo "Error: ui/dist not found. Run: make build"; exit 1; \
	fi
	COURSE_SEARCH_MODE=live .venv/bin/uvicorn app.main:app --port 8000

# Serve the built app locally without real Claude/embedding infrastructure.
run-mock:
	@if [ ! -d ui/dist ]; then \
		echo "Error: ui/dist not found. Run: make build"; exit 1; \
	fi
	MOCK_CLAUDE=1 MOCK_EMBEDDINGS=1 ANTHROPIC_API_KEY=test-key .venv/bin/uvicorn app.main:app --port 8000

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	.venv/bin/python -m py_compile app/models.py
	@echo "Syntax OK"
