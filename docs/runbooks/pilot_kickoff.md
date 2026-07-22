# Pilot Kickoff Runbook

**Status:** Template — fill in per design partner
**Owner:** CTO (Zhao) + clinical advisor
**Manual ref:** §2.2 Sprint C pilot‑ready gate, §3.4 pilot funnel, §6.1 North Star

---

## 1. Pre‑launch checklist (counsel‑gated)

- [ ] Both BAAs fully executed (Anthropic + GCP) — see `docs/COMPLIANCE/baa_status.md`
- [ ] Tier 2 infrastructure provisioned (`infra/provision_gcp.sh` → all green)
- [ ] `BUDDI_BAA_CONFIRMED=0` on the API — do NOT flip yet
- [ ] Design partner agreement signed (pilot scope, data use, term)
- [ ] Design partner designated a clinical reviewer (licensed, board‑certified)
- [ ] Post‑deploy smoke test passes: `python scripts/verify_system.py --base-url https://api.buddi.health --demo`
- [ ] CI green on `main` branch (latest commit at time of launch)

---

## 2. Tenant provisioning

```bash
# For each design partner, run ONCE.
# The raw API key is printed once — copy it securely.
python scripts/provision_tenant.py \
  --slug <partner-slug> \
  --name "<Partner Name>" \
  --scopes clinician,ingest

# Output:
#   Tenant ID: <uuid>
#   API Key:   <raw-key>   ← copy this; it is never stored in plaintext
```

**Do NOT** email the API key. Deliver it via a one‑time secure link (1Password, `gcloud secrets versions add` shared link, or in‑person).

---

## 3. BAA flip (counsel‑gated — do NOT skip)

Only after both BAAs are signed AND counsel confirms:

```sql
-- Flip the tenant's BAA flag. This allows real PHI on /ingest/fhir.
-- The API still requires BUDDI_BAA_CONFIRMED=1 in its env — this is the
-- second gate. Flip both when counsel confirms.

UPDATE tenants
   SET baa_confirmed = TRUE,
       baa_confirmed_at = NOW()
 WHERE slug = '<partner-slug>';

-- Then set BUDDI_BAA_CONFIRMED=1 on the Cloud Run service:
gcloud run services update buddi-api --region=us-central1 \
  --set-env-vars="BUDDI_BAA_CONFIRMED=1"
```

**Rollback if needed:**

```sql
UPDATE tenants SET baa_confirmed = FALSE, baa_confirmed_at = NULL WHERE slug = '<partner-slug>';
```

```bash
gcloud run services update buddi-api --region=us-central1 \
  --set-env-vars="BUDDI_BAA_CONFIRMED=0"
```

---

## 4. Design partner onboarding

### Week 1 — Shadow mode only

1. Partner uploads **≤5 de‑identified charts** via `/ingest/fhir`
2. Buddi surfaces HCC suggestions in the Review Queue
3. **Clinician reviews every suggestion** before any action
4. No prior‑auth drafts, no EHR writes, no auto‑submission
5. Weekly sync: founder + design partner clinician — what was caught, what was missed

### Week 2+ — Prior auth (if pilot scope includes it)

1. Partner flags an encounter for prior‑auth review
2. Buddi drafts the prior‑auth document with clinical evidence
3. **Clinician reviews and edits** the draft
4. Clinician submits through their existing EHR workflow — Buddi never auto‑submits

---

## 5. Weekly clinician review cadence

| Day | Activity | Owner |
|-----|----------|-------|
| Monday | Export last week's suggestions from `/api/audit/query` | CTO |
| Tuesday | Clinician reviews each suggestion: Accept / Reject / Edit | Design partner clinician |
| Wednesday | CTO reviews rejection reasons, flags prompt‑path issues | CTO |
| Friday | Weekly retro: what was caught, what was missed, what's the recovered revenue tally | Both |

Record every Accept/Reject/Edit decision. This is your eval signal for tuning the confidence floor.

---

## 6. North Star instrumentation (manual §6.1)

**Metric:** Approved Recovered Revenue per Tenant per Month

```
ARRPM = sum(est_value of ACCEPTED hcc_suggestions this month)
```

Check weekly:

```bash
curl https://api.buddi.health/api/dashboard/metrics \
  -H "X-API-Key: $BUDDI_API_KEY" | jq '.total_recovered_revenue'
```

Track alongside:
- **Miss rate:** charts where the clinician found a code Buddi missed
- **Rejection rate:** suggestions the clinician rejected (false positives)
- **Acceptance rate:** suggestions the clinician approved (true positives)
- **Time to review:** how long the clinician spent per chart

---

## 7. Escalation

| Situation | Action |
|-----------|--------|
| Audit chain verification returns `verified: false` | Sev‑1 — page CTO immediately via PagerDuty. See `docs/runbooks/audit_chain.md` |
| Error rate > 2% sustained for 5 min | Sev‑2 — check Cloud Run revision, consider rollback. See `docs/runbooks/error_rate.md` |
| LLM API errors > 10% for 10 min | Sev‑3 — check Anthropic status page, check API key quota. See `docs/runbooks/llm_errors.md` |
| Clinician flags a clinical error in a suggestion | Log it, do NOT change the prompt path — route through the eval gate (manual §4.4) |
| Design partner wants a new feature | File it — do NOT build on the call. Both‑founder review per manual §5.2 |

---

## 8. Pilot exit criteria (when do we call it done?)

1. **≥50 charts processed** through the full shadow‑mode workflow
2. **≥70% clinician acceptance rate** on surfaced suggestions
3. **Zero must‑abstain violations** (agent never surfaced a code it shouldn't have)
4. **Audit chain verified at 100%** for every day of the pilot
5. **Both founders + design partner clinician** agree the workflow is production‑ready
6. **ARRPM** tracked and directionally positive

When all six are met → graduate from Pilot to General Availability (Sprint D).
