# syntax=docker/dockerfile:1.7
#
# Buddi — canonical production image.
# Track 1 / Step 1: single entry point is `backend.api:app` on port 8001.
# HEALTHCHECK + non-root user land in Track 2 Step 11 (DO-02, DO-03).

########################
# Build stage
########################
FROM python:3.11-slim AS builder

WORKDIR /app

# Build-only system deps. `curl` retained for a follow-up HEALTHCHECK in Track 2.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

########################
# Final stage
########################
FROM python:3.11-slim

WORKDIR /app

# Runtime libs only (curl kept for HEALTHCHECK hook in Track 2).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# ---- Environment ----
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001 \
    PYTHONPATH=/app

EXPOSE 8001

# Canonical entry point. `--reload` is intentionally absent; dev reload lives in
# `start_dev.py`. Workers scale via the APP_WORKERS env var.
#
# DB-01 / DB-02: alembic migrations are applied on every container start so the
# schema (and the pgvector extension) are guaranteed to be present before
# uvicorn binds. Fail-closed: if the migration fails, the container exits
# non-zero and the orchestrator will refuse to route traffic.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${APP_WORKERS:-1} --proxy-headers --forwarded-allow-ips='*'"]
