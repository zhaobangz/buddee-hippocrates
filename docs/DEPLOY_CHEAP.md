# Buddi — Least‑Cost Deployment Procedure

**Goal:** get Buddi live with the **least money out of pocket**, then describe the
upgrade path to a compliant pilot when real PHI is involved.

The single most important cost/compliance fact about this codebase:

> **Buddi runs a full synthetic demo for ~$0 and with NO PHI.** With no LLM key
> set, the demo path falls back to a deterministic stub, and the fail‑closed BAA
> guard (`BUDDI_BAA_CONFIRMED=0`, default) refuses any prompt that looks like
> real PHI. So a synthetic demo needs **no LLM spend and no signed BAAs**.
>
> Real patient data is a different tier: it requires **signed BAAs** (Anthropic +
> your cloud host) and paid managed infrastructure. Do not point real PHI at any
> Tier 0/1 deployment.
---

## Cost tiers at a glance

| Tier | Use case | Stack | ~Cost/mo | BAA needed? | LLM cost |
|------|----------|-------|----------|-------------|----------|
| **0. Synthetic demo** | Investor/customer demo, no PHI | Neon free PG16+pgvector · Render free / Fly free · Vercel free | **$0** | No | $0 (stub) |
| **1. Always‑on demo** | No cold starts, still synthetic | Neon · Render Starter ($7) or Fly small · Vercel | ~$7–15 | No | $0–low |
| **2. Pilot (real PHI)** | Design partner sends charts | GCP Cloud Run + Cloud SQL (CMEK) + KMS + Secret Manager | ~$40–120+ | **Yes** | metered |

This guide focuses on **Tier 0** (the ~$0 path) and then gives the **Tier 2**
upgrade outline.

---

## Required environment variables (all tiers)

From `core/config.py` / `docs/CLOUD_DEPLOYMENT_GUIDE.md`:

| Var | Required | Notes |
|-----|----------|-------|
| `SECRET_KEY` | ✅ | ≥32 chars. JWT/API signing. No insecure defaults. |
| `BUDDI_STORAGE_KEY` | ✅ | ≥16 chars. At‑rest PHI encryption passphrase. |
| `DATABASE_URL` | ✅ | Postgres 16 + `pgvector`. Must NOT be `postgres:postgres@…`. |
| `API_KEY` | ✅ (recommended) | Static service key; health probes + smoke tests use it. |
| `CORS_ORIGINS` | ✅ | Comma‑separated explicit origins (no `*`), e.g. your frontend URL. |
| `BUDDI_BAA_CONFIRMED` | ✅ | **Keep `0`** for synthetic/demo — fail‑closed PHI guard. |
| `LLM_PROVIDER` | optional | Defaults `anthropic`. Leave LLM keys unset for $0 demo. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | optional | Only for real LLM output; costs money + needs BAA for PHI. |
| `PORT` | optional | Defaults `8001`. Render/Fly may inject their own. |

Generate the secrets:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('BUDDI_STORAGE_KEY=' + secrets.token_hex(16))"
python3 -c "import secrets; print('API_KEY=' + secrets.token_hex(32))"
```

---

## Tier 0 — ~$0 synthetic demo (recommended first deploy)

### Step 1 — Free Postgres + pgvector (Neon)

1. Create a free project at <https://neon.tech> (or Supabase).
2. In the SQL editor run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Copy the connection string → this is your `DATABASE_URL`
   (looks like `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`).
   Because the user is not `postgres:postgres`, it passes the SEC‑04 guard.

### Step 2 — Deploy the backend (Render free, uses repo Dockerfile)

A ready‑to‑use `render.yaml` is committed at the repo root (Render Blueprint).

1. Push your repo to GitHub (already `origin`).
2. Go to <https://dashboard.render.com> → **New → Blueprint** → pick this repo.
3. Render reads `render.yaml` and creates a Docker web service. Fill in the
   `sync: false` secrets when prompted:
   - `DATABASE_URL` = your Neon string
   - `SECRET_KEY`, `BUDDI_STORAGE_KEY`, `API_KEY` = generated above
   - `CORS_ORIGINS` = your Vercel URL (set after Step 4; can edit later)
   - `BUDDI_BAA_CONFIRMED` = `0`
4. Deploy. The image's `HEALTHCHECK` hits `/health` (unauthenticated) so Render
   knows when it's live.

> **Migrations:** run once after the DB is reachable. Either set a Render
> **Pre‑Deploy Command** to `alembic upgrade head` (paid plans), or run it from
> your laptop against the Neon URL:
> ```bash
> DATABASE_URL='postgresql://…neon.tech/neondb?sslmode=require' \
>   ./venv/bin/python -m alembic upgrade head
> ```

**Fly.io alternative (also has a free allowance):**
```bash
fly launch --no-deploy            # detects the Dockerfile; creates fly.toml
fly secrets set SECRET_KEY=… BUDDI_STORAGE_KEY=… API_KEY=… \
  DATABASE_URL='postgresql://…' CORS_ORIGINS='https://your-app.vercel.app' \
  BUDDI_BAA_CONFIRMED=0
fly deploy
fly ssh console -C "alembic upgrade head"
```

### Step 3 — Migrate the database

```bash
# from the repo root, pointing at the cloud DB:
DATABASE_URL='postgresql://…neon.tech/neondb?sslmode=require' \
  ./venv/bin/python -m alembic upgrade head
```

### Step 4 — Deploy the frontend (Vercel free)

1. Import the repo at <https://vercel.com>, set **Root Directory = `frontend`**
   (build: `npm run build`, output: `dist`).
2. Environment variables:
   - `VITE_API_BASE` = `https://<your-render-or-fly-host>/api`
   - `VITE_API_KEY`  = the same `API_KEY` you set on the backend
3. Deploy, copy the resulting `https://<app>.vercel.app` URL.
4. Back on the backend, set `CORS_ORIGINS=https://<app>.vercel.app` and redeploy.

### Step 5 — Smoke test + demo

```bash
BUDDI_BASE_URL=https://<your-backend-host> \
BUDDI_API_KEY=<API_KEY> \
  ./venv/bin/python scripts/verify_system.py
```

Then open `https://<app>.vercel.app/?demo=true` to load synthetic patient
**PT‑9012 (Marcus Holloway)** and run a deterministic shadow‑mode audit — no LLM
key required.

### Step 6 (optional) — Custom domain

A domain is ~$10/yr (Cloudflare/Namecheap). Platform TLS is free on Render, Fly,
and Vercel. Point a CNAME at the platform host.

**Tier 0 running total: $0/mo** (domain optional ~$10/yr).

---

## Tier 1 — make it always‑on (~$7–15/mo)

Free web services sleep and cold‑start. To avoid that for a live demo:

- Upgrade the backend to **Render Starter ($7/mo)** or a small **Fly** machine.
- Optionally add an Anthropic key with a tight budget for *synthetic* live LLM
  output (still keep `BUDDI_BAA_CONFIRMED=0`; only synthetic data flows).
- Keep Neon free and Vercel free.

---

## Tier 2 — compliant pilot with REAL PHI (only when you have a paying/design partner)

This is the **only** path where real patient data is allowed. It costs money and
requires legal paperwork. Do not skip the BAAs.

### A. Legal / compliance (before any PHI)
1. **File + sign BAAs** with **Anthropic** (healthcare program) and **Google
   Cloud**. Update `docs/COMPLIANCE/baa_status.md` until every Required‑BAA row is
   `signed: yes`. OpenAI stays **embeddings‑only, no PHI** unless you also sign
   its BAA.
2. Have privacy policy + security whitepaper ready (`docs/security_whitepaper.md`).

### B. Infrastructure (GCP, per BUILD_PLAN §3.5 + infra/)
1. Cloud SQL Postgres 16 (private IP, **CMEK**, pgvector) → set `DATABASE_URL`.
2. Secret Manager for `SECRET_KEY`, `BUDDI_STORAGE_KEY`, `API_KEY`, `DATABASE_URL`,
   `ANTHROPIC_API_KEY`.
3. Cloud KMS key for the daily signed Merkle audit anchor
   (`BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH` / KMS key id; see `core/merkle.py`).
4. Deploy the two services from the repo templates (same image, different CMD):
   ```bash
   gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/buddi/buddi-api:TAG
   gcloud run services replace infra/cloud-run-api.yaml    --region="$REGION"
   gcloud run services replace infra/cloud-run-worker.yaml --region="$REGION"
   ```
5. Run migrations as a **Cloud Run Job** (not on container start) each deploy.

### C. Turn PHI on (per tenant)
1. `python scripts/provision_tenant.py --slug acme --name "Acme" --scopes clinician,ingest`
   (prints the raw API key once).
2. After counsel verifies the signed + counter‑signed BAA:
   ```sql
   UPDATE tenants SET baa_confirmed = TRUE, baa_confirmed_at = NOW() WHERE id = '<tenant-uuid>';
   ```
3. Set `BUDDI_BAA_CONFIRMED=1` in the production env **only** once every Required
   BAA is in place. Now `/ingest/fhir` accepts that tenant's real bundles.

### D. Rough Tier 2 monthly cost
- Cloud SQL (smallest HA‑capable instance) is the dominant line item (~$30–80+).
- Cloud Run scales to near‑zero (pennies–low dollars at demo volume).
- Anthropic usage is metered (~≤$0.40/encounter target per BUILD_PLAN §3.3.4).
- KMS/Secret Manager/Logging: a few dollars.
- **Estimate: ~$40–120+/mo** before LLM usage, depending on Cloud SQL sizing.

---

## Decision shortcut

- **Just need to show it off / raise / sell?** → **Tier 0 ($0)**, synthetic demo.
- **Want it always‑on for a live link?** → **Tier 1 (~$7–15)**.
- **A real clinic will send real charts?** → **Tier 2**, after BAAs (~$40+).

---

## Guardrails recap (do not bypass to save money)

- Keep `BUDDI_BAA_CONFIRMED=0` on every non‑BAA deployment. It is what keeps you
  out of HIPAA scope on the cheap tiers.
- Never put real PHI into Neon/Render/Fly/Vercel — those are not under a BAA.
- Secrets live in the platform's env/secret store, never in the repo (`.env` is
  gitignored; `.gitleaks.toml` + CI scan for leaks).
