# Buddee — Projected Technical Build Plan (as Claude Code Prompts)

**Version:** 1.0 · **Compiled:** July 21, 2026
**Baseline:** repo `buddee-health-hippocrates` @ commit `d016d93` (v4.2, July 20, 2026)
**Source of truth for scope:** *Strategic Founders Operating Manual, 4th Edition (v4.0)* — §2.2 (three‑sprint 90‑day roadmap), §4 (architecture/ops), §2.1 (visible debt), §6 (KPIs), §7 (risk).
**Audience:** CTO (Zhao), executing via **Claude Code CLI** wired to **DeepSeek v4 (max effort)** — routing pinned in `.claude/settings.local.json`.

---

## 0. How to use this document

This is not a spec — it is a **queue of copy‑paste prompts for Claude Code**, sequenced to close the *remaining* technical MVP work and nothing else. Each prompt:

- cites the **manual section** that authorizes the work (per your instruction to back every decision to the manual);
- names the **exact files / env vars** confirmed present in the repo at `d016d93`;
- carries a **recommended model** and a **done‑when gate** copied from the manual's acceptance gates (§2.2).

### Model routing convention (Claude Code CLI → DeepSeek v4, max effort)

These prompts run in **Claude Code CLI** pointed at **DeepSeek v4** through its Anthropic‑compatible endpoint. The routing is already pinned in `.claude/settings.local.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_MODEL": "deepseek-v4-pro",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-pro[1m]",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": ""
  }
}
```

`ANTHROPIC_DEFAULT_OPUS_MODEL` is empty, so the Opus slot falls back to `ANTHROPIC_MODEL` = `deepseek-v4-pro`; the Sonnet slot is the 1M‑context `deepseek-v4-pro[1m]`. There is exactly **one model** here — **DeepSeek v4 Pro** — and every prompt runs it at **maximum reasoning effort ("max effort")**. Turn max effort on once per session and keep it on:

- Add `"MAX_THINKING_TOKENS": "32000"` to the `env` block above (or `export MAX_THINKING_TOKENS=32000` before launching `claude`) so DeepSeek v4 gets the full extended‑thinking budget on every turn.
- If a prompt still comes back shallow, prepend `ultrathink` to force Claude Code's top thinking tier for that turn.

The two tags below only tell you which Claude Code model **slot** to select with `/model`; both resolve to DeepSeek v4 Pro and differ only by context window:

| Tag in this doc | Use for | `/model` slot | Resolves to |
|---|---|---|---|
| **[DS‑MAX]** | Architecture, clinical/eval logic, security‑sensitive paths, anything touching the audit chain or a clinical prompt | `opus` | `deepseek-v4-pro` @ max effort |
| **[DS‑1M]** | Mechanical wiring, config templating, scripts, tests, docs, and any wide multi‑file refactor | `sonnet` | `deepseek-v4-pro[1m]` (1M‑token context) @ max effort |

> Reach for **[DS‑1M]** when a prompt spans many files/configs at once (it carries the 1M‑token window); reach for **[DS‑MAX]** for the deepest clinical/security reasoning. Same DeepSeek v4 brain either way — keep max effort engaged for both.

### Guardrails to paste into EVERY prompt (non‑negotiable invariants)

These come straight from the manual and are enforced in code today; every prompt below assumes them:

1. **BAA tripwire stays fail‑closed.** `BUDDI_BAA_CONFIRMED=0` everywhere until counsel confirms; never weaken `_enforce_baa_precondition` / `core/phi_guard.py` (manual §7.1, §4.1). No real PHI, ever, in any prompt.
2. **Nothing auto‑submits.** No new endpoint may write to a payer/EHR. Any submission‑path change requires *both founders' sign‑off* (manual §1.3, §5.2).
3. **Claims discipline is code.** Do not make the product claim anything `docs/PRODUCT_TRUTH.md` / `growth/outreach/claims_lint.py` would reject (manual §1.3, §8.2, CTO veto §5.2).
4. **Never change a clinical prompt path "on vibes."** Any change to `core/agent.py` reasoning, model pins, or the confidence floor must go behind the eval gate (manual §4.4).
5. **Keep CI green.** `.github/workflows/main.yml` (ruff · migrations · pytest · eval gate · synthea smoke · pip‑audit · gitleaks · docker build · frontend build) must pass on every PR (manual §4.3).

---

## 1. Ground‑truth reconciliation (why this plan differs from `docs/TECHNICAL_BUILD_PLAN.md`)

The prior `TECHNICAL_BUILD_PLAN.md` (v5.0) and `MVP_COMPLETION_PLAN.md` predate the v4.2 baseline and list several items as "gaps" that **already shipped**. Prompts are written against reality, not the stale docs. Verified at `d016d93`:

| Item the old docs call "TODO" | Actual state @ d016d93 | Consequence for this plan |
|---|---|---|
| "No CI/CD" | **Live** — `main.yml`, `deploy-staging.yml`, `deploy-prod.yml`, `red_team.yml` | No "build CI" prompts. We only *extend* CI (Trivy, mypy burn‑down, LLM‑on eval). |
| "In‑memory rate limiter, `# TODO(human)`" | **Already slowapi + Redis** (`RateLimitMiddleware`, `REDIS_URL`, `BUDDI_RATE_LIMIT_DISABLED`). The only real `TODO(human)` is conversational memory in `core/memory.py`. | No limiter rewrite. Only *provision Memorystore + verify multi‑instance* in Sprint C. |
| "Operator UI dev‑grade, no auth/SSE/error states" | **Polished** — auth/API‑key flow, SSE progress, error/empty states, `?demo=true`, `SLOPanel` all present | No UI rebuild. Only demo‑determinism polish + MFA when hosted. |
| "119 tests" | **115 tests** (migration cleanup, CI‑enforced) | Matches manual §"About This Edition." |
| "Golden set = 25 bundles, eval gate TODO" | **Eval gate live**; **10 labeled seed cases**; 100‑case set blocked on MD advisor | The eval work is *labeling tooling + floor tuning + LLM‑on gate*, not building the harness. |
| Merkle / KMS / Object Lock | **Code‑complete**; awaiting `BUDDI_AUDIT_KMS_PROVIDER` key + `BUDDI_AUDIT_ROOTS_BUCKET` provisioning | Sprint C provisioning, not new code. |

**Net:** the genuinely remaining technical MVP surface is smaller and later‑stage than the old plan implies. It is exactly the manual §2.2 CTO column: **publish the demo → label + tune the eval → verify integrations (SMART/webhooks/Stripe) → provision the PHI tier → stand up SLO/alerting → pilot.**

---

## 2. Sprint A — "Publish, Submit & Form" (Jul 20 – Aug 2)

**Manual acceptance gate (§2.2):** *"A stranger runs the PT‑9012 deterministic demo at a public URL in <60s."* This is the single highest‑leverage item in the company and the oldest open commitment in the book (manual Exec Summary, §2.1, §2.2 Sequencing Rule). CTO owns it; target 48 hours.

---

### P‑A1 · Publish the ~$0 public synthetic demo  **[DS‑1M]**
**Backing:** §2.2 Sprint A (CTO), §4.1 Tier 0/1, Appendix B Week 1; `docs/DEPLOY_CHEAP.md`.
**Targets:** `render.yaml`, `docs/DEPLOY_CHEAP.md`, `scripts/verify_system.py`, `frontend/` env config, `.env.example`.

```
Context: buddee-health-hippocrates @ d016d93. I'm publishing the free public synthetic
demo per docs/DEPLOY_CHEAP.md Tier 0/1: Neon (Postgres 16 + pgvector) → Render Blueprint
(render.yaml) → Vercel (operator UI). This must be a zero-PHI, zero-LLM-spend deterministic
demo.

INVARIANTS (do not violate):
- BUDDI_BAA_CONFIRMED=0 on every service; LLM API keys unset; deterministic stub path only.
- Nothing auto-submits. No real PHI. Keep CI (.github/workflows/main.yml) green.

Do:
1. Audit render.yaml and the frontend Vite env config for anything that assumes localhost
   or a live LLM. Produce a single, ordered deploy runbook delta in docs/DEPLOY_CHEAP.md
   with the exact env vars each of the three tiers needs (Neon DATABASE_URL, Render service
   env incl. BUDDI_BAA_CONFIRMED=0, Vercel VITE_API_BASE_URL).
2. Make the frontend read the API base URL from an env var (VITE_API_BASE_URL) with a safe
   default; do not hardcode the Render host.
3. Extend scripts/verify_system.py so it can run against a REMOTE base URL (arg/env),
   asserting: /health OK, the PT-9012 deterministic demo returns suggestions end-to-end in
   <60s with zero LLM calls, and GET /api/audit/verify returns 100%.
4. Add a shareable deep link that boots the demo directly into the PT-9012 flow
   (?demo=true), and document it.
Output the diff + the exact command sequence to deploy and to verify against the live host.
```
**Done‑when (gate):** a stranger opens the Vercel URL, runs PT‑9012, sees suggestions in <60s, and `verify_system.py --base-url <public>` passes (manual §2.2 Sprint A gate; Appendix B Week 1).

---

### P‑A2 · Harden demo determinism & the "no‑LLM, no‑PHI" proof  **[DS‑MAX]**
**Backing:** §1.3 (claim "Public live demo 50%" → must be trustworthy), §4.1 (PHI guard fail‑closed), §2.3 (demo is the reply‑rate lever).
**Targets:** `core/phi_guard.py` (read‑only assert), `core/llm_manager.py`, demo path in `backend/api.py`, `tests/`.

```
Context: buddee-health-hippocrates @ d016d93. Before this demo is public it must be provably
safe and deterministic. Do NOT change clinical logic behavior — only add guards/tests.

Do:
1. Add a test that boots the app with BUDDI_BAA_CONFIRMED=0 and NO LLM keys, hits the
   PT-9012 demo endpoint, and asserts (a) a deterministic, byte-stable response, (b) zero
   outbound LLM calls (mock/patch the client and assert it was never invoked), (c) the
   response carries the demo/canned source header the frontend uses for its "DEMO MODE"
   banner.
2. Add a test asserting /ingest/fhir returns HTTP 412 for an unconfirmed tenant
   (_enforce_baa_precondition) so we can never accidentally accept a bundle on the public
   tier.
3. Confirm no code path logs raw note text; if any span/log line could, redact it.
Report which tests were added and paste the green pytest output summary.
```
**Done‑when:** new tests pass in CI; demo is byte‑stable and provably LLM‑free (supports the honest "deterministic synthetic demo, zero LLM spend" claim, manual §1.3).

---

### P‑A3 · Demo video capture harness (optional aid)  **[DS‑1M]**
**Backing:** §2.2 Sprint A ("record the 60‑second demo video"), §10.3 (YC weighs the video).
**Targets:** `scripts/` (new `scripts/demo_walkthrough.md` + optional Playwright script).

```
Context: I need to record a 60-second walkthrough of the public demo (PT-9012). Produce a
tight, timestamped shot list (0:00–0:60) that shows: land on demo → Run Shadow Audit →
suggestions with evidence quotes + confidence → open Audit page → click "Verify Chain" →
show 100% verified. Optionally scaffold a Playwright script that drives this exact path
against VITE_API_BASE_URL so I can screen-record a clean, deterministic take. No narration
copy that violates docs/PRODUCT_TRUTH.md.
```
**Done‑when:** a repeatable, claims‑safe walkthrough exists (video recording itself is a human step).

> Sprint A non‑CTO items (YC submission, incorporation decision by Aug 1, founder memo, BAA packets, MD advisor handshake) are **CEO/CFO‑owned** (manual §2.2, §5.1, §11) and intentionally have no Claude Code prompts.

---

## 3. Sprint B — "Label, Verify & Bank" (Aug 3 – Aug 30)

**Manual acceptance gate (§2.2):** *"Eval gate green with real LLM + labeled set; ... security questionnaire pre‑built."* CTO owns the eval + integration verification lanes.

---

### P‑B1 · 100‑case golden‑set labeling pipeline  **[DS‑MAX]**
**Backing:** §2.2 Sprint B (CTO + MD), Figure 0 ("Golden‑set eval BLOCKED → UNBLOCKING"), §6.1 (defensible accuracy), Appendix A (`evals/`).
**Targets:** `evals/golden/`, `evals/run_eval.py`, `evals/README.md`, new `scripts/ingest_golden_labels.py`.

```
Context: buddee-health-hippocrates @ d016d93. We have 10 labeled seed cases in evals/golden/
(clinician_id = "placeholder:awaiting-advisor-hire-1"). The MD advisor will label 100 cases
at ~25/week. Build the tooling so their labels drop in cleanly — do NOT invent clinical
labels yourself.

Do:
1. Define/validate a JSON schema for a golden case matching the existing case_*.json shape
   (expected_codes, acceptable_alternatives, must_abstain_codes, evidence spans, edge notes,
   clinician_id, condition category). Document it in evals/README.md.
2. Write scripts/ingest_golden_labels.py that takes an MD-provided CSV/sheet + the source
   Synthea bundle and emits validated case_*.json files into evals/golden/v1/, failing loudly
   on schema violations or codes that don't map to V28 (manual §8.1: PY2026 is 100% V28).
3. Add a coverage report: cases per condition category vs the 20-each target
   (diabetes/CHF/COPD/CKD + one more), so we can see the set fill to 100.
4. Ensure evals/run_eval.py loads evals/golden/v1/ when present, else the seed set.
Keep clinical content empty/placeholder — this is plumbing for the MD's real labels.
```
**Done‑when:** an MD can hand over a sheet and get validated golden cases with a coverage dashboard; harness loads them (manual §2.2 Sprint B).

---

### P‑B2 · Add citation‑accuracy metric to the eval harness  **[DS‑MAX]**
**Backing:** §1.2 (mandatory verbatim evidence quote), §1.3 ("Defensible accuracy numbers 35%"), §6.1 (evidence‑quote coverage = 100%).
**Targets:** `evals/metrics.py`, `evals/run_eval.py`, `evals/baseline.json`.

```
Context: evals/metrics.py currently computes precision@3, recall@3, abstain_rate, and
must_abstain_violations, but NO citation metric — yet a verbatim evidence quote is a core
product gate (manual §1.2). Add citation accuracy without weakening existing metrics.

Do:
1. Add citation_accuracy = fraction of surfaced suggestions whose evidence quote is a
   verbatim substring of the source note AND whose cited guideline chunk supports the code.
2. Add evidence_quote_coverage = fraction of surfaced suggestions that carry a non-empty
   evidence quote (target 100%, manual §6.1).
3. Surface both in run_eval.py output and add them to evals/baseline.json with a floor
   (start advisory, not blocking, until the 100-set lands).
Add unit tests in tests/ for the new metric math. Keep CI green.
```
**Done‑when:** eval report shows citation accuracy + evidence‑quote coverage; metric is tested (manual §6.1).

---

### P‑B3 · Confidence‑floor tuning sweep  **[DS‑MAX]**
**Backing:** §1.3 ("0.70 floor is a placeholder until the golden set tunes it"), §2.2 Sprint B ("tune `BUDDI_HCC_CONFIDENCE_FLOOR`"), §4.4 ("never change a clinical prompt path on vibes").
**Targets:** new `scripts/tune_confidence_floor.py`, `docs/RETRO/confidence_tuning.md`, `core/agent.py` (value only).

```
Context: BUDDI_HCC_CONFIDENCE_FLOOR defaults to 0.70 (placeholder) in core/agent.py. The
judge second pass runs on the uncertain band [floor, 0.85). Once the 100-case golden set
exists we must tune the floor empirically, behind the eval gate.

Do:
1. Write scripts/tune_confidence_floor.py that runs the full eval at floor ∈
   {0.60,0.65,0.70,0.75,0.80}, produces a precision/recall/F1 + abstain-rate table and a
   simple plot, and recommends the F1-maximizing floor on the labeled set.
2. Write results + the chosen value to docs/RETRO/confidence_tuning.md (decision record).
3. Do NOT hardcode a new floor yet — only change the default once real labels exist and the
   LLM-on eval is green. Leave a clearly marked one-line change site.
This script must not require PHI or live PHI keys; it runs on the golden set only.
```
**Done‑when:** a reproducible sweep + written decision record exists; floor change is gated on the labeled set (manual §4.4).

---

### P‑B4 · Turn on the LLM‑on eval gate in CI  **[DS‑MAX]**
**Backing:** §2.2 Sprint B gate ("Eval gate green with real LLM + labeled set"), §4.3 (CI discipline), §4.4 (judge on a different model family; record both model IDs).
**Targets:** `.github/workflows/main.yml`, `evals/run_eval.py`, secrets config docs.

```
Context: CI currently runs the eval regression gate deterministically. Per manual §2.2/§4.4
we need an LLM-on eval that runs against the labeled set with the real suggester + an
independent-family judge, gated so it fails on >5% precision/recall drop vs
evals/baseline.json.

Do:
1. Add an opt-in CI job (e.g., workflow_dispatch + nightly, NOT every PR to control spend)
   that runs run_eval.py with real LLM keys from GitHub Secrets, records BOTH model IDs
   (suggester + judge) in the run artifact (manual §4.4 judge independence), and enforces the
   5% regression tolerance.
2. Keep the existing deterministic eval on every PR unchanged.
3. Document required secrets and the "never change a clinical prompt path without a green
   LLM-on run" rule in evals/README.md.
Do not put keys in the repo. Keep the deterministic PR gate intact.
```
**Done‑when:** nightly/dispatch LLM‑on eval passes on the labeled set with both model IDs recorded (manual §2.2 Sprint B, §4.4).

---

### P‑B5 · SMART‑on‑FHIR end‑to‑end against the SMART Health IT sandbox  **[DS‑MAX]**
**Backing:** §2.2 Sprint B (CTO), §1.3 ("SMART‑on‑FHIR connector in sandbox validation"), Risk #9 (sanctioned sandboxes only), Appendix A (`smart_fhir.py`).
**Targets:** `backend/smart_fhir.py`, `backend/fhir_client.py`, `tests/test_smart_fhir.py`, `.env.example`.

```
Context: buddee-health-hippocrates @ d016d93. backend/smart_fhir.py has launch+callback code
that has never run against a live sandbox (manual §1.3 says say only "in sandbox
validation"). Validate it against https://launch.smarthealthit.org WITHOUT touching any real
EHR or PHI.

Do:
1. Complete/verify the OAuth2 (PKCE) launch → callback flow end-to-end against the SMART
   Health IT public sandbox; add token refresh if missing.
2. Enforce ALLOWED_FHIR_HOSTS allow-listing on every outbound FHIR call (reject non-listed
   hosts); default to sandbox host only.
3. Store EHR access/refresh tokens encrypted at rest (reuse core/secure_fields.py).
4. Pull a sandbox bundle → run it through /ingest/fhir → confirm suggestions, with
   BUDDI_BAA_CONFIRMED gating respected (sandbox = synthetic, still fail-closed on real PHI).
5. Add integration tests (mock the sandbox HTTP) covering PKCE, refresh, and host allow-list
   rejection.
Report the manual sandbox steps you can't automate. Do not claim Epic/Cerner connectivity.
```
**Done‑when:** a sandbox launch pulls a bundle → suggestions; host allow‑list + refresh tested (manual §2.2 Sprint B; keeps the honest claim at §1.3).

---

### P‑B6 · Webhook retry / backoff + dead‑letter  **[DS‑1M]**
**Backing:** §2.1 visible debt ("webhook retry/backoff missing"), §2.2 Sprint B (CTO), Appendix A (`webhooks.py` HMAC).
**Targets:** `core/webhooks.py`, `backend/api.py`, `tests/test_webhooks.py`.

```
Context: core/webhooks.py sends HMAC-signed deliveries but has no retry/backoff or
dead-letter (manual §2.1 visible debt). Add resilience without changing the signature scheme.

Do:
1. Add exponential backoff with jitter (max 3 attempts) on delivery failure.
2. Add a dead-letter record for deliveries that exhaust retries, queryable by tenant.
3. Ensure the full event catalog fires: prior_auth.state_changed, hcc_suggestion.created,
   hcc_suggestion.approved, audit_event.flagged.
4. Keep HMAC signing + timestamp anti-replay intact; add tests for retry, DLQ, and signature.
Keep CI green.
```
**Done‑when:** retries/DLQ tested; full event catalog fires (manual §2.1).

---

### P‑B7 · Stripe products/prices wiring + checkout smoke  **[DS‑1M]**
**Backing:** §2.4 (pricing model), §2.1 visible debt ("Stripe unconfigured; requires §11 entity + bank"), §11.5 (Stripe gets a legal owner in Sprint B), Appendix A (`billing.py`).
**Targets:** `backend/billing.py`, `.env.example`, new `scripts/stripe_smoke.py`, `docs/cookbook.md`.

```
Context: backend/billing.py has Checkout/Portal/webhook code but no configured Products or
Prices. Per manual §2.4 the model is: $250–400/physician/month floor OR 15–20% gain-share on
validated+submitted recovery, whichever is greater, with credits accruing when Buddee-flagged
unsupported codes are retracted pre-submission (integrity priced both directions). Stripe
config itself waits on the §11 bank account — build the code + a test-mode smoke now.

Do:
1. Parameterize price IDs via env (STRIPE_PRICE_ID_MONTHLY, STRIPE_PRICE_ID_GAIN_SHARE) and
   document them in .env.example.
2. Write scripts/stripe_smoke.py that, in Stripe TEST mode, creates customer → checkout →
   simulates the webhook → asserts tenant provisioning. No live keys committed.
3. Add a metered/usage stub aligned to §2.4 (floor + gain-share + retraction credit) with a
   clear # requires-bank marker where live config plugs in.
Do not hardcode prices. Do not enable live mode.
```
**Done‑when:** Stripe test‑mode smoke passes end‑to‑end; live config is a one‑step plug after the bank exists (manual §2.4, §11.5).

---

### P‑B8 · Security‑questionnaire technical spine (CAIQ‑Lite)  **[DS‑1M]**
**Backing:** §2.2 Sprint B ("pre‑build the security‑questionnaire response (CAIQ‑Lite + addendum)"), §3.4 (security review is the pivotal sales step), §4.4 (HIPAA readiness).
**Targets:** new `docs/COMPLIANCE/security_questionnaire.md`, existing `docs/security_whitepaper.md`.

```
Context: The security review is the single most important sales step (manual §3.4). Draft the
TECHNICAL answers only for a CAIQ-Lite + healthcare addendum, grounded in what the code
actually does at d016d93 — do NOT overclaim (manual §1.3: no "HIPAA-compliant"/"SOC 2";
say "HIPAA-aligned posture").

Do:
1. From core/phi_guard.py, core/db_session.py (RLS), core/safety.py (redaction),
   core/ledger.py + core/merkle.py (audit chain), backend/auth.py, and docs/security_
   whitepaper.md, draft factual answers for: encryption at rest/in transit, RLS tenant
   isolation, PHI redaction, audit logging + tamper-evidence, secrets management, access
   control, sub-processors (Anthropic/OpenAI/GCP, BAA status "in process"), incident response.
2. Explicitly mark every item that is "posture/aligned" vs "certified" — no certification
   claims. Flag CEO/CFO-owned rows (insurance, policies, formation).
Output docs/COMPLIANCE/security_questionnaire.md.
```
**Done‑when:** a claims‑safe technical CAIQ‑Lite draft exists so the security‑review step "costs days, not weeks" (manual §3.4).

---

### P‑B9 · Open‑source readiness dry‑run (decision aid)  **[DS‑MAX]**
**Backing:** §2.1 "Decision item — the open‑source question" (decide in Sprint B, both founders, one page), §9.1 (audit‑chain core as sales asset).
**Targets:** new `docs/OPEN_SOURCE_ASSESSMENT.md`, repo audit only (no license change without both‑founder sign‑off, §5.2).

```
Context: The July 18–20 history reset was done "before open-sourcing repo." Per manual §2.1
we must DECIDE deliberately in Sprint B, both founders, one page of rationale — not drift in.
This prompt only produces the decision aid; it changes no license.

Do:
1. Inventory what would be PUBLIC (audit-chain core: ledger.py, merkle.py, phi_guard.py,
   safety gates) vs MUST STAY PRIVATE (prospect lists, growth/ templates, eval golden labels,
   any secrets/prompts that are moat).
2. Produce a one-page assessment: license options (AGPL vs BSL vs permissive) with the
   trade-off for "verify our chain math yourself" as a sales asset, and a proposed repo split.
3. Run a secrets/PII scan (gitleaks is already in CI) and list anything that would block a
   public push.
Output docs/OPEN_SOURCE_ASSESSMENT.md. Do NOT add a LICENSE or change visibility — that is a
both-founder decision (§5.2).
```
**Done‑when:** one‑page written assessment exists for the founders' decision (manual §2.1).

---

## 4. Sprint C — "Provision & Pilot" (Sep 1 – Oct 17)

**Manual pilot‑ready gate (§2.2):** *"The design partner POSTs a real de‑identified bundle and sees suggestions in <30s p95 with a verifying audit chain and a signed daily root in Object Lock."* **Provision the GCP PHI tier only after BAAs land** (manual §2.2, §4.1, §7.1).

---

### P‑C1 · Parameterize + template the GCP PHI‑tier IaC  **[DS‑MAX]**
**Backing:** §2.2 Sprint C (CTO), §4.1 Tier 2, Appendix A (`infra/cloud-run-*.yaml`).
**Targets:** `infra/cloud-run-api.yaml`, `infra/cloud-run-worker.yaml`, new `infra/provision_gcp.sh` (or Terraform), `docs/CLOUD_DEPLOYMENT_GUIDE.md`.

```
Context: buddee-health-hippocrates @ d016d93. infra/cloud-run-api.yaml and
cloud-run-worker.yaml are ready but full of placeholders (PROJECT_ID, REGION, IMAGE_TAG, VPC
connector buddi-vpc, service accounts buddi-api@/buddi-worker@, Secret Manager
buddi-api-secrets). Per manual §4.1 Tier 2 we must provision only AFTER BAAs land; build the
provisioning now so it's one command when counsel clears it.

Do:
1. Externalize all placeholders into a single infra/env.tier2.example (documented) and make
   the yamls render from it.
2. Write infra/provision_gcp.sh (idempotent gcloud, or Terraform if cleaner) that creates:
   Cloud SQL Postgres 16 (CMEK + private IP + PITR), Cloud KMS signing key for the Merkle
   root, GCS bucket in Object Lock COMPLIANCE mode, Secret Manager entries, Memorystore Redis
   (for the rate limiter + jobs), VPC connector, and the two service accounts with least-priv
   IAM.
3. Add a --dry-run/plan mode and a teardown for non-prod.
Do NOT run it. Do NOT set BUDDI_BAA_CONFIRMED=1. Output the file diffs + the exact
provisioning command and the manual "BAAs must be signed first" checklist gate.
```
**Done‑when:** one idempotent command provisions the full Tier 2 stack; gated behind BAA sign‑off (manual §2.2, §7.1).

---

### P‑C2 · Wire Merkle signing to Cloud KMS + Object Lock export  **[DS‑MAX]**
**Backing:** §1.2 Output 3, §1.3 ("Signed, append‑only Merkle root 80% — awaiting cloud KMS key + Object Lock bucket"), §4.1 ("highest‑leverage delta").
**Targets:** `core/merkle.py`, `core/ledger.py`, env `BUDDI_AUDIT_KMS_PROVIDER`, `BUDDI_AUDIT_ROOTS_BUCKET`, `tests/test_audit_merkle.py`.

```
Context: core/merkle.py is code-complete with an Ed25519/HMAC fallback and offline
verification; it awaits a real Cloud KMS key (BUDDI_AUDIT_KMS_PROVIDER) and an Object Lock
bucket (BUDDI_AUDIT_ROOTS_BUCKET). This is the manual's "highest-leverage delta for the third
consecutive edition" (§4.1). Wire the real providers behind the existing interface.

Do:
1. Verify the KMS provider path signs the daily Merkle root with the provisioned Cloud KMS
   key and that GET /api/audit/verify returns 100% against a KMS-signed root.
2. Verify the signed root exports to the Object Lock (COMPLIANCE mode / WORM) bucket and that
   offline verification still passes.
3. Add an integration test (KMS + GCS mocked/emulated) asserting: sign → export → verify
   online → verify offline, all 100%.
Do not change the chain/hash logic. This is provider wiring + verification only.
```
**Done‑when:** daily root is KMS‑signed, WORM‑exported, verifies online + offline at 100% (moves manual §1.3 claim from 80% → shippable).

---

### P‑C3 · Provision Memorystore Redis + verify multi‑instance rate limiting/jobs  **[DS‑1M]**
**Backing:** §4.2 Bottleneck #1 (Redis on Memorystore in Sprint C), §2.1 visible debt.
**Targets:** `backend/middleware.py` (verify), `core/jobs.py`/`core/worker.py`, `infra/`, `tests/test_rate_limit.py`.

```
Context: The rate limiter (backend/middleware.py, RateLimitMiddleware) is ALREADY slowapi +
Redis via REDIS_URL (manual §4.2 lists it "OPEN" but the code is done — the gap is
provisioning + multi-instance verification). Wire it to the provisioned Memorystore instance
and prove it holds across 2+ instances.

Do:
1. Point REDIS_URL at Memorystore in the Tier 2 config; confirm fail-open behavior on Redis
   outage is intentional and documented.
2. Add a test/harness that simulates two API instances sharing Redis and asserts limits are
   enforced GLOBALLY (not N×), closing bottleneck #1.
3. Confirm the async job queue/worker behavior under the shared Redis + Cloud SQL setup.
Report results; keep CI green.
```
**Done‑when:** rate limits enforced globally across instances; bottleneck #1 closed (manual §4.2).

---

### P‑C4 · SLO dashboard‑as‑code + PagerDuty alerting  **[DS‑1M]**
**Backing:** §2.2 Sprint C ("SLO dashboard (p95<30s, verify=100%, error<0.5%) + PagerDuty"), §6.1 (safety/integrity signals), Appendix A (`/api/slo`).
**Targets:** `/api/slo` (verify), new `infra/monitoring/` (dashboard + alert policy JSON), `docs/runbooks/`.

```
Context: /api/slo exists and the frontend SLOPanel consumes it. Per manual §2.2 Sprint C +
§6.1 we need a production SLO dashboard and paging.

Do:
1. Define, as code (GCP Monitoring dashboard + alert policy JSON under infra/monitoring/),
   the SLOs: /api/shadow/audit p95 < 30s, prior-auth p95 < 10s, error rate < 0.5%,
   audit-chain verify = 100% (a single partially_verified is Sev-1 per §2.3), LLM 429/error
   < 1%.
2. Wire PagerDuty policies: audit-chain lag/verify<100% = P1 (integrity); error>2%/5min = P2;
   LLM 5xx>10%/10min = P3; grounding failure>5% = P2.
3. Add a docs/runbooks/ entry per alert (what it means, first response).
Output the dashboard/alert JSON + runbook stubs. Don't require live GCP to lint the JSON.
```
**Done‑when:** dashboard + alerts deploy from code; integrity breach pages P1 (manual §2.2 Sprint C, §6.1).

---

### P‑C5 · End‑to‑end pilot‑readiness rehearsal (de‑identified)  **[DS‑MAX]**
**Backing:** §2.2 Sprint C pilot‑ready gate, §3.4 (pilot funnel), §6.1 (North Star instrumentation).
**Targets:** `scripts/provision_tenant.py`, `scripts/verify_system.py`, `docs/runbooks/pilot_kickoff.md`.

```
Context: Pilot-ready gate (manual §2.2): a design partner POSTs a real DE-IDENTIFIED bundle
and sees suggestions in <30s p95 with a verifying audit chain and a signed daily root in
Object Lock. Rehearse this against the Tier 2 stack using SYNTHETIC/de-identified bundles
only. BUDDI_BAA_CONFIRMED flips per-tenant ONLY on counsel sign-off — do not flip it here.

Do:
1. Test scripts/provision_tenant.py end-to-end on Tier 2: create tenant, issue key, load the
   V28 guideline pack, verify RLS isolation from a second tenant.
2. Run a de-identified bundle through /ingest/fhir → suggestions, measuring p95 latency and
   confirming GET /api/audit/verify = 100% and a signed root landed in Object Lock.
3. Write docs/runbooks/pilot_kickoff.md: the exact go-live checklist incl. the counsel-gated
   baa_confirmed flip, weekly clinician-review cadence, and the North Star (Approved Recovered
   Revenue per Tenant per Month) instrumentation (manual §6.1).
Report the measured p95 and verify rate.
```
**Done‑when:** the full pilot path passes on synthetic data at <30s p95 with 100% verify; kickoff runbook exists (manual §2.2 Sprint C).

---

## 5. Cross‑cutting hardening (interleave across sprints)

These come from manual §4.3/§4.4 "remaining discipline items" and Risk register — low‑risk, high‑trust, run between the above.

### P‑X1 · Trivy image scanning in CI  **[DS‑1M]**
**Backing:** §4.3 ("wire Trivy image scanning into the pipeline").
```
Add a Trivy container image scan job to .github/workflows/main.yml after the Docker build
step (pip-audit + gitleaks already cover deps/secrets per manual §4.3). Fail on HIGH/CRITICAL
with an allow-list file for accepted findings. Keep the existing jobs unchanged.
```

### P‑X2 · mypy advisory → enforced burn‑down  **[DS‑1M]**
**Backing:** §4.3 ("keep mypy advisory→enforced on a burn‑down").
```
mypy runs advisory in CI. Produce a burn-down: run mypy across backend/ + core/, bucket
errors by module, fix the cheapest tranche, and flip the LOWEST-error modules to enforced in
main.yml while leaving the rest advisory. Do not change runtime behavior. Report the counts.
```

### P‑X3 · Operator‑UI MFA for the hosted tier  **[DS‑MAX]**
**Backing:** §4.4 ("MFA on the operator UI when it becomes hosted"), §7.1.
```
When the operator UI is hosted (post-demo), add MFA to the login flow (the API-key/auth flow
already exists in frontend/). Implement TOTP-based MFA behind a feature flag, off for the
public synthetic demo (no PHI) and required for any PHI tenant. Add tests. Do not weaken the
existing auth or the BAA tripwire.
```

### P‑X4 · Conversational memory session store (the real `TODO(human)`)  **[DS‑MAX]**
**Backing:** `core/memory.py:5` `# TODO(human)` (multi‑turn clinical memory is volatile/per‑request); supports the ChatPage surface.
```
core/memory.py has the only real # TODO(human): memory is volatile + per-request, unsafe for
multi-turn clinical context. Design a tenant-scoped, RLS-safe, PHI-redacted session store
(Redis/Memorystore) for multi-turn context with a strict TTL and no PHI in logs. Gate it
behind the BAA tripwire. Add tests. Only build if multi-turn is on the pilot's critical path;
otherwise output the design and stop.
```

---

## 6. Sequencing & dependencies

```
SPRINT A (48h → Aug 2)        SPRINT B (Aug 3–30)              SPRINT C (Sep 1–Oct 17)
─────────────────────         ────────────────────             ───────────────────────
P-A1 Publish demo ─┐          P-B1 Golden labeling ─┐          P-C1 GCP IaC ─┐
P-A2 Demo safety   ├─(gates)─▶ P-B2 Citation metric  │           (needs BAAs) │
P-A3 Video harness ┘          P-B3 Floor sweep ──────┼─(gate)─▶ P-C2 KMS/WORM │
                              P-B4 LLM-on eval gate ─┘           P-C3 Redis    ├─▶ P-C5
                              P-B5 SMART sandbox                  P-C4 SLO/page │   Pilot
                              P-B6 Webhook retry                                ┘   rehearsal
                              P-B7 Stripe (needs bank)
                              P-B8 CAIQ-Lite spine
                              P-B9 OSS assessment
Cross-cutting: P-X1 Trivy, P-X2 mypy, P-X3 MFA, P-X4 memory — interleave.
```

**Hard gates from the manual (do not reorder):**
- Demo URL gates YC + outbound + angels → **ship P‑A1 first** (§2.2 Sequencing Rule).
- Eval floor tuning (P‑B3) is gated on the labeled set (P‑B1) and must precede any clinical‑prompt change (§4.4).
- **GCP PHI tier (P‑C1/C2) provisions only after BAAs land, which require the entity (§11).** These are CEO/CFO gates, not CTO — do not provision early (§7.1).
- `tenants.baa_confirmed` flips per‑tenant **only on counsel sign‑off** (§2.2 Sprint C, §7.1).

---

## 7. What is deliberately NOT in this plan

Per manual §2.2 ("no new feature surface until v1.0 is closed") and the "Deferred" list:

- **Deferred until a pilot blocks on it:** Pub/Sub streaming, payer integrations, model fine‑tuning, SOC 2 Type I window.
- **CEO/CFO‑owned, no code:** incorporation (§11), BAA filings, MD‑advisor agreement, founder memo/equity (§5.3), SAFE, design‑partner LOI/DPA, CRM/funnel, insurance.
- **Already shipped — verify, don't rebuild:** CI/CD, Redis rate limiter, SSE, operator‑UI auth/error states, audit‑chain concurrency + RLS GUC survival, growth pipeline + claims linter (§2.1, Figure 0).

---

> **Re‑read before executing any prompt:** manual §1.3 (Reality Check), §4.4 (LLM/compliance), §7.1 (Existential Risks), §8.2 (the enforcement line). The BAA flag stays at `0` until counsel says otherwise. Nothing auto‑submits. The demo URL ships before anything else in this book.
>
> This is a forecast, not a promise — update it in the Friday retro. Prompts target the codebase at `d016d93`; re‑diff before running if the baseline has moved.
