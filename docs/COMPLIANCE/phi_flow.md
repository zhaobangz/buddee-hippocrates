# PHI Flow Diagram

**Owner:** Founder (Zhao) + Lead Engineer (Hire #2 when onboarded)
**Last reviewed:** *fill in at every retrospective*

This document is the canonical "where does PHI enter / live / leave"
diagram referenced by `Buddi_Strategic_Founders_Operating_Manual.pdf`
§7.2 Risk #1 mitigation step #6. It is the artifact compliance
counsel will ask for during a HIPAA security risk assessment.

## Data-flow diagram (current state, May 2026)

```
                         ┌─────────────────────┐
                         │ Customer EHR        │
                         │ (Epic / Cerner /    │
                         │  athenahealth)      │
                         └──────────┬──────────┘
                                    │ HTTPS (TLS 1.3)
                                    │ FHIR R4 Bundle
                                    ▼
                       ┌──────────────────────────┐
                       │ Cloud Load Balancer      │
                       │ + Cloud Armor (WAF)      │
                       └──────────┬───────────────┘
                                  │
                                  ▼
                ┌─────────────────────────────────────┐
                │ Cloud Run: buddi-api                │
                │   1. require_api_client (auth)      │
                │   2. tenant_scoped_session (RLS)    │
                │   3. _enforce_baa_precondition      │   ← §7.2 #1
                │   4. FHIRBundle validation          │
                │   5. FHIRAdapter.extract_from_bundle│
                │   6. core/agent.py:handle()         │
                │      • core/llm_manager._baa_guard  │   ← §7.2 #1
                │      • core/agent._apply_safety_floor│  ← §7.2 #2
                │   7. log_audit_event_postgres       │
                └──────┬──────────────┬───────────────┘
                       │              │
              (prompts)│              │ (RAG retrieval)
                       ▼              ▼
       ┌────────────────────┐   ┌────────────────────────┐
       │ Anthropic API      │   │ Cloud SQL: Postgres 16 │
       │ (Claude Opus 4.6)  │   │   • pgvector embeddings│
       │ TLS 1.3 + BAA      │   │   • RLS policies       │
       └────────────────────┘   │   • CMEK encryption    │
                                │   • Private IP only    │
                                └────────────┬───────────┘
                                             │
                                             ▼
                                ┌────────────────────────┐
                                │ GCS Object Lock bucket │
                                │ + KMS-signed Merkle    │
                                │   root, daily          │
                                └────────────────────────┘
```

## PHI lifecycle, per row

| Stage                  | Where PHI lives                                 | Encryption / protection                                | Module                                               | Notes                                              |
| ---------------------- | ----------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------- | -------------------------------------------------- |
| In transit (ingress)   | HTTPS request body                              | TLS 1.3                                                | `backend/api.py:/ingest/fhir`                        | Bundle size capped at `MAX_FHIR_BUNDLE_BYTES` (2 MB default). |
| Parsing                | In-memory Python objects                        | None (in-memory)                                       | `core/schemas.py:FHIRBundle`                         | Schema-validated before any further processing.   |
| Agent prompt           | Outbound HTTPS to Anthropic                     | TLS 1.3 + BAA                                          | `core/llm_manager.py:_anthropic_chat`                | Note wrapped in a `<clinical_note>` delimiter; `_baa_guard` refuses oversized / delimited prompts unless `BUDDI_BAA_CONFIRMED=1`. |
| At rest, clinical_notes| Postgres column `clinical_notes.note_text`      | Cloud SQL CMEK + private IP                            | `core/models.py:ClinicalNote`                        | RLS-scoped per tenant.                             |
| At rest, encrypted cols| `patients.demographics_encrypted`, `ehr_integrations.auth_credentials_encrypted` (BYTEA) | App-layer envelope encryption (PBKDF2+Fernet) via `BUDDI_STORAGE_KEY`, on top of Cloud SQL CMEK | `core/storage.py:SecureStorage` | Defense-in-depth: ciphertext is useless without the storage key even on a DB compromise. |
| At rest, embeddings    | `document_chunks.embedding` (Vector(1536))      | Cloud SQL CMEK + private IP                            | `core/models.py:DocumentChunk`                       | Embeddings of non-PHI guideline text only.         |
| Audit trail            | `audit_events.payload` (JSONB)                  | Cloud SQL CMEK + KMS-signed daily Merkle root          | `core/safety.py`, `core/merkle.py`                   | Append-only via signed root; mutable row in DB.    |
| Logs                   | Cloud Logging                                   | TLS in transit, encrypted at rest by GCP               | `core/safety.py:redact_for_logs`                     | PII redacted before log line is emitted.           |
| Traces                 | Cloud Trace                                     | TLS in transit                                         | `core/agent.py` span attributes                      | Only hashes and byte counts attached to spans.     |

## What does *not* contain PHI

* OpenAI embedding requests (`core/rag_engine.py`) — only public CMS
  guideline text is currently embedded. The eventual move to embed
  customer clinical notes is gated on a separate safety review.
* Marketing waitlist data — separate database, separate FastAPI
  process, separate tenant boundary.
* The Synthea synthetic bundles served from `/api/demo/synthea` —
  Safe-Harbor compliant, no real PHI.

## Egress points

1. **Anthropic (primary LLM)** — every clinical prompt. BAA-gated.
2. **OpenAI (embeddings only)** — public guideline text only. PHI
   guard via `core/llm_manager.py:_baa_guard` is *not* applied here
   because no PHI is sent.
3. **GCS Object Lock bucket** — signed daily Merkle root and event
   hashes; contents are HMAC / Ed25519 signatures, not PHI payloads.
4. **Cloud Logging / Cloud Trace** — only redacted strings and hashed
   identifiers; raw PHI is rejected at the redaction boundary.
5. **Customer webhook endpoints** (`core/webhooks.py`, build-out B2) —
   customer-controlled URLs registered per tenant. Payloads are
   HMAC-SHA256-signed and carry event metadata only (suggestion code,
   prior-auth id, status, audit hash) — **never** the clinical note,
   demographics, or other PHI. The customer's endpoint is within their own
   tenant boundary, so this is not a third-party disclosure.

No PHI leaves the tenant boundary except to the LLM provider (under BAA) and
the customer's own webhook endpoint (customer-controlled, PHI-free payloads).

## Production wiring TODOs

- [x] KMS-backed signing implemented in `core/merkle.py`
      (`MerkleSigner._gcp_kms_signer` / `_aws_kms_signer`), selected via
      `BUDDI_AUDIT_KMS_PROVIDER` + `BUDDI_AUDIT_KMS_KEY`. Verification is
      offline against the public key embedded in each envelope.
- [x] Object Lock (WORM) mirror implemented (`export_daily_root` →
      `BUDDI_AUDIT_ROOTS_BUCKET`, `s3://` / `gs://`) with COMPLIANCE-mode
      retention.
- [ ] Provision the Cloud KMS signing key and set `BUDDI_AUDIT_KMS_*`.
      Note: Cloud KMS asymmetric signing does **not** offer Ed25519 — use
      **EC P-256 (ECDSA-SHA256)** for the KMS key (Ed25519 remains available
      via the self-managed `BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH` path). Record
      the resulting `key_id` in `docs/COMPLIANCE/baa_status.md`.
- [ ] Provision the Object Lock bucket (retention policy via IaC) and set
      `BUDDI_AUDIT_ROOTS_BUCKET`.
- [ ] Publish the public half of the signing key in this directory
      (`merkle_public_key.pem`) so external auditors can verify without
      contacting Buddi.
- [ ] Add a Cloud Logging exclusion filter that drops any log line
      that pattern-matches the `core/safety.py:PII_PATTERNS` set, as a
      belt-and-braces measure against accidental PHI leakage.
- [ ] Document the Cloud SQL CMEK key ID once provisioned.
