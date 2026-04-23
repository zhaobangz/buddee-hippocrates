# syntax=docker/dockerfile:1.7
#
# Buddi — canonical production image.
# Track 1 / Step 1: single entry point is `backend.api:app` on port 8001.
#
# Re-audit (April 21) follow-ups applied here:
#   - DO-02 (FIXED): HEALTHCHECK now probes /api/health on the loopback port
#     every 30s. The container is marked unhealthy after 3 consecutive
#     failures so orchestrators (Cloud Run, k8s) can restart it.
#   - DO-03 (FIXED): the process runs as a dedicated non-root user (`appuser`,
#     UID 1000). This satisfies the CIS Docker Benchmark and means a remote
#     code execution vulnerability cannot escalate to root inside the
#     container.

########################
# Build stage
########################
FROM python:3.11-slim AS builder

WORKDIR /app

# Build-only system deps. `curl` retained for the HEALTHCHECK in the final stage.
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

# Runtime libs only. curl is required by HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# DO-03: create an unprivileged user BEFORE copying source so ownership is
# correct and we never `COPY --chown=root`.
RUN groupadd --system --gid 1000 appuser \
 && useradd --system --uid 1000 --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# --chown so appuser can read (and, for the data/ dir, write) application files.
COPY --chown=appuser:appuser . .

# ---- Environment ----
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001 \
    PYTHONPATH=/app

EXPOSE 8001

# DO-03: drop privileges. Every subsequent RUN/CMD/HEALTHCHECK runs as
# appuser.
USER appuser

# DO-02: lightweight liveness probe. Uses the API_KEY supplied at runtime
# (must be the same credential the platform uses for real traffic).
# `curl -fsS` exits non-zero on any HTTP 4xx/5xx, so a 401 (missing key)
# would also mark the container unhealthy — this is intentional: a
# mis-configured API_KEY is itself a failure state worth surfacing.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS -H "Authorization: Bearer ${API_KEY:-unset}" \
      "http://127.0.0.1:${PORT:-8001}/api/health" \
      > /dev/null || exit 1

# Canonical entry point. `--reload` is intentionally absent; dev reload lives in
# `start_dev.py`. Workers scale via the APP_WORKERS env var.
#
# DB-01 / DB-02: alembic migrations are applied on every container start so the
# schema (and the pgvector extension) are guaranteed to be present before
# uvicorn binds. Fail-closed: if the migration fails, the container exits
# non-zero and the orchestrator will refuse to route traffic.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${APP_WORKERS:-1} --proxy-headers --forwarded-allow-ips='*'"]
