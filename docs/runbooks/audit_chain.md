# Runbook: Audit Chain Integrity Breach (Sev‑1)

**Alert:** `Buddi — Audit Chain Integrity` fires when `GET /api/audit/verify` returns `verified: false` or `partially_verified`.
**Severity:** P1 — integrity breach. Page immediately.
**Manual ref:** §2.3 (audit‑chain integrity is a customer‑visible safety signal)

## Immediate response

1. **Check the endpoint directly:**
   ```bash
   curl https://api.buddi.health/api/audit/verify -H "X-API-Key: $BUDDI_API_KEY" | jq .
   ```
2. **Is it a single day or all days?** Check the `days` array in the response.
3. **If `verified: false` on all days:** the signed‑root verification path is broken — check Cloud KMS accessibility.
4. **If a single day is `partially_verified`:** that day's events were re‑ordered or a hash link broke.

## Common causes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `verified: false` all days | KMS key unavailable or IAM revoked | Check `BUDDI_AUDIT_KMS_KEY` env var; verify the API SA has `cloudkms.signer` role |
| `partially_verified` one day | DB write conflict on that day's audit events | Check Cloud SQL logs for deadlocks; verify advisory lock held |
| `checked_days: 0` | No signed roots exist yet (fresh deploy) | Manually trigger a seal: `POST /api/audit/roots/seal` |
| HTTP 500 from verify endpoint | Cloud SQL unreachable | Check Cloud SQL instance status, VPC connector |

## Recovery steps

1. Fix the underlying cause (KMS, Cloud SQL, IAM)
2. Re‑seal the affected day: `POST /api/audit/roots/seal?day=YYYY-MM-DD`
3. Verify again: `GET /api/audit/verify`
4. Confirm the signed root landed in Object Lock: `gsutil ls gs://buddi-audit-roots-prod/YYYY-MM-DD.json`
5. Post‑mortem: file in `docs/RETRO/`
