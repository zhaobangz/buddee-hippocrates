# Buddee Codebase Audit — July 16, 2026

Scope: full pass over `backend/` (~4.3k LOC), `core/` (~9.1k LOC), `frontend/src` (~3.3k LOC), Alembic migrations, and Docker/config. Methods: bandit + ruff + secret/anti-pattern scans, manual review of every security-critical path (auth, tenant isolation/RLS, audit chain, SSRF, PHI gates, Stripe/SMART OAuth, path traversal), plus targeted concurrency regression tests. Full test suite after fixes: **101 passed, 18 skipped (require live Postgres), 0 failed; ruff clean.**

Overall: this codebase is in far better shape than typical pre-pilot startups — prior hardening passes (SEC-01…10, CQ-07, Issues 7/8) clearly paid off. Auth (Argon2 + constant-time lookup, scoped keys), CORS, SSRF validation, Stripe signature verification, SMART/PKCE flow, path-traversal guards, and secret handling are all solid. The critical findings below were concentrated in the newest multi-tenancy and audit-chain code, and all four fixable ones are now fixed.

## Fixed in this pass

### 1. CRITICAL — RLS tenant context silently cleared by mid-request commits
`core/db_session.py`, `core/worker.py`

`tenant_scoped_session` stamped `app.tenant_id` with `set_config(..., true)`, which is **transaction**-scoped. The first `db.commit()` in a request — which the audit logger performs on nearly every route — ended that transaction and cleared the GUC. Under `FORCE ROW LEVEL SECURITY` (enabled on every tenant table), every subsequent query in that request would return **zero rows** and every write would fail its `WITH CHECK` on production Postgres. The worker loop had the same bug with `app.worker_mode` (cleared by the commit right after claiming a job). Tests never caught it because they run without RLS.

Fix: new `GucStamper` registers a SQLAlchemy `after_begin` listener that re-stamps both GUCs at the start of every transaction (the canonical multi-tenant RLS pattern). Fail-closed semantics are preserved: pooled connections still carry no context between requests. Wired into both the FastAPI dependency and the worker loop.

### 2. CRITICAL — audit hash chain forks under concurrent writes
`backend/api.py` — `log_audit_event_postgres`

The chain tip was read with a plain SELECT before insert. Two concurrent writers (multiple uvicorn workers, Cloud Run instances, or API + worker) read the same tip and both chain onto it — a fork that `_verify_audit_chain` later reports as `chain_broken`. Net effect: under any real load, the product's flagship "tamper-evident" guarantee produces **false tamper alarms**.

Fix: the tip-read → insert → commit section is now serialized per tenant chain via `pg_advisory_xact_lock` (auto-released at commit, cross-instance safe) with a process-level mutex fallback for non-Postgres dialects. Regression-tested with 60 concurrent writes from 6 threads: chain verifies clean.

### 3. HIGH — day-scoped chain verification always false-alarms
`backend/api.py` — `_verify_audit_chain`

`GET /api/audit/verify?day=YYYY-MM-DD` seeded the walk with `previous_hash = None`, but the first event of any day correctly points at the prior day's tip — so day-scoped verification reported `chain_broken` for every day except the tenant's very first. This is the endpoint an operator would use during an actual CMS/RADV inquiry.

Fix: day-scoped walks now seed from the chain tip immediately before the window (single indexed lookup). Regression test covers multi-day chains.

### 4. MEDIUM — seal endpoint accepts incomplete days
`backend/api.py` — `POST /api/audit/roots/seal`

The `day` parameter accepted today or future dates. Sealing a partial day signs a premature Merkle root; later events change the recomputed root, verification reports the day as tampered, and the WORM/Object Lock mirror of the bad envelope is by design undeletable. Fix: 422 for any `day >= today (UTC)`.

### 5. LOW — fire-and-forget webhook tasks could be GC'd mid-flight
`backend/api.py` — `_maybe_schedule_audit_flagged`

`loop.create_task(...)` result was unreferenced; the event loop holds only weak refs, so high-risk audit webhooks could silently never deliver. Fix: strong refs held in a module set until completion.

## Reported, not changed (recommendations)

**DNS-rebinding TOCTOU in SSRF validation (Medium).** `validate_outbound_url` resolves the hostname at validation time, but httpx re-resolves at connect time; a malicious DNS server can pass validation with a public IP then serve a private one. Exploitation requires an admin-scoped API key (webhook registration), which limits exposure. Recommended: pin the validated IP via a custom httpx transport, or route webhook egress through a proxy that re-enforces the IP policy.

**Self-attesting signature envelopes (Medium).** `verify_envelope` verifies asymmetric signatures against the `public_key_pem` embedded in the envelope itself. An attacker who can rewrite both DB and local root files can re-sign history with their own key and pass API-level verification; the design's true anchor is the Object Lock mirror plus the published key. Recommended: add `BUDDI_AUDIT_TRUSTED_KEY_IDS` (or pinned PEM set) and have `/api/audit/verify` flag envelopes signed by unknown keys.

**Audit logging fails open (design decision to revisit).** `log_audit_event_postgres` swallows all exceptions and returns `None`; PHI-touching operations proceed even when the audit write failed. Defensible for availability, but at odds with the audit-trail marketing promise. Consider failing closed (or queueing durable retries) for PHI-material events, and alerting on any `None` return.

**PBKDF2 per-record derivation is expensive (Performance).** Every `SecureStorage` encrypt/decrypt runs 200k-iteration PBKDF2 (~50–100 ms). Webhook dispatch does one per endpoint per event; SMART token reads add more. Fine at pilot volume, will hurt at scale. Recommended: derive a master key once and use per-record random data keys (HKDF), or cache derivations keyed by salt.

**Minor.** `SecureStorage` logs errors via `print()` instead of `logging` (ops visibility); the ZIP/DOB/PHONE redaction regexes over-match (acceptable for logs — bias toward over-redaction); rate limiter fails open on Redis outage (documented and alarmed, reasonable); `/api/audit/verify` deep walk is O(all events) — already documented with the signed-roots fast path.

## Verification performed

Full pytest suite (101 passed / 18 skipped — the skips require the Postgres test container, same as before the changes), ruff clean, py_compile clean, plus a purpose-built regression harness: 6-event multi-day chain verifies full/per-day; 60 concurrent audit writes across 6 threads produce an unbroken chain with zero write errors. The Postgres-only branches (advisory lock SQL, `after_begin` GUC stamping) compile and are dialect-gated; they should get one end-to-end pass against the `localhost:5433` test Postgres in CI before the next deploy — `pytest tests/` picks them up automatically once the container is up.
