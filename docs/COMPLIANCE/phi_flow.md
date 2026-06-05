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
| In transit (ingress)   | HTTPS request body                              | TLS 1.3                                                | `backend/api.py:/ingest/fhir`                        | Bundle size capped at `MAX_FHIR_BUNDLE_BYTES`.     |
| Parsing                | In-memory Python objects                        | None (in-memory)                                       | `core/schemas.py:FHIRBundle`                         | Schema-validated before any further processing.   |
| Agent prompt           | Outbound HTTPS to Anthropic                     | TLS 1.3 + BAA                                          | `core/llm_manager.py:_anthropic_chat`                | Refused by `_baa_guard` unless `BUDDI_BAA_CONFIRMED=1`. |
| At rest, clinical_notes| Postgres column `clinical_notes.note_text`      | Cloud SQL CMEK + private IP                            | `core/models.py:ClinicalNote`                        | RLS-scoped per tenant.                             |
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

## Production wiring TODOs

- [ ] Replace the local `BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH` with a
      Cloud KMS-backed Ed25519 key. Update `docs/COMPLIANCE/baa_status.md`
      with the resulting `key_id`.
- [ ] Publish the public half of the Ed25519 signing key in this
      directory (`merkle_public_key.pem`) so external auditors can
      verify without contacting Buddi.
- [ ] Add a Cloud Logging exclusion filter that drops any log line
      that pattern-matches the `core/safety.py:PII_PATTERNS` set, as a
      belt-and-braces measure against accidental PHI leakage.
- [ ] Document the Cloud SQL CMEK key ID once provisioned.
