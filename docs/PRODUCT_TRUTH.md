# Product Truth — What Buddi Actually Does Today

**Owner:** Founder (Zhao)
**Cadence:** Updated every Friday during retrospective. Manual §7.2 Risk #3.
**Last reviewed:** 2026-06-13

This is the brutal-honest counterweight to the marketing site. The
manual prescribes reading this document *at the start of every sales
call* so you do not accidentally over-claim. Anything that ought to be
on this list but is on the marketing site instead is a counsel risk.

## What Buddi delivers, end-to-end, today

* **Authenticated FastAPI backend** with per-tenant API keys and
  row-level security policies on every clinical table.
* **Shadow-mode HCC suggestion path** with a confidence floor (0.70),
  a mandatory evidence quote, and an **LLM-as-judge second pass** that
  independently re-checks every uncertain-band suggestion (confidence
  in `[floor, 0.85)`) against the chart before surfacing it. Anything
  that fails any gate — or that the judge will not affirm — is abstained
  (fail-closed) and recorded in the audit chain.
* **Hash-chained `audit_events` table** with a daily Merkle root
  signed by a configured Ed25519 key (HMAC fallback in dev).
* **FHIR R4 bundle ingest** with size-cap, schema validation, and a
  BAA precondition that refuses bundles for unconfirmed tenants.
* **OpenTelemetry tracing**, PII-redacted logging, and a verifiable
  audit log endpoint.
* **Hosted synthetic-FHIR sandbox** (25 Safe-Harbor bundles, no PHI).
* **Eval regression gate in CI** with precision / recall / abstain
  metrics computed against a 10-case clinician-labeled seed set.

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

## What is in flight (Weeks 1–4 sprint)

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
- [ ] OpenAI BAA filed and confirmed (founder action, week 1).
- [ ] Anthropic BAA filed and confirmed (founder action, week 1).
- [ ] Cloud KMS signing key (EC P-256) + Object Lock bucket provisioned and `BUDDI_AUDIT_KMS_*` / `BUDDI_AUDIT_ROOTS_BUCKET` set (code path ready; founder/infra action, week 1).
- [ ] Clinical advisor hired and named on the marketing site (week 2).
- [ ] Counsel review of TrustAnchor copy on `buddi-web` (week 3).
- [ ] First design-partner LOI signed (week 5 stretch).

## Numbers the team can defensibly cite today

* **Audit chain verification rate:** 100% in CI (`GET /api/audit/verify`).
* **Eval offline precision:** 1.0 on the seed set (10 cases). Note:
  this is a wiring test, not a real precision number — the LLM-on
  eval lands once the BAA is confirmed.
* **Eval offline recall:** 0.10 (only the diabetic-CKD case fires
  the demo pattern matcher). Clinician advisor's first deliverable
  is to grow this.
* **Synthetic bundle count:** 25 (generated by
  `evals/synthea/generate.py`).
* **Routes registered:** 31 (`/health`, `/api/*`, `/ingest/fhir`,
  `/api/demo/synthea/*`).

## Numbers the team must NOT cite today

* "94% confidence." This was a mock value in the marketing site.
  The agent's actual confidence distribution will be measured once
  the LLM-on eval is in place.
* "$82,000 / physician / year." This is a model output, not a
  measured pilot result. Cite it as "modeled" and link to the
  methodology PDF (TODO).
* "4.2% capture-rate lift." Industry-standard reference number;
  cite the source, never claim it as Buddi's measured number.

## Next update

Friday 2026-05-15 — append the week's deltas above the prior entry
and update the "Last reviewed" header.
