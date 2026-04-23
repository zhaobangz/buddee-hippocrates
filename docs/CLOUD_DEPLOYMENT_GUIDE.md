# Cloud Deployment Guide (Current v4.1)

This guide reflects the **current** Buddi deployment model: containerized FastAPI backend (`backend.api:app`) with PostgreSQL + Alembic migrations and authenticated API traffic.

## What is production-canonical

- Runtime API: `backend.api:app` on port `8001`
- Container entrypoint runs: `alembic upgrade head && uvicorn ...`
- Auth is required on all routes (`API_KEY` / bearer)
- Health probe endpoint: `GET /api/health`
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

## CI/CD status in repo

`.github/workflows/main.yml` currently runs lint + tests. Staging/production deploy jobs are placeholders with warning markers and are not fully wired yet.
