# Buddi — Revenue Integrity & Compliance Platform

Buddi is a shadow-mode revenue-cycle management (RCM) platform for U.S. healthcare. It
ingests FHIR R4 clinical bundles, runs an AI agent pipeline over CMS HCC/ICD-10
guidelines, and emits coding suggestions, prior-authorization drafts, and a
cryptographically verifiable audit trail — without auto-submitting anything to payers.

**Core thesis:** Buddi suggests; clinicians approve. Every review is permanently recorded
in a hash-chained, daily-Merkle-root-signed audit log that can survive a CMS RADV audit.
The audit chain is the moat, not the LLM.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Operator / EHR System                    │
└──────────────┬───────────────────────────────┬───────────────┘
               │ HTTPS (TLS 1.3)               │ FHIR R4 Bundle
┌──────────────▼───────────────────────────────▼───────────────┐
│                   Cloud Run / Local :8001                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                   FastAPI (backend/api.py)              │ │
│  │  Auth · CORS · Rate Limit · Request ID · OTel Tracing   │ │
│  └──────┬──────────────────────────────────────┬───────────┘ │
│         │                                      │             │
│  ┌──────▼────────┐                    ┌────────▼──────────┐  │
│  │  Sync Routes  │                    │  Async Job Queue  │  │
│  │  /health      │                    │  (core/jobs.py)   │  │
│  │  /audit/*     │                    │  shadow_audit     │  │
│  │  /demo/*      │                    │  prior_auth       │  │
│  │  /billing/*   │                    └────────┬──────────┘  │
│  │  /webhooks    │                             │             │
│  └───────────────┘                    ┌────────▼──────────┐  │
│                                       │  Worker           │  │
│                                       │  (core/worker.py) │  │
│                                       └────────┬──────────┘  │
└────────────────────────────────────────────────┼─────────────┘
                                                 │
┌────────────────────────────────────────────────┼──────────────┐
│                                          Core Agent Pipeline  │
│  ┌───────────────┐  ┌──────────────┐  ┌────────────────────-┐ │
│  │ FHIR Adapter  │  │  RAG Engine  │  │  LLM Manager        │ │
│  │ (fhir_client) │──│ (rag_engine) │──│  Anthropic (1°)     │ │
│  │ Extract notes │  │ pgvector     │  │  OpenAI (embeddings)│ │
│  │ + billed codes│  │ hybrid search│  │  BAA tripwire       │ │
│  └───────┬───────┘  └──────┬───────┘  └─────────┬──────────-┘ │
│          │                 │                    │             │
│  ┌───────▼─────────────────▼────────────────────▼──────────-┐ │
│  │                   Agent (core/agent.py)                  │ │
│  │  Shadow Audit · Prior Auth · LLM-as-Judge · Safety Floor │ │
│  └──────────────────────────┬───────────────────────────────┘ │
│                             │                                 │
│  ┌──────────────────────────▼───────────────────────────────┐ │
│  │              Audit Chain (core/merkle.py)                │ │
│  │  Hash-chained events · Daily Merkle root · KMS-signed    │ │
│  │  Object Lock (WORM) export · Verifiable audit trail      │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

**Two-process model:** The API service (`backend/api.py`, port 8001) handles
synchronous requests. Long-running LLM work (shadow audits, prior-auth generation) is
enqueued as async jobs in the `jobs` table and processed by the background worker
(`core/worker.py`). Both processes share the same Docker image; they differ only in
`CMD`.

### Safety layers

Every coding suggestion passes through multiple gates before reaching an operator:

1. **Confidence floor** (default 0.70) — suggestions below threshold are abstained
2. **LLM-as-judge second pass** — independent verification for uncertain-band
   suggestions (confidence in [0.70, 0.85))
3. **Mandatory evidence quotes** — every suggestion must cite verbatim text from the
   clinical note
4. **BAA tripwire** — refuses PHI-shaped prompts until `BUDDI_BAA_CONFIRMED=1`
5. **Fail-closed** — any guard failure results in abstention, never a silent skip

### LLM strategy

| Task | Model | Provider |
|------|-------|----------|
| Clinical reasoning (HCC/ICD-10 coding, prior-auth) | Claude Opus 4.8 | Anthropic |
| High-volume coding suggestions | Claude Sonnet 4.6 | Anthropic |
| Embeddings (guidelines + queries) | text-embedding-3-large | OpenAI |

OpenAI is used for embeddings only — no PHI touches the OpenAI prompt path.
Anthropic is the sole clinical-reasoning provider.

---

## Current status

- ✅ **Canonical runtime:** `backend.api:app` on port `8001`
- ✅ **Auth enforced on every route:** `X-API-Key` or `Authorization: Bearer ...`
- ✅ **DB model + migrations:** PostgreSQL 16 + Alembic + pgvector with HNSW index
- ✅ **FHIR ingest path:** `POST /ingest/fhir` with structural validation and size guardrails
- ✅ **Hash-chained audit log:** per-tenant hash chain with daily KMS-signed Merkle roots
- ✅ **Async job queue:** `jobs` table with idempotency keys, worker loop, SSE progress streaming
- ✅ **SMART-on-FHIR:** OAuth2 PKCE launch flow for EHR connector
- ✅ **Stripe billing:** Checkout, Customer Portal, webhook handling
- ✅ **Webhooks:** HMAC-signed delivery for 4 event types
- ✅ **Tracing:** OpenTelemetry spans exported to OTLP HTTP when available
- ✅ **Eval harness:** 10-case clinician-labeled golden set with CI regression gate
- ✅ **Red-team suite:** 50+ adversarial prompts with nightly CI run
- ✅ **Frontend:** React 19 + Vite + Tailwind operator UI with demo mode

---

## Quick start (local backend)

### 1) Prerequisites

- Python 3.11
- PostgreSQL 16+ with `pgvector` extension

### 2) Install dependencies

`requirements.txt` is **runtime-only** (what the production image ships).
Test/CI tooling lives in `requirements-dev.txt`.

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip

# Production runtime:
pip install -r requirements.txt

# Local dev / CI:
pip install -r requirements.txt -r requirements-dev.txt
```

> Always run tooling via `python -m <tool>` (e.g. `python -m pytest`,
> `python -m alembic`) or after `source venv/bin/activate`.

### 3) Configure environment

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Set at minimum:

- `SECRET_KEY` (required, min 32 chars)
- `BUDDI_STORAGE_KEY` (required, min 16 chars)
- `DATABASE_URL` (must **not** use `postgres:postgres` outside test mode)
- `API_KEY` (for service-to-service auth)
- `ANTHROPIC_API_KEY` (for LLM features)
- `frontend/.env`: `VITE_API_BASE=http://localhost:8001/api`, `VITE_API_KEY`

### 4) Run DB migrations

```bash
alembic upgrade head
```

### 5) Start the API

```bash
# Production parity:
python start.py

# Dev mode (backend + frontend):
python start_dev.py
```

Backend: `http://localhost:8001` — Swagger docs at `http://localhost:8001/docs`

---

## One-line developer ergonomics (`make`)

```bash
make install      # backend venv + pip deps, frontend npm install
make db           # docker Postgres+pgvector on :5433
make migrate      # alembic upgrade head
make dev          # python start_dev.py — backend :8001, frontend :5173
make test         # pytest -q + frontend Vitest
make lint         # ruff (backend) + eslint (frontend)
make help         # list all targets
```

> The `make` flow runs a throwaway Postgres on **port 5433** with
> `postgres:postgres`, matching `tests/conftest.py`. `migrate`/`dev` set
> `BUDDI_TEST_MODE=1` to satisfy the local credential guard.

Open `http://localhost:5173/?demo=true` to load the synthetic patient
**PT-9012 (Marcus Holloway)** and run a deterministic shadow-mode revenue
audit — no LLM key required.

---

## API routes

### Health & readiness

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/internal/health` | None | Load-balancer probe |
| GET | `/health` | None | Version status |
| GET | `/api/health` | API key | Authenticated health with tenant info |
| GET | `/api/readiness` | API key | Readiness probe (503 if agent not bootstrapped) |

### Shadow audit (core product)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/shadow/audit` | Clinician | Queue or run HCC/ICD shadow audit |
| POST | `/ingest/fhir` | Ingest | FHIR bundle ingest |
| POST | `/api/ingest/fhir` | Ingest | FHIR bundle ingest (API path) |
| POST | `/api/encounter/{id}/process` | Clinician | Queue encounter processing |
| GET | `/api/billing/suggest` | API key | Get HCC suggestions for tenant |

### Portal auth (invite-only email+password+hCaptcha)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/login` | None (captcha) | Email+password login → access JWT + rotating refresh token |
| POST | `/api/auth/signup` | None (invite+captcha) | Redeem admin invite → account + session |
| POST | `/api/auth/refresh` | Refresh token | Rotate refresh, new access JWT (reuse revokes family) |
| POST | `/api/auth/logout` | Refresh token | Revoke refresh token (idempotent) |
| GET | `/api/auth/me` | User JWT | Current portal user profile |
| POST | `/api/auth/invites` | Admin | Generate single-use invite (raw token returned once) |

### Prior authorization

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/prior-auth/generate` | Clinician | Generate prior-auth draft |

### Async jobs

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/jobs/{job_id}` | Clinician | Poll job status + result |
| GET | `/api/jobs/{job_id}/stream` | Clinician | SSE stream of job progress |

### Demo & synthetic data

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/demo/sample-patient` | API key | Get demo patient (Marcus Holloway) |
| GET | `/api/demo/synthea` | API key | List synthetic FHIR bundles |
| GET | `/api/demo/synthea/{name}` | API key | Fetch synthetic bundle JSON |
| POST | `/api/demo/synthea/{name}/ingest` | API key | Run synthetic bundle through agent |
| GET | `/api/demo/bundles` | Clinician | List demo fixture bundles |
| GET | `/api/demo/bundles/{name}` | Clinician | Fetch demo fixture bundle |

### SMART-on-FHIR

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/ehr/launch` | Admin | Initiate SMART standalone launch |
| GET | `/api/ehr/callback` | None | OAuth redirect handler |

### Audit chain

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/audit/query` | API key | Get audit log entries |
| GET | `/api/audit/verify` | Admin | Verify audit chain + signed Merkle roots |
| GET | `/api/audit/roots` | Admin | List signed daily Merkle roots |
| POST | `/api/audit/roots/seal` | Admin | Trigger immediate Merkle root sealing |

### HCC suggestions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/suggestions/{id}/approve` | Clinician | Approve an HCC suggestion |

### Stripe billing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/billing/subscribe` | Admin | Create Stripe Checkout session |
| POST | `/api/billing/portal` | Admin | Get Stripe billing portal URL |
| GET | `/api/billing/status` | Admin | Get subscription status |
| POST | `/api/billing/webhook` | None (HMAC) | Stripe event receiver |

### Webhooks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/webhooks` | Admin | Register webhook endpoint |
| GET | `/api/webhooks` | Admin | List webhook registrations |
| DELETE | `/api/webhooks/{id}` | Admin | Delete webhook |

### Metrics & dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/metrics/slo` | Admin | PHI-safe SLO metrics (p95 latency, approval rates) |
| GET | `/api/dashboard/metrics` | API key | Revenue recovery dashboard aggregates |

### Chat & patient

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/chat/chat` | Clinician | Chat with agent (routes to shadow-mode) |
| GET | `/api/patient/{id}` | API key | Get patient profile |

Auth example:

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8001/api/health
```

---

## Audit chain (the moat)

Every clinical action — suggestion creation, clinician approval/rejection, prior-auth
state transition — writes an append-only row to the `audit_events` table. Each row is
hash-chained to its predecessor: `sha256(prev_hash || canonical_json(payload))`.

**Daily at midnight UTC**, the background Merkle task:

1. Builds a Merkle tree over the day's events
2. Signs the root with Cloud KMS (or Ed25519 PEM / HMAC fallback in dev)
3. Exports the signed envelope to a GCS Object Lock bucket (WORM, 7-year retention)

The result is a **tamper-evident audit trail** — any alteration to any event in the
chain is cryptographically detectable. This is the artifact that makes Buddi defensible
in a CMS/OIG audit.

Verification (`GET /api/audit/verify`) walks the DB chain and validates every event
against the signed Merkle roots. The endpoint that seals a day's root refuses to seal
today or future dates (partial-day sealing would produce a premature root).

---

## Repository map

```text
backend/        FastAPI routes, auth, FHIR adapter, SMART-on-FHIR, Stripe billing
core/           agent orchestration, LLM manager, RAG engine, safety, Merkle audit,
                models, jobs, worker, webhooks, PHI guard, config, tracing
alembic/        database migration config and 8 revision scripts
frontend/       React 19 + Vite operator UI (dev/demo surface)
tests/          pytest suite — 18 test files covering API, auth, audit, billing,
                jobs, rate limiting, FHIR/SMART, webhooks, red-team
tools/          clinical workflows, EHR reader, FHIR client, search
scripts/        tenant provisioning, seed data, migration smoke, system verification
docs/           operational guides, compliance docs, runbooks, deployment guides
evals/          evaluation harness, golden set, red-team suite, Synthea bundles
growth/         outbound sales outreach pipeline and generated outbox
infra/          Cloud Run deployment manifests, OpenTelemetry config
data/           ingestion scripts, crosswalk data
storage/        runtime audit root storage
```

---

## Docker

```bash
# Build and run with Compose:
docker compose up -d

# Services: api (:8001), worker, db (pgvector/pg16), otel-collector
```

The `Dockerfile` is a multi-stage Python 3.11 build with a non-root `buddi` user,
HEALTHCHECK, and explicit COPYs (no blanket `COPY . .`).

---

## Verification

```bash
# Unit/integration tests:
pytest -q

# Migration smoke test (round-trip upgrade/downgrade):
MIGRATION_SMOKE_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/postgres \
  python scripts/migrate_smoke.py --roundtrip

# Lint (matches CI):
python -m ruff check backend/ core/ tools/ scripts/ evals/ tests/

# System verification:
python scripts/verify_system.py
BUDDI_TEST_MODE=1 python scripts/verify_reaudit_fixes.py
```

Local test Postgres:

```bash
docker run -d --name buddi-pg-test \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=buddi \
  -p 5433:5432 pgvector/pgvector:pg16
```

---

## Deployment

- **$0 synthetic demo:** Render (backend) + Neon (Postgres) + Vercel (frontend) —
  see `docs/DEPLOY_CHEAP.md`
- **Production (real PHI):** GCP Cloud Run + Cloud SQL + Cloud KMS + GCS Object Lock —
  see `docs/CLOUD_DEPLOYMENT_GUIDE.md`
- **CI/CD:** GitHub Actions (`.github/workflows/`) — lint, test, eval gate, Docker
  build, security scans, staging/production deploy with canary

---

## Key docs

- `docs/PRODUCT_TRUTH.md` — honest, current-capabilities-only reference (read before sales calls)
- `docs/MVP_COMPLETION_PLAN.md` — strategic plan aligned with founders manual
- `docs/TECHNICAL_BUILD_PLAN.md` — detailed 12-week sprint plan
- `docs/DEPLOY_CHEAP.md` — $0–$15/mo deployment guide
- `docs/CLOUD_DEPLOYMENT_GUIDE.md` — GCP production deployment
- `docs/cookbook.md` — API recipes and integration patterns
- `docs/security_whitepaper.md` — security architecture and compliance posture
- `docs/INCIDENT_RESPONSE.md` — severity tiers, on-call escalation
- `docs/runbooks/secret_rotation.md` — credential rotation procedures
- `docs/COMPLIANCE/baa_status.md` — BAA tracking across providers
- `docs/COMPLIANCE/phi_flow.md` — PHI data flow documentation
- `docs/AUDIT_PARTITIONING.md` — audit event partition management
- `evals/README.md` — eval harness usage and CI gate
- `AUDIT_REPORT.md` — July 2026 codebase security audit
