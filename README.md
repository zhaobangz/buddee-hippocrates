# Buddi RCM & Compliance Platform

Buddi is a FastAPI-first backend for revenue integrity and compliance workflows (shadow-mode coding review, prior-auth lifecycle support, and audit traceability), with an optional React frontend used mainly for local development demos.

## Current project status

- ✅ **Canonical runtime:** `backend.api:app` on port `8001`
- ✅ **Auth enforced on every route:** `X-API-Key` or `Authorization: Bearer ...`
- ✅ **DB model + migrations:** PostgreSQL + Alembic + `pgvector`
- ✅ **FHIR ingest path:** `POST /ingest/fhir` with structural validation and size guardrails
- ✅ **Tracing:** OpenTelemetry spans exported to OTLP HTTP (`localhost:4318`) when available
- ⚠️ **Frontend:** present and runnable, but some store calls still target legacy endpoints (see `frontend/README.md`)

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
```

Set at minimum:

- `SECRET_KEY` (required, min length validated)
- `BUDDI_STORAGE_KEY` (required)
- `DATABASE_URL` (must **not** use `postgres:postgres` outside test mode)
- `API_KEY` (recommended for service-to-service auth)
- `LLM_API_KEY` / `OPENAI_API_KEY` as needed

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

## Development workflow

Use the dev launcher when you want auto-reload and optional frontend boot:

```bash
python start_dev.py
```

This starts:

- backend with `--reload` on `http://127.0.0.1:8001`
- Vite frontend on `http://localhost:5173` (if `frontend/` exists)

---

## API surface (v4.1)

All routes below require authentication.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Service + DB status |
| `/ingest/fhir` | POST | Validated FHIR Bundle ingest for shadow-mode processing |
| `/encounter/{encounter_id}/process` | POST | Queue/process marker for encounter workflow |
| `/billing/suggest` | GET | Retrieve HCC suggestions (optional `encounter_id`) |
| `/prior-auth/generate` | POST | Create draft prior-authorization request |
| `/audit/query` | GET | Return recent audit events |

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