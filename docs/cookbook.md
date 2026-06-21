# Buddee API Cookbook

Complete, copy-paste-runnable recipes for every core Buddee flow. Every example
uses **synthetic** data (Marcus Holloway / Synthea fixtures) — never real PHI.

## Prerequisites

- Your API key (from your Buddee account or the provisioning script).
- Base URL: `https://api.buddi.health` (production) or `http://localhost:8001`
  (local dev). Set both as shell variables:

```bash
export BUDDI_URL="http://localhost:8001"
export BUDDI_KEY="your-api-key-here"
```

Authentication is via the `X-API-Key` header (or `Authorization: Bearer <key>`).
Scopes: `clinician` (analysis), `ingest` (FHIR ingest), `admin` (billing, audit
verify, webhooks, metrics).

---

## Recipe 1: Ingest a clinical note and poll for HCC suggestions

The shadow-audit endpoint is **asynchronous** by default: it enqueues a job and
returns `202` immediately so your request never blocks on the LLM call.

**Step 1 — submit the audit (returns a job):**

```bash
curl -sS -X POST "$BUDDI_URL/api/shadow/audit" \
  -H "X-API-Key: $BUDDI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "MH-SYNTHETIC-001",
    "note": "65-year-old male with longstanding Type 2 diabetes mellitus with peripheral neuropathy, CKD stage 3b, and hypertension. A1c 8.4%.",
    "billed_codes": ["E11.9", "I10"]
  }'
```

```json
{ "job_id": "8f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f", "status": "pending", "poll_url": "/api/jobs/8f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f" }
```

**Step 2 — poll the job until `completed`:**

```bash
curl -sS "$BUDDI_URL/api/jobs/8f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f" \
  -H "X-API-Key: $BUDDI_KEY"
```

```json
{
  "job_id": "8f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f",
  "status": "completed",
  "result": {
    "identified_codes": [
      { "code": "E11.22", "description": "Type 2 diabetes mellitus with diabetic chronic kidney disease", "confidence": 0.93, "review_status": "human_review_required" }
    ],
    "recovered_revenue": 8400.0,
    "audit_hash": "sha256:…",
    "intent_detected": "shadow_mode_rcm"
  }
}
```

**Step 3 — review.** Every suggestion is `human_review_required`. Nothing is
submitted to a payer or EHR. Approve a suggestion explicitly via
`POST /api/suggestions/{id}/approve`.

> **Tip:** for a synchronous response (no polling), append `?sync=true`. This is
> intended for tests and low-latency callers; production should use the async
> path to stay under the 30s p95 SLO.

---

## Recipe 2: Generate a prior-authorization draft

```bash
curl -sS -X POST "$BUDDI_URL/api/prior-auth/generate" \
  -H "X-API-Key: $BUDDI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "procedure_code": "70553",
    "payer": "Medicare",
    "clinical_context": "Progressive headaches with focal neurologic findings; MRI brain w/ and w/o contrast requested.",
    "demo": true
  }'
```

```json
{
  "draft_id": "…",
  "auth_request_id": "…",
  "draft_letter": "…",
  "supporting_codes": ["G44.1"],
  "payer_rationale": "…",
  "status": "draft",
  "audit_hash": "sha256:…"
}
```

The draft is always `status: "draft"`. Buddee never auto-submits to a payer.

---

## Recipe 3: Verify your audit chain

Every analysis is written to a SHA-256 hash-chained, append-only audit log, with
a daily KMS-signed Merkle root. Verify it any time:

```bash
curl -sS "$BUDDI_URL/api/audit/verify" \
  -H "X-API-Key: $BUDDI_KEY"
```

```json
{ "all_verified": true, "event_count": 42, "chain_root": "sha256:9f2c…", "chain": { "verified": true }, "roots": { "verified": true, "checked_days": 7 } }
```

Field reference:

| Field | Meaning |
|---|---|
| `all_verified` / `verified` | `true` only if both the in-DB hash chain **and** every signed daily Merkle root verify. |
| `event_count` / `events_checked` | Number of audit events walked. |
| `chain` | Result of the in-DB hash-chain walk. |
| `roots` | Result of recomputing each signed daily Merkle root from the live DB. |

Scope a re-walk to one day (partition-pruned, fast): `?day=2026-06-01`.
Force a full chain re-walk: `?deep=true`. Requires the `admin` scope.

---

## Recipe 4: Register a webhook

Buddee POSTs HMAC-signed events to your endpoint. Supported events:
`hcc_suggestion.created`, `hcc_suggestion.approved`, `prior_auth_state.changed`,
`audit_event.flagged`. Requires the `admin` scope.

```bash
curl -sS -X POST "$BUDDI_URL/api/webhooks" \
  -H "X-API-Key: $BUDDI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.example.com/buddi/webhook",
    "events": ["hcc_suggestion.created", "hcc_suggestion.approved"],
    "secret": "whsec_your_shared_secret_min16"
  }'
```

**Verifying the signature.** Each delivery carries `X-Buddi-Event` and
`X-Buddi-Signature: sha256=<hex>`. Recompute and compare:

```python
import hashlib, hmac
expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
# constant-time compare against the X-Buddi-Signature header
```

The signing secret is stored encrypted at rest; Buddee never returns it after
creation. Keep your copy to verify signatures.

---

## Recipe 5: Use the demo sandbox (no PHI required)

List the synthetic Synthea bundles, then ingest one — no real patient data:

```bash
curl -sS "$BUDDI_URL/api/demo/synthea" -H "X-API-Key: $BUDDI_KEY"
```

```json
{ "bundles": [ { "name": "bundle_001_diabetic_ckd.json", "fetch_url": "/api/demo/synthea/bundle_001_diabetic_ckd.json" } ], "count": 25, "synthetic": true }
```

```bash
curl -sS -X POST "$BUDDI_URL/api/demo/synthea/bundle_001_diabetic_ckd.json/ingest" \
  -H "X-API-Key: $BUDDI_KEY"
```

```json
{ "status": "success", "bundle_name": "bundle_001_diabetic_ckd.json", "synthetic": true, "response": { "identified_codes": [ … ] }, "audit_hash": "sha256:…" }
```

The committed 5-fixture demo set (one per condition) is also served, clinician-
scoped, at `GET /api/demo/bundles` and `GET /api/demo/bundles/{name}`.

---

## Recipe 6: Check SLO health

PHI-safe operational metrics for the operator dashboard (admin scope):

```bash
curl -sS "$BUDDI_URL/api/metrics/slo" -H "X-API-Key: $BUDDI_KEY"
```

```json
{
  "shadow_audit_p95_ms": 14200,
  "prior_auth_p95_ms": 5100,
  "audit_chain_verify_ok": true,
  "audit_chain_last_verified_at": "2026-06-18T02:00:00+00:00",
  "suggestions_approved_7d": 128,
  "suggestions_rejected_7d": 12,
  "suggestions_abstained_7d": 31,
  "suggestion_approval_rate_7d": 0.914,
  "encounters_processed_24h": 47,
  "generated_at": "2026-06-18T15:04:00+00:00",
  "tenant_id_hash": "a1b2c3d4e5f6a7b8"
}
```

All values are durations, counts, booleans, or a salted tenant fingerprint — no
patient identifiers. Latency fields are `null` when there is no data in the
window.

---

## Error reference

| Status | Meaning | Common cause |
|---|---|---|
| 400 | Bad request | Malformed JSON, invalid `day` format, bad webhook signature. |
| 401 | Missing or invalid API key | No `X-API-Key` / `Authorization` header, or unknown key. |
| 403 | Insufficient scope | Key lacks the required scope (`clinician` / `ingest` / `admin`). |
| 404 | Not found | Unknown job/suggestion/bundle, or no tenant. |
| 412 | BAA precondition not met | `/ingest/fhir` before `BUDDI_BAA_CONFIRMED=1` / tenant BAA flag. |
| 422 | Validation error | FHIR bundle fails schema, note too long, unknown webhook event. |
| 429 | Rate limit exceeded | Too many requests; back off and retry with jitter. |
| 503 | Unavailable | Dependency not configured (e.g. Stripe) or agent not bootstrapped. |

All errors return `{"detail": "<human-readable reason>"}`.

---

## SDK / Postman collection

A ready-to-import Postman collection lives at
[`docs/buddi.postman_collection.json`](./buddi.postman_collection.json). Import
it, set the `base_url` and `api_key` collection variables, and every request is
pre-authenticated. Interactive API docs: `/docs` (Swagger UI) and `/redoc`.
