# Sprint C — Implementation Roadmap

**Status:** IaC written, awaiting GCP access + BAA sign‑off
**Owner:** CTO (Zhao) — execute top‑to‑bottom after counsel clears BAAs
**Last updated:** 2026-07-21

Each task below has a **What's done** section (committed code you can use now),
a **What you do** section (gcloud commands + config changes), and a
**Done‑when** gate matching the manual.

---

## Pre‑flight: Before any Tier 2 provisioning

- [ ] Anthropic BAA signed and counter‑signed
- [ ] Google Cloud BAA signed and counter‑signed
- [ ] `docs/COMPLIANCE/baa_status.md` updated — every Required‑BAA row = `signed: yes`
- [ ] Both founders approve Tier 2 go‑live (manual §5.2)
- [ ] GCP project created under a dedicated Google Workspace org (not personal Gmail)
- [ ] Billing alerts set at $100 threshold
- [ ] `gcloud auth login` + `gcloud config set project $GCP_PROJECT_ID`

---

## P‑C1 · Provision the GCP Tier 2 stack

### What's done
- `infra/env.tier2.example` — all 30+ placeholders documented
- `infra/provision_gcp.sh` — idempotent, `--dry-run` preview, `--teardown` destroy
- `infra/cloud-run-api.yaml` — parameterized with Secret Manager injection
- `infra/cloud-run-worker.yaml` — parameterized, scales‑to‑zero
- `docs/CLOUD_DEPLOYMENT_GUIDE.md` — existing deploy docs

### What you do

```bash
# 1. Copy and fill in the env file.
cp infra/env.tier2.example infra/env.tier2
# Edit infra/env.tier2 — replace every placeholder with real values.

# 2. Source it.
source infra/env.tier2

# 3. Preview (no changes).
bash infra/provision_gcp.sh --dry-run

# 4. Provision (requires BAA gate confirmation).
bash infra/provision_gcp.sh

# 5. Add secret versions.
echo -n 'postgresql://...' | gcloud secrets versions add buddi-database-url --data-file=-
echo -n '<32-char-hex>'  | gcloud secrets versions add buddi-secret-key --data-file=-
echo -n '<16-char-hex>'  | gcloud secrets versions add buddi-storage-key --data-file=-
echo -n '<api-key-hex>'  | gcloud secrets versions add buddi-api-key --data-file=-
echo -n 'sk-ant-...'     | gcloud secrets versions add buddi-anthropic-key --data-file=-

# 6. Enable pgvector on Cloud SQL.
gcloud sql connect buddi-prod --user=buddi_app --database=buddi
# Then run: CREATE EXTENSION IF NOT EXISTS vector;

# 7. Build + push the image.
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/$GCP_PROJECT_ID/buddi/buddi-api:prod

# 8. Deploy the services.
REGION=us-central1
PROJECT_ID=$GCP_PROJECT_ID
envsubst < infra/cloud-run-api.yaml | gcloud run services replace - --region=$REGION
envsubst < infra/cloud-run-worker.yaml | gcloud run services replace - --region=$REGION

# 9. Run migrations.
gcloud run jobs create buddi-migrate-prod \
  --image=us-central1-docker.pkg.dev/$GCP_PROJECT_ID/buddi/buddi-api:prod \
  --command="python" --args="-m,alembic,upgrade,head" \
  --region=$REGION \
  --service-account=buddi-migrate@$GCP_PROJECT_ID.iam.gserviceaccount.com \
  --set-secrets=DATABASE_URL=buddi-database-url:latest \
  --set-env-vars=BUDDI_TEST_MODE=0,ENVIRONMENT=production

gcloud run jobs execute buddi-migrate-prod --region=$REGION --wait
```

### Done‑when
`curl https://api.buddi.health/health` returns `{"status":"ok"}` and
`python scripts/verify_system.py --base-url https://api.buddi.health --demo` passes
all checks on the live host.

---

## P‑C2 · Wire Merkle signing to Cloud KMS + Object Lock

### What's done
- `core/merkle.py` — code‑complete, GCP KMS provider path exists
- `core/ledger.py` — hash‑chain logic untouched
- `tests/test_audit_merkle.py` — existing unit tests for the HMAC fallback

### What you do

**Step 1 — Set env vars on Cloud Run:**

```bash
gcloud run services update buddi-api --region=$REGION \
  --set-env-vars="BUDDI_AUDIT_KMS_PROVIDER=gcp" \
  --set-env-vars="BUDDI_AUDIT_KMS_KEY=projects/$GCP_PROJECT_ID/locations/us-central1/keyRings/buddi-prod/cryptoKeys/buddi-merkle-signing/cryptoKeyVersions/1" \
  --set-env-vars="BUDDI_AUDIT_ROOTS_BUCKET=gs://buddi-audit-roots-prod/" \
  --set-env-vars="BUDDI_AUDIT_OBJECT_LOCK_MODE=COMPLIANCE" \
  --set-env-vars="BUDDI_AUDIT_OBJECT_LOCK_DAYS=2555"
```

**Step 2 — Trigger a Merkle seal and verify:**

```bash
# Trigger the daily seal (or wait until midnight UTC).
curl -X POST https://api.buddi.health/api/audit/roots/seal \
  -H "X-API-Key: $BUDDI_API_KEY"

# Verify the audit chain end‑to‑end.
curl https://api.buddi.health/api/audit/verify \
  -H "X-API-Key: $BUDDI_API_KEY"
# Expected: {"verified": true, "status": "verified", ...}

# Download the signed root + verify offline (copy it and run locally).
gcloud storage cp gs://buddi-audit-roots-prod/$(date +%Y-%m-%d).json .
python -c "
from core.merkle import verify_signed_root_offline
result = verify_signed_root_offline(open('$(date +%Y-%m-%d).json').read())
print('Offline verification:', result)
"
# Expected: True
```

**Step 3 — Check the Object Lock status:**

```bash
gcloud storage buckets describe gs://buddi-audit-roots-prod --format="value(retentionPolicy)"
# Expected: COMPLIANCE mode, 2555d retention
```

### Done‑when
- Daily root is KMS‑signed (not HMAC)
- Signed root exported to Object Lock bucket
- `GET /api/audit/verify` returns `verified: true`
- Offline verification passes
- This moves the manual §1.3 claim from "80%" to shippable

---

## P‑C3 · Memorystore Redis ⇒ multi‑instance rate limiting

### What's done
- `backend/middleware.py` — `RateLimitMiddleware` already wired to `REDIS_URL`
- `core/jobs.py` — job queue independent of rate limiter
- `tests/test_rate_limit.py` — existing rate‑limit tests

### What you do

**Step 1 — Set REDIS_URL:**

```bash
REDIS_HOST=$(gcloud redis instances describe buddi-redis-prod \
  --region=$REGION --format="value(host)")

gcloud run services update buddi-api --region=$REGION \
  --set-env-vars="REDIS_URL=redis://$REDIS_HOST:6379/0"

gcloud run services update buddi-worker --region=$REGION \
  --set-env-vars="REDIS_URL=redis://$REDIS_HOST:6379/0"
```

**Step 2 — Test multi‑instance enforcement:**

```bash
# Run two concurrent bursts from different sources.
# Both should hit the same Redis‑backed limit, not N× the limit.
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    https://api.buddi.health/api/health \
    -H "X-API-Key: $BUDDI_API_KEY" &
done
wait
# Expect: some 429s after the rate limit is hit.
# If all 200s, the limit is NOT being enforced globally — debug Redis connectivity.
```

### Done‑when
Rate limits enforced globally (not per‑instance); bottleneck #1 closed per manual §4.2.

---

## P‑C4 · SLO dashboard‑as‑code + PagerDuty alerting

### What's done
- `/api/slo` endpoint exists
- Frontend `SLOPanel` consumes it

### What you do

**Step 1 — Deploy the GCP Monitoring dashboard:**

```bash
gcloud monitoring dashboards create \
  --config-from-file=infra/monitoring/slo_dashboard.json
```

**Step 2 — Deploy alert policies:**

```bash
gcloud alpha monitoring policies create \
  --policy-from-file=infra/monitoring/alert_policy_audit_chain.json

gcloud alpha monitoring policies create \
  --policy-from-file=infra/monitoring/alert_policy_error_rate.json

gcloud alpha monitoring policies create \
  --policy-from-file=infra/monitoring/alert_policy_llm_errors.json
```

**Step 3 — Wire PagerDuty:**

In the PagerDuty console, add the GCP Cloud Monitoring integration.
Map the alert policy severity levels to PagerDuty services:
- Audit chain verify < 100% → P1 (integrity breach — page immediately)
- Error rate > 2% over 5 min → P2
- LLM 5xx > 10% over 10 min → P3
- Grounding failure > 5% → P2

**Step 4 — Create runbook entries** (stubs in `docs/runbooks/`):

| Alert | Runbook | First response |
|-------|---------|---------------|
| audit-chain-verify | `docs/runbooks/audit_chain.md` | Check `/api/audit/verify`, check Cloud SQL, verify KMS key accessible |
| error-rate-spike | `docs/runbooks/error_rate.md` | Check Cloud Run revision status, roll back if recent deploy |
| llm-error-spike | `docs/runbooks/llm_errors.md` | Check Anthropic status page, check API key validity |

### Done‑when
Dashboard + alerts deploy from code; audit‑chain breach pages P1 (manual §2.2 Sprint C, §6.1).

---

## P‑C5 · Pilot‑readiness rehearsal

### What's done
- `scripts/provision_tenant.py` — tenant + API key creation
- `scripts/verify_system.py` — smoke test harness
- `docs/DEPLOY_CHEAP.md` — Tier 2 provisioning docs

### What you do

```bash
# 1. Provision a test tenant.
python scripts/provision_tenant.py \
  --slug pilot-rehearsal \
  --name "Pilot Rehearsal" \
  --scopes clinician,ingest

# 2. Run verify against the live Tier 2 host.
BUDDI_BASE_URL=https://api.buddi.health \
BUDDI_API_KEY=<key-from-step-1> \
  python scripts/verify_system.py --demo

# 3. Run the Synthea de‑identified bundle workflow.
#    Use one committed fixture from evals/synthea/fixtures/.
BUNDLE=$(cat evals/synthea/fixtures/marcus_holloway.json)
curl -s -X POST https://api.buddi.health/ingest/fhir \
  -H "X-API-Key: $BUDDI_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$BUNDLE"

# 4. Run shadow audit on the ingested patient.
curl -s -X POST "https://api.buddi.health/api/shadow/audit?sync=true" \
  -H "X-API-Key: $BUDDI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "note": "67-year-old male with type 2 diabetes and CKD stage 3a...",
    "billed_codes": ["E11.9", "I10"],
    "patient_id": "PT-9012",
    "demo": true
  }'

# 5. Verify audit chain integrity.
curl https://api.buddi.health/api/audit/verify \
  -H "X-API-Key: $BUDDI_API_KEY"
# Must return {"verified": true, ...}

# 6. Check that a signed root landed in Object Lock.
gcloud storage ls gs://buddi-audit-roots-prod/$(date +%Y-%m-%d).json
```

### Done‑when
- Full pilot path passes at <30s p95
- `GET /api/audit/verify` = 100%
- Signed root in Object Lock
- `docs/runbooks/pilot_kickoff.md` exists (see template below)

---

## Cross‑cutting hardening (P‑X1 through P‑X4)

### P‑X1 · Trivy image scanning in CI

**What's done:** CI already has pip‑audit + gitleaks + Docker build.

**You do:**
1. Add this step to `.github/workflows/main.yml` after the Docker build:

```yaml
- name: Trivy image scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: buddi-api:local
    format: table
    severity: HIGH,CRITICAL
    exit-code: 1
```

2. Create `.trivyignore` for accepted findings.

### P‑X2 · mypy burn‑down

**You do:**
```bash
# Run mypy across the tree, bucket by module.
pip install mypy
mypy backend/ core/ --ignore-missing-imports 2>&1 | tee mypy_report.txt

# Count errors per module.
grep -c "error:" mypy_report.txt

# Fix the cheapest module first (fewest errors), flip to enforced in CI.
# In .github/workflows/main.yml, add:
#   - name: mypy (enforced — backend/api.py)
#     run: mypy backend/api.py --ignore-missing-imports
#   - name: mypy (advisory — remaining)
#     run: mypy backend/ core/ --ignore-missing-imports || true
```

### P‑X3 · Operator‑UI MFA

**Design (build only if multi‑tenant pilot is confirmed):**
- TOTP‑based MFA behind a feature flag (`ENABLE_MFA`)
- Off for the public synthetic demo (no PHI, no MFA friction)
- Required for any tenant with `baa_confirmed = TRUE`
- Store TOTP secrets encrypted via `core/secure_fields.py`
- Add `POST /api/auth/mfa/setup` and `POST /api/auth/mfa/verify` routes
- Frontend: TOTP input field on the ApiKeyPrompt screen when MFA is required

### P‑X4 · Conversational memory session store

**Design (build only if multi‑turn is on the pilot's critical path):**
- Tenant‑scoped, RLS‑safe session store on Redis/Memorystore
- Each session keyed by `tenant_id:conversation_id`
- TTL = 1 hour (auto‑expire, no PHI accumulation)
- Messages stored as JSON blobs with `redact_for_logs()` applied before any logging
- Gate the feature behind `BUDDI_BAA_CONFIRMED=1` and `ENABLE_MULTI_TURN=true`
- API: `POST /api/chat/sessions` (create), `GET /api/chat/sessions/{id}` (load), `DELETE /api/chat/sessions/{id}` (clear)

---

## Post‑provisioning: Pilot kickoff runbook template

See `docs/runbooks/pilot_kickoff.md` — create this file with:

1. **Tenant provisioning:** `python scripts/provision_tenant.py` per design partner
2. **BAA flip:** SQL command that flips `tenants.baa_confirmed = TRUE` for the tenant (counsel‑gated)
3. **Clinician workflow:** weekly review cadence, shadow‑mode review, human‑approval step
4. **North Star metric:** Approved Recovered Revenue per Tenant per Month (manual §6.1)
5. **Escalation:** PagerDuty contact, Slack channel, weekly founder sync

---

## Quick‑reference: env vars for Tier 2 production

```
# Security (Secret Manager)
SECRET_KEY=<32+ chars>
BUDDI_STORAGE_KEY=<16+ chars>
API_KEY=<service key>
ANTHROPIC_API_KEY=sk-ant-...

# Database (Cloud SQL, CMEK)
DATABASE_URL=postgresql://buddi_app:<pw>@<private-ip>:5432/buddi

# PHI guard
BUDDI_BAA_CONFIRMED=0   # ⛔  Flip to 1 ONLY after BAAs signed

# Audit (Cloud KMS + GCS Object Lock)
BUDDI_AUDIT_KMS_PROVIDER=gcp
BUDDI_AUDIT_KMS_KEY=projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>/cryptoKeyVersions/1
BUDDI_AUDIT_ROOTS_BUCKET=gs://buddi-audit-roots-prod/
BUDDI_AUDIT_OBJECT_LOCK_MODE=COMPLIANCE
BUDDI_AUDIT_OBJECT_LOCK_DAYS=2555

# Redis (Memorystore)
REDIS_URL=redis://<host>:6379/0

# Provider
LLM_PROVIDER=anthropic

# Rate limiting
BUDDI_RATE_LIMIT_DISABLED=0
TRUSTED_PROXY_CIDRS=<Cloud Run ingress CIDRs>

# CORS
CORS_ORIGINS=https://app.buddi.health

# Monitoring
OTLP_ENDPOINT=<Cloud Trace endpoint>
```
