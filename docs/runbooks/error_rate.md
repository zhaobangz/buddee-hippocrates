# Runbook: Error Rate Spike (Sev‑2)

**Alert:** `Buddi — Error Rate Spike` fires when 5xx error rate > 2% over 5 minutes.
**Severity:** P2 — degraded service. Respond within 30 min during business hours.

## Immediate response

1. Check Cloud Run revision status:
   ```bash
   gcloud run revisions list --service=buddi-api --region=us-central1 --limit=5
   ```
2. Was there a recent deploy? If yes, this is likely a bad revision → roll back:
   ```bash
   gcloud run services update-traffic buddi-api --to-latest --region=us-central1
   # Or to a specific known‑good revision:
   gcloud run services update-traffic buddi-api \
     --to-revisions=<good-revision>=100 --region=us-central1
   ```

3. Check Cloud SQL:
   ```bash
   gcloud sql instances describe buddi-prod --format="value(state)"
   ```

4. Check Anthropic status: https://status.anthropic.com/
