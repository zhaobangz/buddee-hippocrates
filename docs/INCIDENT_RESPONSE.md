# Incident Response Runbook

**Owner:** Founder (Zhao) — primary on-call until Hire #2 lands.
**Manual reference:** §4.3 release cadence, §7.2 Risk #1, §7.3 lower-tier risks.
**Last reviewed:** *fill in at every retrospective*

This is the one-page runbook the on-call engineer reaches for at 3am.
It covers the three incident classes that matter for a HIPAA-regulated
AI product: PHI exposure, audit-chain integrity, and availability.

## Severity tiers

| Tier  | Definition                                                                                  | Initial response time | Notification           |
| ----- | ------------------------------------------------------------------------------------------- | --------------------- | ---------------------- |
| Sev-1 | Suspected or confirmed PHI breach; audit chain fails verification; production fully down.   | Immediate (<15min)    | Founder + counsel.     |
| Sev-2 | `/shadow/audit` p95 > 60s; nightly red-team suite failure; partial outage; degraded LLM provider; a single tenant cannot ingest. | 1 hour | Founder + customer. |
| Sev-3 | Elevated error rate; eval regression in production; cost / quota alert.                      | 4 business hours      | Founder.               |

## Sev-1: PHI breach (suspected or confirmed)

The 60-day HIPAA breach-notification clock starts the moment Buddi
knows or *should have known* (45 CFR § 164.408). Move fast.

1. **Stop the bleed.** Set `BUDDI_BAA_INGEST_ENFORCEMENT=disabled` to
   *false* (i.e. leave default enforcement on) and rotate
   `API_KEY` / per-tenant keys so further ingest is blocked.
2. **Capture forensics.** Snapshot Cloud Logging for the last 24h and
   pull the audit chain for the affected tenant:

   ```bash
   gcloud logging read 'resource.type="cloud_run_revision"' --limit=10000 \
       --format=json > /tmp/incident-${INCIDENT_ID}.json
   curl -H "Authorization: Bearer $BUDDI_ADMIN_KEY" \
       "$BUDDI_API/api/audit/query?tenant_id=$TENANT_ID" > /tmp/audit-${INCIDENT_ID}.json
   ```
3. **Notify counsel within 1 hour.** They start the 60-day clock and
   the state attorney general notifications.
4. **Notify the customer within 24 hours**, even if the breach is
   unconfirmed. They have their own notification obligations.
5. **Open a privileged retrospective document** under
   `docs/RETRO/incident-YYYY-MM-DD.md` (not committed to git).

## Sev-1: PHI sent to an LLM without an executed BAA

The single highest-probability Sev-1 (§7.2 Risk #1): real PHI reaches a model
provider before the Business Associate Agreement is on file. The BAA tripwire
(`core/llm_manager._baa_guard` + the `/ingest/fhir` 412 guard) should make this
impossible, so its occurrence means the guard regressed.

1. **Stop the bleed.** Confirm `BUDDI_BAA_CONFIRMED` is `0` (or flip it) and
   confirm the affected tenant's `tenants.baa_confirmed` is `false`. Both gate
   ingest; with either tripped, `/ingest/fhir` returns 412 and the LLM path
   refuses oversized / `<clinical_note>`-delimited prompts.
2. **Identify what was sent.** Pull the audit chain for the tenant and grep for
   `shadow_mode_rcm` / `prior_auth_draft` events in the exposure window — the
   payloads record note length and codes (PHI itself is `redact_for_logs`-clean
   in logs, encrypted at rest in the DB).
3. **Confirm provider retention.** Anthropic under a BAA does not train on or
   retain inputs; without a BAA, assume the input was retained and treat as a
   breach. Contact the provider to request deletion and a written attestation.
4. **Treat as a PHI breach** — follow the breach procedure below (counsel within
   1 hour; 45 CFR § 164.408 clock).

## Sev-1: Audit chain fails verification

`GET /api/audit/verify` returns `verified: false` or
`status: chain_broken` / `hash_mismatch` / `signed_root_mismatch`.

1. **Do not write any further audit events** until forensics is
   complete — additional writes corrupt the gap analysis. Set
   `BUDDI_DISABLE_MERKLE_TASK=1` and route inbound traffic to
   read-only.
2. **Pull the most recent signed Merkle root** from
   `BUDDI_AUDIT_ROOTS_DIR` and verify against the last known-good DB
   snapshot:

   ```bash
   python -c "
   from core.database import SessionLocal
   from core.merkle import verify_signed_roots_against_db
   db = SessionLocal()
   print(verify_signed_roots_against_db(db))
   "
   ```
3. **Identify the divergence.** The signed Merkle root tells you which
   day the chain broke. Restore from the most recent backup *before*
   that day; bring up a read-only replica to investigate the live
   state.
4. **Notify counsel before any customer communication.** An audit-
   chain failure can be both a PHI exposure (if the audit log
   contained PHI in a payload) and a False Claims Act risk (if the
   audit log was the artifact a customer relied on for billing
   provenance).

## Sev-2: LLM provider degraded (Anthropic 5xx / 429s)

1. Check `https://status.anthropic.com`. If site-wide, communicate to
   customers and queue ingest via Cloud Tasks (when implemented).
2. If tenant-specific, check the per-tenant rate-limit bucket in
   `backend/middleware.py:_TokenBucketLimiter.state_for`.
3. As a temporary fallback, set `LLM_PROVIDER=openai` only if the
   OpenAI BAA is current — otherwise refuse to serve LLM-dependent
   routes. This is what makes the BAA tripwire load-bearing.

## Sev-2: Production deploy gone wrong

Cloud Run keeps the last 30 days of revisions. Roll back via the
console:

```bash
gcloud run services update-traffic buddi-api \
    --to-revisions=buddi-api-00099-abc=100
```

Then open a retrospective entry in `docs/RETRO/` for the post-mortem.

## Sev-3: Eval regression in production

Triggered by the nightly LLM-on eval job (when wired) reporting
precision / recall below the floor in `evals/baseline.json`.

1. Pull the per-case JSON output from the workflow artifact.
2. Identify which cases regressed and which providers were used.
3. Open a PR raising `BUDDI_HCC_CONFIDENCE_FLOOR` for the affected
   intent path until the underlying regression is fixed. The
   `must_abstain_codes` violations from the offline gate will block
   the PR from merging if it makes things worse.

## Communications templates

Customer-facing language for a Sev-1 should be drafted by counsel,
not by the engineer at 3am. Pre-built templates live under
`docs/COMMS/` (TODO).

## On-call escalation

| Role               | Owner                     | Backup            |
| ------------------ | ------------------------- | ----------------- |
| Primary on-call    | `[FOUNDER_NAME]`          | Hire #2 (TBD)     |
| Counsel            | (TBD firm)                | —                 |
| Clinical advisor   | `[CLINICAL_ADVISOR_NAME]` | `[FOUNDER_NAME]`  |
| Cloud / KMS access | `[FOUNDER_NAME]`          | Hire #2 (TBD)     |

The "founder gets sick" mitigation in manual §7.3 #10 lives here:
the Cloud Run + Cloud SQL + KMS infrastructure must run unattended
for ≥30 days. Document the GPG-key escrow location at the next
retrospective.

## Post-mortem template

Copy into `docs/RETRO/incident-YYYY-MM-DD.md` (gitignored) within 5 business
days of any Sev-1 / Sev-2. Blameless — focus on the system, not the person.

```markdown
# Incident <YYYY-MM-DD> — <one-line title>

- **Severity:** Sev-_
- **Detected at / by:** <UTC timestamp> / <alert | customer | manual>
- **Resolved at:** <UTC timestamp>   **Duration:** <hh:mm>
- **Author / responders:** [FOUNDER_NAME], …
- **PHI involved?:** yes / no   **Breach clock started (§164.408)?:** yes / no

## Impact
Who/what was affected (tenants, records, SLO), and for how long.

## Timeline (UTC)
- HH:MM — …

## Root cause
The technical cause and the contributing factors (the "5 whys").

## Detection & response
How we found out; what worked; where we lost time.

## Action items
| # | Action | Owner | Due | Status |
|---|--------|-------|-----|--------|
| 1 | …      | …     | …   | open   |

## Lessons / guardrails added
Tests, alerts, or runbook updates that make this class of incident impossible
or self-evident next time.
```
