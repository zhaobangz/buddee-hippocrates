# Buddee Health — Security Whitepaper

**Audience:** compliance officers, hospital procurement, and security reviewers.
**Version:** 4.1.0 · **Contact:** security@buddi.health
**Scope:** the `buddee-health-hippocrates` clinical-AI backend (FastAPI + Postgres + pgvector).

Every claim below is traceable to source. File citations are given inline.

---

## 1. Executive summary

Buddee operates in **shadow mode**: it surfaces missed HCC/ICD-10 coding and
prior-authorization opportunities as *draft suggestions that always require human
approval*. Nothing is ever auto-submitted to a payer or EHR. Every analysis is
written to a SHA-256 hash-chained, append-only audit log whose daily root is
KMS-signed and mirrored to WORM (Object Lock) storage — an independently
verifiable record of exactly what was suggested, on what evidence, and who
approved it. This audit moat is the product's core trust guarantee and its
primary defense against False Claims Act exposure.

## 2. Data classification

| Class | Examples | Systems touched |
|---|---|---|
| **PHI** | Clinical notes, patient name/MRN/DOB/SSN, FHIR bundles | Postgres (`clinical_notes`, `patients`), the Anthropic LLM (under BAA) |
| **Tenant-confidential** | API keys, Stripe customer IDs, webhook secrets | Postgres (`tenant_api_keys`, `tenants`, `webhook_endpoints`) — all hashed or encrypted |
| **Operational (PHI-free)** | Durations, counts, audit hashes, SLO metrics | `audit_events`, `/api/metrics/slo`, Cloud Logging/Trace |
| **Public** | CMS guideline text, Synthea synthetic bundles | pgvector embeddings, `/api/demo/*` |

Only the PHI class crosses a trust boundary, and only to the LLM provider under
a signed BAA (§6). Embeddings (`core/rag_engine.py`) are computed over public
CMS guideline text only — never patient notes.

## 3. Encryption

- **In transit:** TLS 1.3 for all ingress (Cloud Load Balancer) and for egress
  to the LLM provider and customer webhooks.
- **At rest, infrastructure:** Cloud SQL and GCS use customer-managed encryption
  keys (CMEK).
- **At rest, application layer (defense in depth):** sensitive BYTEA columns
  (`patients.demographics_encrypted`, `ehr_integrations.auth_credentials_encrypted`)
  are envelope-encrypted with a per-record PBKDF2-HMAC-SHA256 salt (200k
  iterations) feeding a Fernet key — see `core/storage.py:SecureStorage`. The
  master key (`BUDDI_STORAGE_KEY`) has no default; the process refuses to start
  without it. Ciphertext is useless without the key even on a full DB compromise.

## 4. Access control

- **API keys:** looked up by an indexed SHA-256 hash, then verified against a
  salted **Argon2id** hash (`backend/auth.py` — `key_hash_sha256` + `hashed_key`
  on `tenant_api_keys`). Raw keys are never stored or logged.
- **Per-tenant Row-Level Security:** every tenant-scoped table enforces a
  Postgres RLS policy keyed on `current_setting('app.tenant_id')`, set per
  request by `core/db_session.py:tenant_scoped_session`. The database refuses
  cross-tenant reads even if an application filter is missing
  (`alembic/versions/7a3c8d9f0142_rls_baa_hnsw.py`).
- **Scope-based authorization:** routes require `clinician`, `ingest`, or
  `admin` scopes via `backend/auth.py:require_scope`. Test-mode never grants
  `admin`/`ingest` (no CI privilege escalation).
- **No direct DB access** is exposed to customers; all access is mediated by the
  scoped API.

## 5. Audit trail

Every clinical action is appended to `audit_events` with a SHA-256 cryptographic
hash chaining each event to its predecessor
(`backend/api.py:log_audit_event_postgres`, verified by `_verify_audit_chain`).
A daily Merkle root over the day's events is **KMS-signed** (Cloud KMS EC P-256,
or a self-managed Ed25519 key) and exported to a GCS bucket under **Object Lock
(COMPLIANCE mode, ~7-year retention)** — see `core/merkle.py`. Auditors verify
the signed root **offline** against the embedded public key. `GET /api/audit/verify`
checks both the in-DB chain and every signed root; `audit_events` is monthly
range-partitioned so verification stays fast at scale
(`alembic/versions/c4f1e2d3a5b6_partition_audit_events.py`).

## 6. LLM provider posture

- **Anthropic Claude is the primary clinical-reasoning provider, under a signed
  BAA.** Default `LLM_PROVIDER=anthropic` (`core/config.py`).
- **OpenAI is embeddings-only** and receives no PHI — only public CMS guideline
  text. An embeddings-only guard proxy raises `RuntimeError` if any non-embedding
  call is routed through OpenAI (`core/rag_engine.py:_EmbeddingsOnlyOpenAI`).
- **BAA tripwire:** while `BUDDI_BAA_CONFIRMED != 1` (or the tenant's
  `baa_confirmed` flag is false), `/ingest/fhir` returns `412` and the LLM path
  refuses any prompt that looks like PHI (oversized or `<clinical_note>`-delimited)
  — `core/llm_manager.py:_baa_guard`. This makes "PHI reached a model without a
  BAA" structurally hard, not merely procedural.
- **Logging:** `core/safety.py:redact_for_logs` strips PII patterns before any
  value reaches stdout / Cloud Logging.

## 7. Incident response

A potential PHI breach triggers a **24-hour notification SLA to legal counsel**
(45 CFR §164.408) and is treated as Sev-1. A failed nightly red-team run or
`/shadow/audit` p95 > 60s is Sev-2. The full runbook — severity tiers, the two
most-likely Sev-1 scenarios (PHI-to-LLM-without-BAA, audit-chain failure), and a
blameless post-mortem template — lives in
[`docs/INCIDENT_RESPONSE.md`](./INCIDENT_RESPONSE.md). On-call escalation and a
PagerDuty/alert-webhook integration page the on-call engineer; the nightly
adversarial red-team (`.github/workflows/red_team.yml`) alerts on any guardrail
regression.

## 8. SOC 2 roadmap

SOC 2 **Type I** assessment is in progress; **Type II** observation window to
follow. Trust Services Criteria controls already implemented in code:

1. Logical access — Argon2id API keys, scoped authorization (`backend/auth.py`).
2. Tenant isolation — Postgres RLS (`core/db_session.py`).
3. Encryption at rest — CMEK + app-layer envelope encryption (`core/storage.py`).
4. Encryption in transit — TLS 1.3 only.
5. Audit logging — tamper-evident hash chain (`backend/api.py`, `core/merkle.py`).
6. Integrity verification — daily KMS-signed Merkle roots, offline-verifiable.
7. Immutable retention — GCS Object Lock (WORM) on signed roots.
8. Change management — CI gates (lint, tests, eval regression) on every PR
   (`.github/workflows/main.yml`).
9. Adversarial testing — nightly 60-prompt red-team suite (`evals/red_team/`).
10. Rate limiting / DoS protection — per-tenant limiter (`backend/middleware.py`).
11. PII redaction in logs (`core/safety.py:redact_for_logs`).
12. Least privilege in CI — test mode never grants `admin`/`ingest`.
13. Secrets hygiene — no secret material committed; `.env.example` is the only
    template; runtime artifacts are git-ignored.
14. Vendor management — BAA tripwire enforced in code (`core/llm_manager.py`).
15. Data minimization — embeddings over public text only; PHI-free SLO metrics.

## 9. Penetration testing

An independent third-party penetration test is **scheduled for Q3 2026 with
[vendor TBD]**. Findings and remediation will be summarized in a future revision
of this document and made available under NDA on request.

## 10. Contact

Report a vulnerability or request our full compliance package at
**security@buddi.health**. We support coordinated disclosure and will acknowledge
reports within two business days.

---

*This document is generated from `docs/security_whitepaper.md`; the PDF edition
is produced from the same source. Last reviewed: update at each release.*
