# Runbook: LLM Provider Errors (Sev‑3)

**Alert:** `Buddi — LLM Provider Errors` fires when Anthropic API error/429 rate > 10% over 10 min.
**Severity:** P3 — LLM‑dependent paths degraded. Respond within 1 hour.

## Immediate response

1. Check Anthropic status: https://status.anthropic.com/
2. Check API key quota: Anthropic Console → API Keys → Usage
3. Check the agent is still bootstrapping:
   ```bash
   curl https://api.buddi.health/api/health -H "X-API-Key: $BUDDI_API_KEY" | jq '.agent_status'
   ```
   Expected: `"ready"`. If `"degraded"`, the agent fell back to deterministic stubs.
4. If the agent is degraded, suggestions are deterministic — no clinical harm, but no new LLM insights.

## Recovery

The deterministic fallback keeps the system operational during LLM outages (§1.3: "fail‑closed").
No manual intervention required — the agent re‑bootstraps automatically when the provider recovers.
Monitor for 10 minutes; if the error rate drops below 1%, the alert resolves.
