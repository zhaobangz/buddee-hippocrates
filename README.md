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

---

## Quick start (local backend)

### 1) Prerequisites

- Python 3.11 recommended
- PostgreSQL 16+ with `pgvector` extension available

### 2) Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

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
make install      # backend pip deps + frontend npm ci
make db           # docker-run Postgres+pgvector and CREATE EXTENSION vector
make migrate      # alembic upgrade head
make dev          # python start_dev.py — backend on :8001, frontend on :5173
make test         # pytest -q + frontend Vitest smoke
make lint         # eslint frontend
```

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
pytest -q
python scripts/verify_system.py
BUDDI_TEST_MODE=1 python scripts/verify_reaudit_fixes.py
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