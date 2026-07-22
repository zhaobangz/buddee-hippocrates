# Product Truth — What Buddi Actually Does Today

**Owner:** Founder (Zhao)
**Cadence:** Updated every Friday during retrospective. Manual §7.2 Risk #3.
**Last reviewed:** 2026-07-20

This is the brutal-honest counterweight to the marketing site. The
manual prescribes reading this document *at the start of every sales
call* so you do not accidentally over-claim. Anything that ought to be
on this list but is on the marketing site instead is a counsel risk.

## What Buddi delivers, end-to-end, today

* **Authenticated FastAPI backend** with per-tenant API keys (Argon2 hashing +
  SHA-256 lookup), scope-based authorization, and row-level security policies
  on every clinical table.
* **Shadow-mode HCC suggestion path** with a confidence floor (0.70),
  a mandatory evidence quote, and an **LLM-as-judge second pass** that
  independently re-checks every uncertain-band suggestion (confidence
  in `[floor, 0.85)`) against the chart before surfacing it. Anything
  that fails any gate — or that the judge will not affirm — is abstained
  (fail-closed) and recorded in the audit chain.
* **Hash-chained `audit_events` table** with a daily Merkle root
  signed by a configured Ed25519 key (HMAC fallback in dev). Per-tenant
  chain isolation via Postgres advisory locks. Day-scoped verification
  walks from the prior day's tip.
* **FHIR R4 bundle ingest** with size-cap (2 MB), schema validation, and a
  BAA precondition that refuses bundles for unconfirmed tenants.
* **Async job queue** (`jobs` table) with idempotency keys, worker loop,
  and SSE progress streaming (`GET /api/jobs/{id}/stream`).
* **SMART-on-FHIR EHR connector** with OAuth2 PKCE standalone launch flow
  and encrypted token storage.
* **Webhooks** with HMAC-SHA256 signed delivery for 4 event types
  (`hcc_suggestion.created`, `hcc_suggestion.approved`,
  `prior_auth.state_changed`, `audit_event.flagged`).
* **Stripe billing** — Checkout, Customer Portal, and webhook handling.
* **OpenTelemetry tracing**, PII-redacted logging, rate limiting, and
  request-ID propagation.
* **Hosted synthetic-FHIR sandbox** (25 Safe-Harbor Synthea bundles, no PHI).
* **Eval regression gate in CI** with precision / recall / abstain
  metrics computed against a 10-case clinician-labeled seed set.
* **Red-team adversarial prompt suite** (50+ prompts) with nightly CI run.
* **React 19 + Vite operator UI** with dashboard, review queue, chat,
  and audit trail pages. `?demo=true` loads a deterministic synthetic
  patient workflow.

## What Buddi does NOT deliver today (and may be implied by marketing)

| Marketing claim                                                | Reality                                                                                  |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| "HIPAA-compliant"                                              | HIPAA *aligned*. Posture documented; security risk assessment not yet performed.         |
| "SOC 2 Type II"                                                | Not in audit window. Counsel-reviewed posture; no Type I or Type II report exists.       |
| "Integrates with Epic / Cerner"                                | Accepts a FHIR bundle. No SMART-on-FHIR launch flow, no App Orchard / CODE registration. |
| "Live AI agent" (hero chat)                                    | Live when Anthropic key + BAA confirmed; otherwise canned demo replies.                  |
| "50 health systems"                                            | Aspirational copy; remove or replace with `getWaitlistCount()`.                          |
| "Auto-submits prior authorizations"                            | Never. Buddi drafts; clinicians submit. This is a structural moat, not a TODO.           |
| "Tamper-proof audit log"                                       | Hash-chained + daily Merkle root, signed via Cloud KMS (GCP/AWS) and mirrored to an Object Lock bucket. Code path is live; awaiting cloud key + bucket provisioning. |
| "Fine-tuned on physician data"                                 | Anthropic Claude + pgvector RAG. No customer data used for training.                     |

## What is in flight (current sprint)

Per `Buddi_Strategic_Founders_Operating_Manual.pdf` §2.2 and the
30-day action tracker:

- [x] Daily Merkle-root background task (`backend/api.py`).
- [x] `core/merkle.py` with Cloud KMS (GCP/AWS) signing + Ed25519 / HMAC fallback, offline public-key verification, and Object Lock (WORM) export.
- [x] Postgres RLS migration (`7a3c8d9f0142`).
- [x] BAA tripwire (`core/llm_manager.py:_baa_guard`).
- [x] FHIR-ingest BAA precondition (`_enforce_baa_precondition`).
- [x] Anthropic-primary LLM stack; LangChain stripped from the prompt path.
- [x] HNSW index on `document_chunks.embedding` (§4.2 Bottleneck #2).
- [x] Confidence floor + abstain path (`core/agent.py:_apply_safety_floor`).
- [x] LLM-as-judge second pass (§7.2 Risk #2 #4, `core/agent.py:_judge_suggestions`).
- [x] Audit-chain moat test coverage (`tests/test_audit_merkle.py` — build / sign / verify / **tamper detection**).
- [x] Eval harness with CI gate (`evals/`).
- [x] 25 Synthea synthetic FHIR bundles + hosted demo route.
- [x] Prompt caching via Anthropic `cache_control` (`core/llm_manager.py`).
- [x] SMART-on-FHIR EHR connector with PKCE flow (`backend/smart_fhir.py`).
- [x] Async job queue with idempotency keys + SSE progress streaming (`core/jobs.py`, `core/worker.py`).
- [x] Webhooks with HMAC-signed delivery for 4 event types (`core/webhooks.py`).
- [x] Stripe billing integration — Checkout, Portal, webhook (`backend/billing.py`).
- [x] Rate limiting middleware + Request ID propagation (`backend/middleware.py`).
- [x] Red-team adversarial prompt suite with nightly CI run (`evals/red_team/`).
- [x] 10-case clinician-labeled golden eval set committed to `evals/golden/`.
- [x] Docker multi-stage build with non-root user + HEALTHCHECK (`Dockerfile`).
- [x] `render.yaml` for $0 Render Blueprint synthetic demo deploy.
- [x] GCP Cloud Run deployment manifests for API + worker (`infra/cloud-run-*.yaml`).
- [x] OpenTelemetry tracing wired throughout (`core/tracing.py`).
- [ ] OpenAI BAA filed and confirmed (founder action, week 1).
- [ ] Anthropic BAA filed and confirmed (founder action, week 1).
- [ ] Cloud KMS signing key (EC P-256) + Object Lock bucket provisioned and `BUDDI_AUDIT_KMS_*` / `BUDDI_AUDIT_ROOTS_BUCKET` set (code path ready; founder/infra action).
- [ ] Clinical advisor hired and named on the marketing site.
- [ ] Counsel review of TrustAnchor copy on `buddi-web`.
- [ ] First design-partner LOI signed.
- [ ] Redis-backed rate limiter (Memorystore provision + slowapi swap).
- [ ] Grow golden eval set from 10 to 100 clinician-labeled cases.

## Numbers the team can defensibly cite today

* **Audit chain verification rate:** 100% in CI (`GET /api/audit/verify`).
* **Routes registered:** 31 (`/health`, `/internal/health`, plus 29 `/api/*` routes
  across health, shadow-audit, prior-auth, jobs, demo, EHR, webhooks, audit-chain,
  billing, metrics, chat, and patient categories).
* **Synthetic bundle count:** 25 (generated by `evals/synthea/generate.py`).
* **Golden eval cases:** 10 clinician-labeled seed cases in `evals/golden/`.
* **Test coverage:** 18 test files covering API, auth, audit/Merkle, billing,
  jobs, rate limiting, FHIR/SMART, webhooks, red-team, migrations, partitioning,
  PHI security, RAG retrieval, agent safety, SLO metrics, and LLM provider.
* **Red-team prompts:** 50+ adversarial prompts across injection, PHI leakage,
  jailbreak, and confidence-inflation categories.

## Numbers the team must NOT cite today

* "94% confidence." This was a mock value in the marketing site.
  The agent's actual confidence distribution will be measured once
  the LLM-on eval is in place.
* "$82,000 / physician / year." This is a model output, not a
  measured pilot result. Cite it as "modeled" and link to the
  methodology.
* "4.2% capture-rate lift." Industry-standard reference number;
  cite the source, never claim it as Buddi's measured number.

## Next update

Friday 2026-07-25 — append the week's deltas above the prior entry
and update the "Last reviewed" header.
