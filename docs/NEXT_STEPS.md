# Buddee — Next Steps (Do-This-Now Action List)

**Anchored to:** Strategic Founders Operating Manual, 2nd Edition (June 2026)
**Codebase baseline:** v4.1 (this repo)
**Generated:** July 5, 2026 · Last updated: July 20, 2026

> This is the distilled "what do I actually do next" list, ordered by dependency and
> leverage. It complements the fuller `docs/MVP_COMPLETION_PLAN.md`. Where a task is a
> human-only action (legal, sales, hiring), it is tagged **[HUMAN]** with the reference
> to the H-task in the completion plan.
>
> **Deployment reality:** this codebase deploys to **Render (free, synthetic)** and
> **GCP Cloud Run (paid, real-PHI)** — *not AWS*. All infra manifests (`render.yaml`,
> `infra/cloud-run-*.yaml`) and `docs/DEPLOY_CHEAP.md` target Render + GCP.

---

## Where you already are (don't redo this)

Per `docs/MVP_COMPLETION_PLAN.md` §1, these are **SHIPPED in code**:
- ✅ Daily KMS-signed Merkle root → Object Lock (`core/merkle.py`) — *the moat*
- ✅ Anthropic-primary LLM cutover; LangChain stripped; BAA tripwire (`core/llm_manager.py`)
- ✅ Postgres RLS + tenant scoping with `GucStamper` for mid-request commits (`core/db_session.py`)
- ✅ SMART-on-FHIR, webhooks, Stripe, async jobs, SSE streaming — all implemented
- ✅ Prompt caching via Anthropic `cache_control`
- ✅ HNSW index on `document_chunks.embedding`
- ✅ Red-team adversarial prompt suite with nightly CI
- ✅ 10-case golden eval set committed; CI regression gate wired
- ✅ Docker + docker-compose + Cloud Run manifests + render.yaml
- ✅ Frontend demo mode (`?demo=true`) with deterministic shadow audit flow

**What's left is: (1) deploy the live demo (Phase 0), (2) finish 3 in-flight items
(Phase 1), (3) do the human legal/sales work (Phase 2), (4) provision the paid PHI
tier (Phase 3).** In that order. The code for all technical items is written;
remaining work is deployment, verification, and human actions.

---

## PHASE 0 — Ship the $0 synthetic demo THIS WEEK (no dependencies, do today)

You can put a working, live, no-PHI demo online right now with zero spend and zero
BAAs. This is your #1 leverage move: it becomes the asset for every sales/investor
conversation (Manual §3.2 Channel 1). Follow `docs/DEPLOY_CHEAP.md` Tier 0.

1. **Generate the three required secrets** (run locally):
   ```bash
   python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
   python3 -c "import secrets; print('BUDDI_STORAGE_KEY=' + secrets.token_hex(16))"
   python3 -c "import secrets; print('API_KEY=' + secrets.token_hex(32))"
   ```

2. **Create a free Postgres (Neon):** sign up at https://neon.tech → new project →
   in the SQL editor run `CREATE EXTENSION IF NOT EXISTS vector;` → copy the
   connection string (this is your `DATABASE_URL`).

3. **Deploy the backend to Render (log in to Render, not AWS):**
   - Push repo to GitHub if not already (`origin`).
   - https://dashboard.render.com → **New → Blueprint** → pick this repo (it reads
     the committed `render.yaml`, service name `buddi-api`, free plan, Oregon).
   - Fill the `sync:false` secrets when prompted: `DATABASE_URL` (Neon),
     `SECRET_KEY`, `BUDDI_STORAGE_KEY`, `API_KEY`, and **`BUDDI_BAA_CONFIRMED=0`**
     (keep it 0 — this is the fail-closed PHI guard; leave it 0 on all cheap tiers).

4. **Run the DB migrations once** (from your laptop against Neon):
   ```bash
   DATABASE_URL='postgresql://…neon.tech/neondb?sslmode=require' \
     ./venv/bin/python -m alembic upgrade head
   ```

5. **Deploy the frontend to Vercel:** import repo, **Root Directory = `frontend`**,
   set `VITE_API_BASE=https://<render-host>/api` and `VITE_API_KEY=<API_KEY>`.
   Then set `CORS_ORIGINS=https://<app>.vercel.app` on the Render backend and redeploy.

6. **Smoke test + show it:**
   ```bash
   BUDDI_BASE_URL=https://<render-host> BUDDI_API_KEY=<API_KEY> \
     ./venv/bin/python scripts/verify_system.py
   ```
   Open `https://<app>.vercel.app/?demo=true` → loads synthetic patient **PT-9012
   (Marcus Holloway)** and runs a deterministic shadow-mode audit with no LLM key.

7. **(Optional) Custom domain** `demo.buddi.health` — buy ~$10/yr, point a CNAME at
   Vercel/Render. **[HUMAN — H28]**

**Exit criteria:** a public link that runs the deterministic HCC demo end-to-end.

---

## PHASE 1 — Finish the 3 in-flight v1.0 items (Manual §2.2 Sprint A)

Do NOT add new features until these close (Manual headline judgment #2).

### 1A. Finish the synthetic FHIR bundle library  ✅ DONE
- 25 bundles generated (`evals/synthea/bundles/bundle_001…025`). 5-condition committed
  fixtures in `evals/synthea/fixtures/` (diabetes, CHF, COPD, CKD, sepsis).
- All validate against `FHIRBundle`. Demo routes live at `/api/demo/synthea/*`.

### 1B. Finish the eval harness + CI gate  🔶 IN PROGRESS (blocked on clinical advisor)
- 10-case seed set committed to `evals/golden/`. CI gate wired in `.github/workflows/main.yml`.
- `EVAL_PRECISION_FLOOR=0.60`, `EVAL_RECALL_FLOOR=0.60` configured.
- **[HUMAN — H29]** The clinical advisor must **grow the golden set from 10 to 100**
  cases — this is the hard blocker.
- **[HUMAN — H30]** Tune `BUDDI_HCC_CONFIDENCE_FLOOR` (placeholder 0.70) from eval results.

### 1C. Verify the Anthropic cutover + Merkle job end-to-end  ✅ CODE COMPLETE
- `llm_manager.py` uses Anthropic SDK directly; OpenAI embeddings-only guard active;
  BAA tripwire refuses PHI-shaped prompts while `BUDDI_BAA_CONFIRMED=0`.
- Daily Merkle-root job code path complete (`core/merkle.py`); needs cloud KMS key +
  Object Lock bucket provisioned for production verification.
- `grep -ri langchain` returns nothing in the prompt path. LangChain fully stripped.

---

## PHASE 2 — The human-only work that unlocks revenue (start in parallel, Week 1–3)

These cannot be coded. They gate everything past a synthetic demo. Start now.

- **[HUMAN — H15/H14]** Post the part-time **Clinical Advisor / MD** JD (Week 1),
  hire by Week 2. Board-certified PC/IM, 5+ yrs HCC fluency, has defended a CMS RADV
  audit. This one hire unlocks 1B labels, ICD specificity, and design-partner intros.
- **[HUMAN — H1/H2/H3]** File and **sign the BAAs**: Anthropic (healthcare program),
  OpenAI (embeddings-only), and **Google Cloud**. No real PHI flows until all three
  are signed. Update `docs/COMPLIANCE/baa_status.md` as each row flips to `signed: yes`.
- **[HUMAN — H4/H5]** Engage healthcare compliance counsel; start the HIPAA Security
  Risk Assessment (keep the output OUT of git).
- **[HUMAN — H6]** Pre-build the security-questionnaire response (CAIQ-Lite + addendum)
  so you don't lose 2–3 weeks per deal.
- **[HUMAN — H10/H9]** Begin **25–40 personalized outbound sends/week** to ACO Medical
  Directors / practice administrators; goal is the first design-partner LOI
  (10–25 physician risk-bearing group, ≥30% MA — *not a hospital*).

---

## PHASE 3 — Provision the compliant PHI tier on GCP (Manual §4.1/§4.3)

Only start once a design partner is close AND the BAAs are signed. This is where you
"log in to GCP" (not AWS). Follow `docs/DEPLOY_CHEAP.md` Tier 2 + `docs/CLOUD_DEPLOYMENT_GUIDE.md`.

- **[HUMAN — H19]** Create the GCP project; enable Cloud Run, Cloud SQL, KMS,
  Secret Manager, Artifact Registry.
- **[HUMAN — H20]** Cloud SQL Postgres 16 + pgvector, **private IP + CMEK**, daily
  backups (30-day retention, PITR). → set `DATABASE_URL`.
- **[HUMAN — H22]** GCS **Object Lock** bucket, COMPLIANCE mode, ~7-year retention.
- **[HUMAN — H23]** Cloud KMS key (EC P-256/384) for Merkle signing → set
  `BUDDI_AUDIT_KMS_PROVIDER=gcp`, `BUDDI_AUDIT_KMS_KEY=…`.
- Put all secrets in Secret Manager (never in repo).
- **Build + deploy the two services** (API + worker share the image, differ by CMD):
  ```bash
  gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/buddi/buddi-api:TAG
  gcloud run services replace infra/cloud-run-api.yaml    --region="$REGION"
  gcloud run services replace infra/cloud-run-worker.yaml --region="$REGION"
  ```
- Run Alembic as a **Cloud Run Job** each deploy (not on container start).
- **Turn PHI on, per tenant, only after counsel verifies the counter-signed BAA:**
  ```bash
  python scripts/provision_tenant.py --slug acme --name "Acme" --scopes clinician,ingest
  ```
  ```sql
  UPDATE tenants SET baa_confirmed = TRUE, baa_confirmed_at = NOW() WHERE id = '<tenant-uuid>';
  ```
  Then set `BUDDI_BAA_CONFIRMED=1` in the production env **only** once every required
  BAA is in place. Now `/ingest/fhir` accepts that tenant's real bundles.

---

## PHASE 4 — Pilot-ready hardening (Manual §2.2 Sprint B, Weeks 5–8)

Config/verification of already-built features + the scaling fixes from §4.2:

- **SMART-on-FHIR:** register at https://launch.smarthealthit.org, run the PKCE flow
  end-to-end, pull a real sandbox bundle through `/ingest/fhir`. Set production
  `SMART_CLIENT_ID` and `ALLOWED_FHIR_HOSTS`.
- **Webhooks:** verify all four events fire (`prior_auth_state.changed`,
  `hcc_suggestion.created`, `hcc_suggestion.approved`, `audit_event.flagged`); add
  retry/backoff.
- **[HUMAN — H35]** Stripe: create Products/Prices ($250–400/physician/mo flat +
  15–20% gain-share); set `STRIPE_PRICE_ID_MONTHLY`/`_GAIN_SHARE`; test Checkout + Portal.
- **Redis rate limiter (Bottleneck #1):** provision Memorystore in the private VPC,
  swap `RateLimitMiddleware` to Redis-backed slowapi (the `# TODO(human)` marks the spot).
- **pgvector HNSW (Bottleneck #2):** confirm the HNSW index migration
  (`alembic/versions/7a3c8d9f0142_rls_baa_hnsw.py`) is applied; benchmark at 1M chunks.
- **Async job path (Bottleneck #3):** confirm `/api/shadow/audit` returns a `job_id`;
  add per-tenant queue-depth alarm.
- **SLO dashboard:** point OTLP at Cloud Trace; build the SLO dashboard
  (`/shadow/audit` p95 <30s, verify=100%, error <0.5%); **[HUMAN — H26]** PagerDuty alerts.

**Pilot-ready gate (end Week 8):** design partner POSTs the first real de-identified
bundle and gets suggestions in <30s p95 with a verifying audit chain.

---

## The single most important sequence (if you read nothing else)

1. **Today:** ship the $0 Render/Vercel synthetic demo (Phase 0).
2. **Week 1:** post the MD advisor JD + file all three BAAs (Phase 2). Verify cutover (1C).
3. **Week 2–3:** hire the MD → label the golden set → eval CI gate goes green (1B).
4. **Week 3–5:** first design-partner LOI (Phase 2), pre-built security questionnaire.
5. **Week 5+:** provision GCP PHI tier (Phase 3) → pilot-ready hardening (Phase 4) → kickoff.

> Re-read Manual §1.3 (Reality Check), §4.2 (Scaling Bottlenecks), §7.1 (Existential
> Risks) before any external commitment. Keep `BUDDI_BAA_CONFIRMED=0` everywhere except
> the counsel-cleared production PHI tier.
