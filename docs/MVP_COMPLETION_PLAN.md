# Buddee MVP Completion Plan

**Anchored to:** Strategic Founders Operating Manual 2nd Edition (June 2026)
**Codebase baseline:** v4.1 (pre-launch/foundation branch)
**Generated:** June 26, 2026

---

## Table of Contents

1. [Where We Stand — Status Against the Manual](#1-where-we-stand)
2. [Architecture & Tech Stack for Production](#2-architecture--tech-stack)
3. [Sprint A: Weeks 1–4 — Compliance Credibility (In Progress)](#3-sprint-a)
4. [Sprint B: Weeks 5–8 — Pilot-Ready](#4-sprint-b)
5. [Sprint C: Weeks 9–12 — First-Pilot Ops & PMF Read](#5-sprint-c)
6. [Deployment Cost Estimate](#6-deployment-costs)
7. [Human-Only Tasks (What Claude Can't Do)](#7-human-only-tasks)
8. [Week-by-Week Execution Tracker](#8-execution-tracker)

---

## 1. Where We Stand

### Status of Weeks 1–4 Compliance Credibility Sprint deliverables

| # | Deliverable | Status | Evidence |
|---|------------|--------|----------|
| 1 | Daily KMS-signed Merkle root → GCS Object Lock | ✅ SHIPPED | `core/merkle.py`, `BUDDI_AUDIT_KMS_PROVIDER`, `BUDDI_AUDIT_ROOTS_BUCKET` |
| 2 | OpenAI BAA confirmed; Anthropic BAA opened | ✅ SHIPPED | `BUDDI_BAA_CONFIRMED` env var, BAA tripwire in `llm_manager.py` |
| 3 | Anthropic-primary LLM cutover; LangChain stripped | ✅ SHIPPED | `core/llm_manager.py` uses Anthropic SDK; `core/rag_engine.py` uses OpenAI SDK directly |
| 4 | Postgres RLS policies via Alembic migration | ✅ SHIPPED | `core/db_session.py`, RLS migration in `alembic/versions/` |
| 5 | 100-encounter eval harness + CI regression gate | 🔶 IN PROGRESS | `EVAL_PRECISION_FLOOR`, `EVAL_RECALL_FLOOR` env vars exist; golden set labeling needed |
| 6 | TrustAnchor copy reconciled; SOC 2 claims removed | ✅ SHIPPED | Manual confirms "resolved in v2.0" |
| 7 | Synthea integration (25 synthetic bundles) + demo.buddi.health | 🔶 IN PROGRESS | `evals/synthea/bundles/`, `/api/demo/synthea` routes exist |
| 8 | First design-partner LOI (risk-bearing physician group) | ❌ CARRIED FORWARD | **Human task — see §7** |

### What the codebase actually has (v4.1 inventory)

**Backend (strong):**
- FastAPI v4.1 with auth-gated routes on every endpoint
- 16 SQLAlchemy tables with Alembic migrations
- SHA-256 hash-chained `audit_events` table (range-partitioned by month)
- Daily KMS-signed Merkle root export to GCS/S3 Object Lock
- Anthropic-primary LLM manager (`claude-opus-4-8` reasoning, `claude-sonnet-4-6` coding)
- Tier-based model routing with adaptive thinking for reasoning tier
- Prompt caching via Anthropic `cache_control`
- OpenAI embeddings-only guard (`_EmbeddingsOnlyOpenAI` proxy)
- pgvector-backed RAG engine with pluggable `Retriever` protocol
- LLM-as-judge second pass for uncertain-band HCC suggestions
- Confidence floor + mandatory evidence quote safety gates
- BAA tripwire (fail-closed PHI guard)
- PHI redaction in logs and OpenTelemetry spans
- Prompt-injection mitigation (XML-style `<clinical_note>` delimiters)
- Async job queue (`jobs` table) with idempotency keys
- Worker loop (in-process or standalone Cloud Run service)
- Stripe billing (Checkout, portal, webhook)
- Webhooks with HMAC-signed delivery
- SMART-on-FHIR EHR connector (launch + callback)
- SLO metrics endpoint (p95 latency, approval rates)
- Tenant-scoped DB sessions with Postgres RLS
- CORS allow-listing (no wildcards)
- Rate limiting middleware (in-process; Redis swap annotated)
- Dockerfile (non-root user, HEALTHCHECK, explicit COPYs)
- `render.yaml` for Render Blueprint deploy

**Frontend (dev-grade):**
- React 18 + Vite + Tailwind + Zustand
- Dashboard, Shadow, Audit, Chat pages
- API key in memory only (never localStorage)

**Tests & QA:**
- pytest suite for API/auth/audit/integration paths
- Eval harness env vars wired but golden set pending
- Red-team suite env vars wired (`ALERT_EMAIL`, `BUDDI_RED_TEAM_BASE_URL`)

### What the manual says must happen next (priority order)

The manual's headline judgments are explicit:

> 1. **The thesis is correct and the moat is the audit chain, not the LLM.** Build that artifact first and hardest.
> 2. **Ship the second half of v1.0 before adding any feature.** The Merkle root is shipped; now close the remaining gaps.
> 3. **Hire the clinical credibility before you hire the engineer.** A part-time MD advisor unlocks eval labels, ICD specificity, and design-partner intros.
> 4. **The first $1 of revenue must come from a physician group or billing co — not a hospital system.**

---

## 2. Architecture & Tech Stack

### Production Target (12-month — per manual §4.1)

```
┌──────────────────────────────────────────────────┐
│                 Customer EHR / Operator UI        │
└──────────────┬───────────────────────────────────┘
               │ HTTPS (tenant routing)
┌──────────────▼───────────────────────────────────┐
│     GCP Cloud Load Balancer + Cloud Armor (WAF)   │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│              Cloud Run: buddi-api                 │
│     FastAPI · min=2 max=20 · TLS 1.3 only        │
└──────┬────────────────────────┬──────────────────┘
       │                        │
┌──────▼──────┐    ┌────────────▼──────────────────┐
│  Cloud SQL  │    │       Cloud Tasks              │
│  Postgres 16│    │  async LLM, webhooks,          │
│  + pgvector │    │  prior-auth polling            │
│  + RLS      │    └───────────────────────────────┘
│  + CMEK     │
│  + priv IP  │
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────┐
│           GCS Object Lock bucket                  │
│    daily KMS-signed Merkle root                   │
└──────────────────────────────────────────────────┘

External APIs:
  • Anthropic API (BAA) — Claude Opus 4.8 / Sonnet 4.6
  • OpenAI API — embeddings ONLY (text-embedding-3-large)
  • Stripe API — billing

Observability:
  • Cloud Logging + Cloud Trace + SLO dashboard
  • PagerDuty on burn-rate alerts
```

### Tech Stack Breakdown

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Runtime** | Python 3.11 | Pinned in Dockerfile; 3.12+ deprecation surface not worth chancing |
| **API Framework** | FastAPI 0.135 | Already in use; async-native; strong OpenAPI docs |
| **LLM Provider (clinical)** | Anthropic (Claude Opus 4.8 / Sonnet 4.6) | BAA-eligible; tier-based routing for reasoning vs coding |
| **LLM Provider (embeddings)** | OpenAI (text-embedding-3-large) | Embeddings-only guard enforced; no PHI on this path |
| **Database** | PostgreSQL 16 + pgvector | Already modeled; RLS policies live; HNSW index pending |
| **Vector Store** | pgvector → Turbopuffer (at 5M+ chunks) | `Retriever` protocol already defined for clean swap |
| **ORM / Migrations** | SQLAlchemy 2.0 + Alembic | Already in use; forward-only migrations |
| **Cache / Rate Limiting** | Redis (Memorystore) via slowapi | Swap from in-memory; TODO annotated in middleware |
| **Job Queue** | PostgreSQL-backed `jobs` table → Cloud Tasks | Already built; Cloud Tasks for production scale |
| **Object Storage** | GCS Object Lock (WORM) | Daily KMS-signed Merkle root export |
| **KMS** | GCP Cloud KMS (EC P-256/P-384 or RSA) | HSM-backed signing key; private key never leaves HSM |
| **Secret Management** | GCP Secret Manager | No secrets in repos or env files |
| **CI/CD** | GitHub Actions | Lint → type-check → test → eval-gate → Docker build → security scan |
| **Container Registry** | Artifact Registry | GCP-native; vulnerability scanning |
| **Production Hosting** | GCP Cloud Run | Serverless; scales to zero; private VPC ingress |
| **Staging Hosting** | Cloud Run (separate service) | Synthetic-only; deployed on every merge to main |
| **Demo Hosting** | Render free tier or Cloud Run | Synthetic-only; $0 path; `BUDDI_BAA_CONFIRMED=0` |
| **Frontend Hosting** | Vercel (free) | Already configured; env vars for API base + key |
| **Monitoring** | Cloud Trace + Cloud Logging + Cloud Monitoring | OpenTelemetry already wired |
| **Alerting** | PagerDuty on SLO burn-rate alerts | p95 latency, error rate, audit-chain verify failure |
| **Billing** | Stripe (Checkout + Customer Portal) | Already integrated; gain-share + flat-fee pricing model |

### `$0` Demo Stack (no PHI, no BAA)

For investor demos, sales calls, and the public sandbox — keep `BUDDI_BAA_CONFIRMED=0`:

| Layer | Choice | Cost |
|-------|--------|------|
| Backend | Render free (Docker) | $0 |
| Database | Neon free (PG16 + pgvector) | $0 |
| Frontend | Vercel free | $0 |
| LLM | None (deterministic demo stub) | $0 |
| **Total** | | **$0/mo** |

→ Upgrade to Render Starter ($7/mo) for always-on (no cold starts).

---

## 3. Sprint A: Weeks 1–4 — Compliance Credibility (Finish In-Progress Items)

The Sprint A items marked SHIPPED are the foundation. These are the **open items** that need completion:

### A1. Complete Anthropic-Primary Cutover Verification

**Status:** Code is written; need verification pass.

- [ ] Verify `llm_manager.py` Anthropic SDK path works end-to-end with real keys
- [ ] Verify OpenAI embeddings-only guard catches non-embedding calls
- [ ] Verify BAA tripwire properly refuses PHI-shaped prompts when `BUDDI_BAA_CONFIRMED=0`
- [ ] Verify prompt caching (`cache_control`) reduces token cost on repeated clinical contexts
- [ ] Test fallback behavior when Anthropic key is missing → OpenAI fallback

### A2. Finish the Eval Harness (100-Encounter Golden Set)

**Status:** Env vars wired (`EVAL_PRECISION_FLOOR`, `EVAL_RECALL_FLOOR`). Golden set needs clinician labeling.

- [ ] Generate 100 de-identified encounter bundles from Synthea spanning 5 conditions (diabetes, CHF, COPD, CKD, sepsis) — **20 per condition**
- [ ] Have clinical advisor label the "correct" HCC/ICD-10 codes for each encounter
- [ ] Wire the golden set into `evals/run_eval.py`
- [ ] Add CI regression gate: fail if precision or recall drops >5% from `evals/baseline.json`
- [ ] Set `EVAL_PRECISION_FLOOR=0.60` and `EVAL_RECALL_FLOOR=0.60` for real-LLM nightly run
- [ ] Tune `BUDDI_HCC_CONFIDENCE_FLOOR` based on eval results (currently placeholder 0.70)

### A3. Complete Synthetic FHIR Bundle Library

**Status:** Directory structure exists. Finish the 25-bundle corpus.

- [ ] Generate 25 Safe-Harbor synthetic FHIR bundles via `evals/synthea/generate.py`
- [ ] Cover: diabetes-with-complications, CHF, COPD, CKD stage 3-5, sepsis, hypertension, dementia, depression, CAD, AFib, asthma, obesity, hypothyroidism, anemia, osteoporosis, arthritis, neuropathy, PAD, stroke, liver disease
- [ ] Verify each bundle validates against `FHIRBundle` schema
- [ ] Deploy hosted synthetic demo at `demo.buddi.health` with soft access code
- [ ] Set up the 5-bundle committed fixture set in `evals/synthea/fixtures/` (one per strategy-doc condition)

### A4. Operator UI Hardening

**Status:** Dev-grade React app exists. Needs hardening for hosted surface.

- [ ] Add proper auth flow (API key entry → validate → store in memory)
- [ ] Add tenant-scoping indicator (last 8 chars of tenant UUID from `/api/health`)
- [ ] Add "Demo mode" banner when `X-Response-Source: canned`
- [ ] Add loading states for all async operations
- [ ] Add error boundaries and graceful degradation
- [ ] Add SSE streaming for job progress (`/api/jobs/{id}/stream`)
- [ ] Ensure no PHI is stored in localStorage/sessionStorage
- [ ] Add screen-reader accessibility (WCAG 2.1 AA)
- [ ] Deploy behind API key auth at `app.buddi.health`

### A5. First Design-Partner Outreach (Human Task — see §7)

---

## 4. Sprint B: Weeks 5–8 — Pilot-Ready

These items make Buddee shippable to a paying design partner.

### B1. SMART-on-FHIR Launch Flow (Complete the EHR Connector)

**Status:** `backend/smart_fhir.py` exists with launch/callback routes. Needs real sandbox testing.

- [ ] Register with SMART Health IT public sandbox (https://launch.smarthealthit.org)
- [ ] Complete OAuth2 PKCE flow end-to-end
- [ ] Store EHR access tokens encrypted at rest
- [ ] Add token refresh logic
- [ ] Pull a real FHIR bundle from the sandbox and run it through `/ingest/fhir`
- [ ] Document the Epic App Orchard / Cerner Code registration process (for future)
- [ ] Add `ALLOWED_FHIR_HOSTS` validation in `fhir_client.py` for production safety

### B2. Webhooks for Integration Surface

**Status:** `core/webhooks.py` exists with HMAC-signed delivery. Needs the full event catalog.

- [ ] Ensure `prior_auth_state.changed` fires on every state transition
- [ ] Ensure `hcc_suggestion.created` fires on new shadow audit results
- [ ] Ensure `hcc_suggestion.approved` fires on clinician approval
- [ ] Ensure `audit_event.flagged` fires on high-risk events
- [ ] Add webhook delivery retry (exponential backoff, max 3 attempts)
- [ ] Add webhook delivery dashboard (success rate, latency, last delivery)
- [ ] Document webhook payload schemas for customer integration

### B3. Async Job Queue Hardening

**Status:** `core/jobs.py` + `core/worker.py` exist. Needs production hardening.

- [ ] Add per-tenant queue-depth monitoring
- [ ] Add PagerDuty alert when queue depth >500 jobs
- [ ] Add job timeout (mark as failed after 5 minutes)
- [ ] Add dead-letter queue for jobs that fail 3+ times
- [ ] Verify Cloud Run worker service config (`infra/cloud-run-worker.yaml`)
- [ ] Test Cloud Tasks integration as alternative to polling worker

### B4. Stripe Billing Go-Live

**Status:** `backend/billing.py` and routes exist. Needs real Stripe configuration.

- [ ] Create Stripe Products & Prices in dashboard:
  - Monthly flat fee: $250–400/physician/month
  - Gain-share: 15–20% of validated recovered revenue
- [ ] Set `STRIPE_PRICE_ID_MONTHLY` and `STRIPE_PRICE_ID_GAIN_SHARE` in production
- [ ] Configure Stripe Customer Portal branding
- [ ] Test Checkout flow end-to-end
- [ ] Test webhook event handling (`invoice.paid`, `customer.subscription.deleted`)
- [ ] Add subscription status to operator dashboard
- [ ] Create first invoice template

### B5. OpenTelemetry → Cloud Trace SLO Dashboard

**Status:** OTel already wired. Needs GCP-side configuration.

- [ ] Enable Cloud Trace in GCP project
- [ ] Point `OTLP_ENDPOINT` at Cloud Trace collector
- [ ] Create Cloud Monitoring SLO dashboard:
  - `/shadow/audit` p95 < 30s
  - `/prior-auth` p95 < 10s
  - Error rate < 0.5%
  - Audit-chain verify = 100%
  - OpenAI/Anthropic 429 rate < 1%
- [ ] Set up PagerDuty burn-rate alerts

### B6. Redis-Backed Rate Limiter

**Status:** In-memory token bucket with `# TODO(human): swap to Redis-backed slowapi`.

- [ ] Provision Redis Memorystore instance in private VPC
- [ ] Swap `RateLimitMiddleware` to `slowapi` with Redis backend
- [ ] Configure per-tenant rate limits
- [ ] Verify rate limiting works across multiple Cloud Run instances
- [ ] Add rate-limit headers to API responses (`X-RateLimit-Remaining`, etc.)

### B7. Postgres HNSW Index for pgvector

**Status:** No vector index — full table scans on cosine distance.

- [ ] Create Alembic migration:
  ```sql
  CREATE INDEX ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
  ```
- [ ] Add `chunk_id` FK column on `rag_retrievals` for join efficiency
- [ ] Benchmark retrieval latency at 10K / 100K / 1M chunks

### B8. First Pilot Kickoff

- [ ] Design partner signs LOI
- [ ] Provision tenant in production database
- [ ] Design partner POSTs first real de-identified FHIR bundle
- [ ] Verify suggestions return in <30s p95
- [ ] Verify audit chain is complete and verifiable
- [ ] Schedule weekly clinician-review cadence

---

## 5. Sprint C: Weeks 9–12 — First-Pilot Ops & PMF Read

### C1. Weekly Clinician-Review Cadence

- [ ] Structured weekly review with design partner's clinical team
- [ ] Log suggestion approval rate in audit chain (PMF signal)
- [ ] False-positive review with clinical advisor
- [ ] Track: approval rate, time-to-decision, codes surfaced vs accepted

### C2. Adversarial Red-Team Suite

**Status:** Env vars wired (`ALERT_EMAIL`, `BUDDI_RED_TEAM_BASE_URL`).

- [ ] Build 50+ jailbreak and PHI-leak prompt attempts
- [ ] Run nightly via `evals/red_team/run_red_team.py`
- [ ] Email alerts on any successful bypass
- [ ] CI gate: fail if any red-team prompt passes safety boundaries
- [ ] Include: prompt injection, role-play attacks, encoding tricks, multi-turn jailbreaks

### C3. Second Design Partner (Billing Services Company)

- [ ] Target: 5–50 employee billing/coding company serving 50–500 physicians
- [ ] Value prop: one integration → serve all their physician groups
- [ ] Multiply reach per pilot effort

### C4. First De-Identified Case Study

- [ ] Draft: "Practice X recovered $Y in suspected HCC dollars in 60 days, with Z% clinician approval rate, no auto-submitted claims"
- [ ] Legal review for de-identification
- [ ] Design partner approval
- [ ] Publish on marketing site — this is "the single most important page on the marketing site" per manual

### C5. Audit Events Partitioning Verification

**Status:** Range-partitioned by month (migration exists).

- [ ] Verify partition pruning works for time-bounded queries
- [ ] Test at 5M+ row scale
- [ ] Ensure `GET /api/audit/verify` with day filter uses partition pruning

---

## 6. Deployment Costs

### Tier 0: $0/mo Synthetic Demo (NOW)

| Resource | Provider | Cost |
|----------|----------|------|
| Backend (Docker) | Render free | $0 |
| Database (PG16 + pgvector) | Neon free | $0 |
| Frontend | Vercel free | $0 |
| Domain | Cloudflare | ~$10/yr |
| LLM | None (stub) | $0 |
| **Monthly total** | | **$0** |

### Tier 1: ~$7–15/mo Always-On Demo

| Resource | Provider | Cost |
|----------|----------|------|
| Backend | Render Starter | $7/mo |
| Database | Neon free | $0 |
| Frontend | Vercel free | $0 |
| LLM (synthetic only) | Anthropic (budget-capped) | $0–5/mo |
| **Monthly total** | | **~$7–15** |

### Tier 2: ~$40–120+/mo Compliant Pilot (Real PHI)

| Resource | Provider | Cost |
|----------|----------|------|
| Cloud Run (API) | GCP | ~$0–20 (near-zero at pilot volume) |
| Cloud Run (Worker) | GCP | ~$0–10 |
| Cloud SQL (small HA) | GCP | ~$30–80 |
| Memorystore (Redis) | GCP | ~$10–20 |
| Secret Manager | GCP | ~$2–5 |
| Cloud KMS | GCP | ~$2–5 |
| Cloud Logging/Trace | GCP | ~$5–15 |
| Artifact Registry | GCP | ~$1–5 |
| Load Balancer + Cloud Armor | GCP | ~$20–30 |
| Anthropic API | metered | ~$0.30–0.40/encounter target |
| Stripe | 2.9% + $0.30 | Variable |
| Domain | Cloudflare | ~$10/yr |
| **Monthly estimate** | | **~$80–200** |

### Startup One-Time Costs

| Item | Cost |
|------|------|
| HIPAA Security Risk Assessment (compliance counsel) | $15–30k |
| Cyber + Tech E&O Insurance (healthcare-AI rider) | $5–15k/yr |
| SOC 2 Type I readiness assessment | $10–20k |
| Clinical advisor stipend (part-time) | $3–5k/mo |
| Domain registration | ~$10/yr |
| Conference sponsorship (AHIMA/HFMA/RISE) | $15–30k each |

---

## 7. Human-Only Tasks

These tasks **must be done by a human** (Zhao or the founding team). They cannot be automated by Claude or any AI tool.

### Legal & Compliance (Existential Priority)

| # | Task | Priority | Manual Reference |
|---|------|----------|------------------|
| H1 | **Confirm Anthropic BAA is executed in writing.** The code has the tripwire and the Anthropic SDK, but the legal agreement must be signed by both parties. Without this, no real PHI can flow. | 🔴 CRITICAL — Week 1 | §7.2 Risk #1 |
| H2 | **Confirm OpenAI BAA is on file** (for embeddings path — no PHI on OpenAI prompt path). | 🔴 CRITICAL — Week 1 | §7.2 Risk #1 |
| H3 | **Sign Google Cloud BAA.** Required before any PHI touches Cloud SQL, Cloud Run, or GCS. | 🔴 CRITICAL — Week 2 | §4.3 |
| H4 | **Engage healthcare compliance counsel.** For HIPAA security risk assessment ($15–30k), DPA template, liability-flowdown contract language, counsel review of trust-anchor copy. | 🔴 CRITICAL — Week 3 | §7.2 Risk #1 |
| H5 | **Complete HIPAA Security Risk Assessment (SRA).** Output is a privileged report — do NOT commit to git. | HIGH — Month 1 | §7.2 Risk #1 |
| H6 | **Pre-build security questionnaire response document (CAIQ-Lite + Buddee addendum).** Before the first pilot ask, or you lose 2–3 weeks per deal. | HIGH — Week 2 | §3.4 |
| H7 | **File SOC 2 Type I readiness.** The manual says SOC 2 Type II "audit in progress" copy was a soft falsehood that needed to come down. Replace with truthful posture. | MEDIUM — Month 3 | §1.3 Item #3 |
| H8 | **Draft and review privacy policy + security whitepaper.** Required before any paid customer signs. | MEDIUM — Week 4 | §3.4 |

### Business Development & Sales

| # | Task | Priority | Manual Reference |
|---|------|----------|------------------|
| H9 | **Secure first design-partner LOI.** Target: 10–25 physician primary care group with risk-bearing contracts and ≥30% Medicare Advantage mix. NOT a hospital system. | 🔴 CRITICAL — Week 5 | §2.2, §3.1 |
| H10 | **Conduct 25–40 personalized outbound sends/week.** LinkedIn + email to ACO Medical Directors and Practice Administrators. Include one specific HCC capture insight from the org's public Medicare Compare data. | HIGH — Weekly | §3.2 Channel 1 |
| H11 | **Write first long-form compliance content piece** (2,500 words). Topic: "How to defend a CMS RADV audit when your AI tool surfaced the suspected HCC code." Syndicate to AHIMA/HFMA/AAPC newsletters. | MEDIUM — Week 3 | §3.2 Channel 2 |
| H12 | **Identify and register for 1 conference** (AHIMA, RISE Nashville, or HFMA). Not HIMSS until v2.0. Format: 30-min talk + live demo walkthrough. Cost: $15–30k. | MEDIUM — Month 3 | §3.2 Channel 3 |
| H13 | **Create one-page comparison sheet:** Buddee vs Optum/3M 360/Epic Cogito. The #3 buyer objection. | MEDIUM — Week 6 | §3.3 |

### Hiring & Team

| # | Task | Priority | Manual Reference |
|---|------|----------|------------------|
| H14 | **Hire part-time Clinical Advisor / Medical Director** (Hire #1). 0.5–1.0% equity, $3–5k/month stipend, 8–12 h/week. Criteria: board-certified primary care/IM; 5+ years HCC coding fluency; has personally defended a CMS RADV audit; U.S.-based; no conflicts with another HCC vendor. | 🔴 CRITICAL — Week 2 | §5.2 |
| H15 | **Post clinical-advisor JD.** The manual says this is the Week 1 COO priority. | HIGH — Week 1 | §5.1 |
| H16 | **Hire fractional ops/EA support** (~$1–2k/month). 5 h/week back = 12% capacity unlock. | MEDIUM — Month 1 | §7.2 Risk #3 |
| H17 | **Hire Lead Full-Stack Engineer** (Hire #2, Month 4). $180–220k + 1–2% equity. Criteria: 7+ years production SaaS; Python + TypeScript fluent; prior healthcare or fintech; FastAPI, Postgres, React, OTel; shipped under SOC 2 Type II. | PLANNED — Month 4 | §5.2 |
| H18 | **Hire Founding RCM Marketer** (Hire #3, Month 6). $130–180k + 0.5–1% equity. Only after first case study exists. | PLANNED — Month 6 | §5.2 |

### Infrastructure & Operations

| # | Task | Priority | Manual Reference |
|---|------|----------|------------------|
| H19 | **Provision GCP project** with Cloud SQL (CMEK + private IP), Cloud KMS, Secret Manager, Artifact Registry. | HIGH — Week 2 | §4.3 |
| H20 | **Set up Cloud SQL automated daily backups** (30-day retention, PITR enabled). | HIGH — Week 2 | §4.3 |
| H21 | **Run quarterly restore drill** — founder runs a full backup restore. | RECURRING | §4.3 |
| H22 | **Provision GCS Object Lock bucket** with COMPLIANCE mode retention (2,555 days ≈ 7 years). | HIGH — Week 2 | §4.1 |
| H23 | **Configure Cloud KMS key** (EC P-256/P-384 recommended) for Merkle root signing. Set `BUDDI_AUDIT_KMS_PROVIDER=gcp` and `BUDDI_AUDIT_KMS_KEY`. | HIGH — Week 2 | §4.1 |
| H24 | **Set up CI/CD pipeline** in GitHub Actions: lint → type-check → test → eval-gate → Docker build → security scan → deploy to staging. | HIGH — Week 3 | §4.3 |
| H25 | **Configure production deploy workflow:** git tag `v*.*.*` signed by founder's GPG key → Cloud Run production. | MEDIUM — Week 4 | §4.3 |
| H26 | **Set up PagerDuty** with on-call rotation (founder + advisor in v1.0). | MEDIUM — Week 4 | §4.3 |
| H27 | **Write incident response runbook** (`docs/INCIDENT_RESPONSE.md`). Severity tiers, CMS-incident thresholds (24h notification to counsel). | MEDIUM — Week 4 | §4.3 |
| H28 | **Set up domain + DNS:** `buddi.health`, `api.buddi.health`, `demo.buddi.health`, `app.buddi.health`. | HIGH — Week 3 | §4.3 |

### Clinical & Product

| # | Task | Priority | Manual Reference |
|---|------|----------|------------------|
| H29 | **Label the 100-encounter golden set** (with clinical advisor). This gates the eval harness and the CI regression gate. Each encounter needs: confirmed HCC/ICD-10 codes, whether the code is clearly documented, and edge cases noted. | HIGH — Week 3 | §2.2, §7.2 Risk #2 |
| H30 | **Tune the confidence floor** (`BUDDI_HCC_CONFIDENCE_FLOOR`) based on eval results. Current placeholder is 0.70. The eval harness is what tunes this. | HIGH — After A2 | §7.2 Risk #2 |
| H31 | **Weekly written retrospective** in `docs/RETRO/`. Update the manual's Appendix B tracker. | RECURRING — Weekly | §7.2 Risk #3 |
| H32 | **Re-read §1.3 (Reality Check), §4.2 (Scaling Bottlenecks), and §7.1 (Existential Risks)** before any external commitment. | RECURRING — Before any sales call | Manual closing note |
| H33 | **Time-block calendar:** CTO mornings (8am–1pm), CEO afternoons (sales/advisor/counsel calls). Pin for the entire 12-week sprint. | RECURRING — Daily | §5.1, §7.2 Risk #3 |
| H34 | **Quarterly deload week** — one full week off every 12 weeks. "Load-bearing infrastructure, not a luxury." | RECURRING — Quarterly | §7.2 Risk #3 |

### Financial & Administrative

| # | Task | Priority | Manual Reference |
|---|------|----------|------------------|
| H35 | **Create Stripe account** and configure Products & Prices matching the gain-share + flat-fee model. | HIGH — Week 7 | §2.4 |
| H36 | **Purchase cyber + tech E&O insurance** with healthcare-AI rider (~$5–15k/year for $1–5M coverage). Required before any pilot over $50k ARR. | HIGH — Month 2 | §7.2 Risk #2 |
| H37 | **Set up business banking, accounting, and invoicing.** | MEDIUM — Month 1 | — |
| H38 | **GPY key for Merkle root + production tags:** store in fireproof safe with documented recovery access. | HIGH — Week 4 | §4.3, §7.3 Risk #10 |

---

## 8. Week-by-Week Execution Tracker

Refreshed from Manual Appendix B. Check items as completed.

### Week 1 (current)
- [ ] Confirm Anthropic BAA executed in writing
- [ ] Finalize Anthropic-primary cutover verification in `llm_manager.py`
- [ ] Verify LangChain removal is complete (zero imports)
- [ ] Verify daily Merkle-root job exports to GCS Object Lock without gaps
- [ ] Time-blocking calendar confirmed: CTO mornings, CEO afternoons
- [ ] Post clinical-advisor JD
- [ ] Begin 25-bundle Synthea generation

### Week 2
- [ ] Clinical advisor identified and in conversation
- [ ] GCP project provisioned: Cloud SQL + KMS + Secret Manager + Artifact Registry
- [ ] GCS Object Lock bucket provisioned with 7-year retention
- [ ] 25 synthetic FHIR bundles generated and validated
- [ ] Public synthetic-only `demo.buddi.health` deployed
- [ ] Security questionnaire (CAIQ-Lite + addendum) pre-built
- [ ] First 5 outbound conversations with ACO Medical Directors started

### Week 3
- [ ] Clinical advisor starts (Hire #1)
- [ ] 100-encounter golden set labeling begins
- [ ] CI/CD pipeline green: lint → test → eval-gate → build → security scan
- [ ] First long-form compliance content drafted (clinician co-author)
- [ ] Domain + DNS configured: `buddi.health`, `api.buddi.health`, `demo.buddi.health`
- [ ] Operator UI hardening: auth flow, tenant scoping, demo banner

### Week 4
- [ ] Eval harness with CI regression gate live
- [ ] Operator UI hardened and deployed at `app.buddi.health`
- [ ] HIPAA security risk assessment engaged with counsel
- [ ] First design-partner LOI in motion (risk-bearing group)
- [ ] Incident response runbook written
- [ ] GPG key for Merkle root stored with recovery access documented
- [ ] Production deploy workflow (signed tag → Cloud Run) configured

### Week 5
- [ ] First design-partner LOI signed
- [ ] SMART-on-FHIR launch flow tested against public sandbox
- [ ] Pilot kickoff scheduled

### Week 6
- [ ] SMART-on-FHIR EHR connector complete
- [ ] Webhooks live for all four event types
- [ ] HNSW index migration applied to pgvector

### Week 7
- [ ] Stripe billing go-live (Products, Prices, Checkout, Portal)
- [ ] Redis-backed rate limiter (Memorystore + slowapi)
- [ ] Cloud Tasks integration for async job queue

### Week 8
- [ ] OpenTelemetry → Cloud Trace SLO dashboard online
- [ ] PagerDuty alerts configured
- [ ] **Pilot kickoff:** design partner POSTs first real de-identified bundle
- [ ] Verify: suggestions <30s p95, audit chain verifiable

### Weeks 9–12
- [ ] Weekly clinician-review cadence with design partner
- [ ] Adversarial red-team suite running nightly
- [ ] Second design partner (billing services company) signed
- [ ] First de-identified case study published
- [ ] `audit_events` partitioning verified at scale

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `core/agent.py` | RCM orchestrator — shadow audit, prior auth, intent routing |
| `core/llm_manager.py` | Anthropic-primary LLM adapter with BAA tripwire |
| `core/rag_engine.py` | pgvector RAG with OpenAI embeddings-only guard |
| `core/safety.py` | PII redaction, safety boundaries, sanitize_response |
| `core/merkle.py` | Daily KMS-signed Merkle root + GCS Object Lock export |
| `core/models.py` | 16 SQLAlchemy ORM models |
| `core/schemas.py` | Pydantic schemas (ShadowModeResponse, PriorAuthDraft, FHIRBundle) |
| `core/jobs.py` | Async job queue (enqueue, claim, complete, fail) |
| `core/worker.py` | Background worker loop (in-process or standalone) |
| `core/db_session.py` | Tenant-scoped RLS DB sessions |
| `core/config.py` | Pydantic-settings with mandatory secrets validation |
| `core/phi_guard.py` | BAA precondition enforcement for PHI processing |
| `core/webhooks.py` | HMAC-signed webhook dispatch |
| `backend/api.py` | FastAPI v4.1 route table (~2,900 lines) |
| `backend/auth.py` | API key + Bearer auth with tenant scoping |
| `backend/fhir_client.py` | FHIR bundle adapter |
| `backend/smart_fhir.py` | SMART-on-FHIR OAuth2 launch flow |
| `backend/billing.py` | Stripe Checkout + Portal + webhook |
| `backend/middleware.py` | RequestID + rate limiting middleware |
| `alembic/` | Database migration scripts |
| `frontend/` | React 18 + Vite operator UI |
| `tests/` | pytest suite |
| `Dockerfile` | Production image (non-root, HEALTHCHECK, explicit COPYs) |
| `render.yaml` | Render Blueprint for $0 demo deploy |
| `docs/DEPLOY_CHEAP.md` | Tier 0–2 deployment guide |
| `.env.example` | All configuration knobs documented |

---

> **Re-read before any external commitment:** Manual §1.3 (Reality Check), §4.2 (Scaling Bottlenecks), §7.1 (Existential Risks).
>
> This document is a forecast, not a promise. Update it weekly during retrospective.
>
> 🤖 Generated with [Claude Code](https://claude.com/claude-code) — reviewed and approved by founding team before execution.
