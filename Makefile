.PHONY: install dev dev-ui dev-real dev-db dev-phase2 migrate embed new-migration test validate-kb add-field clear-cache lint build

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
	@echo "Built. Run 'uvicorn app.main:app' to serve the full app on :8000."

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	.venv/bin/python -m py_compile app/models.py
	@echo "Syntax OK"
