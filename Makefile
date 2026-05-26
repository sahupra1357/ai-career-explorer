.PHONY: install dev test validate-kb add-field clear-cache lint

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
# Open a second terminal and start the React frontend separately once it exists.
dev:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run: cp .env.example .env"; exit 1; \
	fi
	MOCK_CLAUDE=1 .venv/bin/uvicorn app.main:app --reload --port 8000

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

# ── Runtime helpers ───────────────────────────────────────────────────────────

# Clear the in-memory LRU cache (dev server must be running)
clear-cache:
	curl -s -X POST http://localhost:8000/api/cache/clear | python3 -m json.tool

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	.venv/bin/python -m py_compile app/models.py
	@echo "Syntax OK"
