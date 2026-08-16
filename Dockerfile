# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-slim AS ui-builder
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY --from=ui-builder /ui/dist ./ui/dist

EXPOSE 8000

# Run migrations, then serve. Failing migrations must fail the container: `&&` stops the
# chain, the container exits non-zero, and the platform keeps the previous deploy live.
# Baked into the image on purpose — it cannot be forgotten the way an env var can, and it
# runs on every host (Render, compose, plain `docker run`) without extra configuration.
CMD ["sh", "-c", "python scripts/db_migrate.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
