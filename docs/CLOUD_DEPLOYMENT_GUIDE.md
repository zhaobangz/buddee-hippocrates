# Cloud Deployment Guide (Current v4.1)

This guide reflects the **current** Buddi deployment model: containerized FastAPI backend (`backend.api:app`) with PostgreSQL + Alembic migrations and authenticated API traffic.

## What is production-canonical

- Runtime API: `backend.api:app` on port `8001`
- Two-service split (§3.5): the **API** runs the default image CMD (`uvicorn`);
  the **worker** (`buddi-worker`) reuses the *same image* with its CMD overridden
  to `python -m core.worker` (see `infra/cloud-run-worker.yaml`).
- Schema migrations run as a **separate Cloud Run Job** (`buddi-migrate-*`) on each
  deploy — **not** on container start — so autoscaled replicas never race on
  `alembic upgrade head`. Locally, run `make migrate` (or
  `docker compose run --rm api alembic upgrade head`) before first start.
- Auth is required on all API routes (`API_KEY` / bearer)
- Health probes: `GET /health` (unauthenticated — used by the container
  `HEALTHCHECK` and the deploy smoke tests) and `GET /api/health` (authenticated,
  DB-backed readiness)
- RAG retrieval uses PostgreSQL + `pgvector` (not FAISS index files)

## Required environment variables

At minimum, set these as managed secrets/config:

- `SECRET_KEY`
- `BUDDI_STORAGE_KEY`
- `DATABASE_URL`
- `API_KEY` (recommended and expected by smoke checks + health probes)
- `LLM_API_KEY` and/or `OPENAI_API_KEY`
- `CORS_ORIGINS` (comma-separated explicit origins, no `*`)

## Container deployment checklist

1. Build image from repo `Dockerfile`.
2. Ensure target Postgres has `pgvector` enabled.
3. Set `DATABASE_URL` to a dedicated credential (non-`postgres:postgres`).
4. Provide `API_KEY` so health checks can authenticate.
5. Route TLS traffic through your platform ingress/load balancer.
6. Restrict CORS (`CORS_ORIGINS`) to known frontend origins.

## Example: generic Docker runtime

```bash
docker build -t buddi-api:latest .

docker run --rm -p 8001:8001 \
  -e SECRET_KEY='replace-with-strong-secret' \
  -e BUDDI_STORAGE_KEY='replace-with-strong-storage-key' \
  -e API_KEY='replace-with-api-key' \
  -e DATABASE_URL='postgresql://user:pass@host:5432/buddi' \
  -e CORS_ORIGINS='https://app.example.com' \
  -e LLM_API_KEY='...' \
  buddi-api:latest
```

## Example: Google Cloud Run shape

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT/buddi-api

gcloud run deploy buddi-api \
  --image gcr.io/YOUR_PROJECT/buddi-api \
  --platform managed \
  --region us-central1 \
  --set-env-vars PORT=8001 \
  --set-secrets SECRET_KEY=SECRET_KEY:latest,BUDDI_STORAGE_KEY=BUDDI_STORAGE_KEY:latest,API_KEY=API_KEY:latest,DATABASE_URL=DATABASE_URL:latest,LLM_API_KEY=LLM_API_KEY:latest \
  --no-allow-unauthenticated
```

> Note: `--no-allow-unauthenticated` aligns with backend behavior (all routes require auth).

## Post-deploy smoke checks

```bash
BUDDI_BASE_URL=https://your-api.example.com \
BUDDI_API_KEY=your-api-key \
python scripts/verify_system.py
```

## Two-service deployment (§3.5)

Both services run the **same image**; only the CMD and scaling differ.

| | `buddi-api` | `buddi-worker` |
|---|---|---|
| Template | `infra/cloud-run-api.yaml` | `infra/cloud-run-worker.yaml` |
| CMD | default (`uvicorn …`) | `python -m core.worker` |
| minScale / maxScale | 1 / 20 | 0 / 10 |
| `BUDDI_DISABLE_WORKER` | `0` in-process, or `1` when the worker service drains the queue | n/a |
| `BUDDI_DISABLE_MERKLE_TASK` | `0` (API seals the daily Merkle root) | `1` |

Apply a template (after substituting `PROJECT_ID`/`REGION`/`IMAGE_TAG`):

```bash
gcloud run services replace infra/cloud-run-api.yaml --region="$REGION"
gcloud run services replace infra/cloud-run-worker.yaml --region="$REGION"
```

Local parity is `docker compose up` (api + worker + Postgres/pgvector + an OTel
collector); see `docker-compose.yml`.

## Secret management & onboarding

- Secrets are injected from **Secret Manager** (never baked into the image; see
  `.gitignore`). Rotation procedures: **`docs/runbooks/secret_rotation.md`**.
- Provision a tenant + API key: `python scripts/provision_tenant.py --slug acme \
  --name "Acme" --scopes clinician,ingest`. The raw key is printed once.

## CI/CD status in repo

- `.github/workflows/main.yml` — lint (ruff), pytest, eval-regression gate, Synthea
  drift check, plus **security scanning** (gitleaks blocking, configured via
  `.gitleaks.toml`; pip-audit + mypy advisory) and a Docker **build verification**.
- `.github/workflows/deploy-staging.yml` — on push to `main`: build/push the image to
  Artifact Registry, deploy a **no-traffic** revision, run the `buddi-migrate-staging`
  job, smoke-test `/health`, then shift traffic. Authenticates via **Workload
  Identity Federation** (no long-lived SA keys).
- `.github/workflows/deploy-prod.yml` — manual `workflow_dispatch` gated by a typed
  `DEPLOY` confirmation and the protected `production` GitHub Environment: promote a
  staging image, **canary at 10%**, 30-minute soak, then 100% traffic.
