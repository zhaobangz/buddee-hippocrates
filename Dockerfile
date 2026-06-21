# syntax=docker/dockerfile:1.7
#
# Buddi — canonical production image (BUILD_PLAN.md §3.5).
#
# Dual-mode, single image:
#   * Default CMD serves the API (`backend.api:app` on :8001).
#   * The worker reuses THIS image with CMD overridden to
#     ["python", "-m", "core.worker"] — set in infra/cloud-run-worker.yaml,
#     not here, so the API and worker can never drift out of sync.
#
# Reproducibility (Task 1.1): pin python:3.11-slim by digest in production.
# Resolve the current digest with:
#   docker buildx imagetools inspect python:3.11-slim --format '{{.Manifest.Digest}}'
# then change the two FROM lines to:
#   FROM python:3.11-slim@sha256:<digest> AS builder
#   FROM python:3.11-slim@sha256:<digest>
#
# Re-audit (April 21) follow-ups, still in force:
#   - DO-02: HEALTHCHECK probes the unauthenticated /health on the loopback
#     port; 3 consecutive failures mark the container unhealthy so Cloud
#     Run / k8s restart it.
#   - DO-03: the process runs as a dedicated non-root user (`buddi`). A
#     remote code-execution bug cannot escalate to root inside the container.
#   - DO-05: NO `COPY . .` — each directory is copied explicitly so .env,
#     venv/, audit_log.json, data/, config/credentials.json, etc. can never
#     leak into the image.

########################
# Build stage
########################
FROM python:3.11-slim AS builder

WORKDIR /app

# Build-only system deps. `curl` is reinstalled in the final stage for the
# HEALTHCHECK; build-essential stays here and is NOT shipped.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Task 1.3: production dependencies ONLY. requirements-dev.txt (ruff, pytest,
# mypy, fakeredis, …) is intentionally never copied into any stage.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

########################
# Final stage
########################
FROM python:3.11-slim

WORKDIR /app

# Runtime libs only — curl is required by the HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Task 1.2 (DO-03): unprivileged runtime user, created before COPY so we never
# ship root-owned writable paths.
RUN adduser --disabled-password --gecos "" buddi

# Installed third-party packages + console scripts (uvicorn, alembic) from the
# builder stage.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Task 1.7 (DO-05): explicit COPYs only — never `COPY . .`.
COPY backend/ backend/
COPY core/ core/
COPY tools/ tools/
COPY alembic/ alembic/
COPY alembic.ini .

# ---- Environment ----
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001 \
    PYTHONPATH=/app

EXPOSE 8001

# Task 1.2 (DO-03): drop privileges. Every subsequent CMD/HEALTHCHECK runs as buddi.
USER buddi

# Task 1.6 (DO-02): liveness probe against the unauthenticated /health route.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:8001/health || exit 1

# Task 1.4: default entrypoint serves the API. Schema migrations run as a
# dedicated Cloud Run Job per deploy (see .github/workflows/deploy-*.yml
# `buddi-migrate-*`), NOT on container start — otherwise N autoscaled replicas
# race on `alembic upgrade head`. Locally, run `make migrate` (or
# `docker compose run --rm api alembic upgrade head`) before first start.
#
# Task 1.5: the worker is launched by overriding this CMD (see
# infra/cloud-run-worker.yaml): ["python", "-m", "core.worker"].
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8001"]
