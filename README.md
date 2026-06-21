# Buddi RCM & Compliance Platform

Buddi is a FastAPI-first backend for revenue integrity and compliance workflows (shadow-mode coding review, prior-auth lifecycle support, and audit traceability), with an optional React frontend used mainly for local development demos.

## Current project status

- ✅ **Canonical runtime:** `backend.api:app` on port `8001`
- ✅ **Auth enforced on every route:** `X-API-Key` or `Authorization: Bearer ...`
- ✅ **DB model + migrations:** PostgreSQL + Alembic + `pgvector`
- ✅ **FHIR ingest path:** `POST /ingest/fhir` with structural validation and size guardrails
- ✅ **Tracing:** OpenTelemetry spans exported to OTLP HTTP (`localhost:4318`) when available
- ✅ **Frontend contract:** store API calls use the canonical `/api/*` backend routes and shared `X-API-Key` axios instance

---

## Architecture (what is actually in use)

- **Backend API:** FastAPI (`backend/api.py`)
- **Agent orchestration:** `core/agent.py`
- **LLM adapter:** `core/llm_manager.py`
- **RAG retrieval:** PostgreSQL/pgvector-backed retrieval (`core/rag_engine.py`)
- **Safety + audit helpers:** `core/safety.py`
- **Migrations:** Alembic (`alembic/`)

> **Legacy local artifacts (`*.faiss` / `*.pkl`).** Earlier revisions shipped a
> FAISS sidecar index (`guidelines_index.faiss` + `guidelines_metadata.pkl`).
> Retrieval is now **pgvector-backed** (`core/rag_engine.py`) and nothing in the
> codebase reads those files, so they are **not required to run the app**. They
> are git-ignored (`*.faiss`, `*.pkl`) and were removed from version control; if
> you have local copies you can delete them. Should a future FAISS path be
> reintroduced, generate the index from `core/rag_engine.py` rather than
> committing the binaries.

---

## Quick start (local backend)

### 1) Prerequisites

- Python 3.11 recommended
- PostgreSQL 16+ with `pgvector` extension available

### 2) Install dependencies

`requirements.txt` is **runtime-only** (what the production image ships).
Test/CI tooling (pytest, pytest-asyncio, fakeredis, lupa, ruff) lives in
`requirements-dev.txt` and layers on top via `-r requirements.txt`.

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip

# Production runtime only:
pip install -r requirements.txt

# Local dev / CI (adds test + lint tooling):
pip install -r requirements.txt -r requirements-dev.txt
```

> Always run tooling via `python -m <tool>` (e.g. `python -m pytest`,
> `python -m alembic`) or after `source venv/bin/activate`. If you ever see a
> `bad interpreter` error from `venv/bin/<tool>`, the venv was created under a
> different absolute path — recreate it with the commands above.

### 3) Configure environment

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Set at minimum:

- `SECRET_KEY` (required, min length validated)
- `BUDDI_STORAGE_KEY` (required)
- `DATABASE_URL` (must **not** use `postgres:postgres` outside test mode)
- `API_KEY` (recommended for service-to-service auth)
- `LLM_API_KEY` / `OPENAI_API_KEY` as needed
- `frontend/.env` values: `VITE_API_BASE=http://localhost:8001/api` and
  `VITE_API_KEY` matching the backend `API_KEY` for local browser requests

### 4) Run DB migrations

```bash
alembic upgrade head
```

### 5) Start production-parity API process

```bash
python start.py
```

Backend is available at:

- `http://localhost:8001`
- Swagger docs: `http://localhost:8001/docs`

---

## One-line developer ergonomics

If you have `make` and Docker, the canonical local sequence is:

```bash
make install      # backend venv + pip deps, frontend npm install
make db           # docker Postgres+pgvector on :5433, CREATE EXTENSION vector
make migrate      # alembic upgrade head
make dev          # python start_dev.py — backend on :8001, frontend on :5173
make test         # pytest -q + frontend Vitest (--passWithNoTests for now)
make lint         # ruff (backend) + eslint (frontend)
make help         # list all targets
```

> The `make` flow runs a throwaway Postgres on **port 5433** with
> `postgres:postgres`, matching `tests/conftest.py` so `make test` and a bare
> `pytest` share one database. `migrate`/`dev` set `BUDDI_TEST_MODE=1` only to
> satisfy the SEC-04 `postgres:postgres` guard locally. This is distinct from
> the production-style `DATABASE_URL` (dedicated credential, port 5432) in the
> Quick start above — use that one for any real data.

Open `http://localhost:5173/?demo=true` to load the synthetic patient
**PT-9012 (Marcus Holloway)** and run a deterministic shadow-mode revenue
audit. The dashboard, audit trail, and prior-auth modal will all populate
from a single click — no LLM key required (the demo path falls back to a
deterministic stub).

## Development workflow

Use the dev launcher when you want both services:

```bash
python start_dev.py
```

Key API routes:

| Route | Method | Description |
| --- | --- | --- |
| `/api/health` | GET | Authenticated liveness check |
| `/api/readiness` | GET | Authenticated readiness check; 503 if the agent is degraded |
| `/ingest/fhir` | POST | Validated FHIR Bundle ingest for shadow-mode processing |
| `/api/encounter/{encounter_id}/process` | POST | Queue/process marker for encounter workflow |
| `/api/billing/suggest` | GET | Retrieve HCC suggestions (optional `encounter_id`) |
| `/api/prior-auth/generate` | POST | Create draft prior-authorization request |
| `/api/audit/query` | GET | Return recent audit events |

Auth example:

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8001/api/health
```

---

## Verification commands

```bash
# Unit/integration tests. DB-backed tests connect to the test Postgres on
# port 5433 (see tests/conftest.py); without one reachable they skip the DB
# assertions and exercise only the HTTP layer, so `pytest -q` is always green.
pytest -q

# Migration smoke test — runs the full `alembic upgrade head` (+ a
# downgrade/upgrade round-trip) against a throwaway database. Skips cleanly
# if no Postgres is reachable.
MIGRATION_SMOKE_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/postgres \
  python scripts/migrate_smoke.py --roundtrip

# Lint (matches CI):
python -m ruff check backend/ core/ tools/ scripts/ evals/ tests/

python scripts/verify_system.py
BUDDI_TEST_MODE=1 python scripts/verify_reaudit_fixes.py
```

A local test Postgres+pgvector on port 5433 (matching `tests/conftest.py`):

```bash
docker run -d --name buddi-pg-test \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=buddi \
  -p 5433:5432 pgvector/pgvector:pg16
```

---

## Repository map

```text
backend/     FastAPI routes, auth, FHIR adapter
core/        agent orchestration, config, storage, safety, RAG, tracing
alembic/     migration config and revisions
frontend/    optional React/Vite operator UI (dev/demo surface)
scripts/     smoke checks, seeding, and verification utilities
tests/       pytest integration coverage for API/auth paths
docs/        operational and setup guides
```

---

## Additional docs

- `docs/QUICK_REFERENCE.md`
- `docs/FRONTEND_BACKEND_CONNECTION.md`
- `docs/WEB_SETUP_GUIDE.md`
- `docs/CLOUD_DEPLOYMENT_GUIDE.md`
- `docs/TRACING_SETUP.md`