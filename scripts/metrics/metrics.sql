-- Buddi SLO metrics (build-out C2)
-- ---------------------------------------------------------------------------
-- Standalone, PHI-safe SQL reproducing GET /api/metrics/slo. Point a read
-- replica + Metabase / Looker Studio at this. Every output is a duration,
-- count, boolean, or timestamp — no patient identifiers.
--
-- Durations are read from the `duration_ms` field stamped into the JSONB
-- audit payload by backend/api.py (shadow_mode_rcm + prior_auth_draft_generated
-- audit events). Replace :tenant_id with the tenant UUID (or remove the
-- tenant filters for a fleet-wide dashboard).

-- 1) Shadow-mode audit latency percentiles (last 24h), milliseconds.
SELECT
    percentile_cont(0.50) WITHIN GROUP (ORDER BY (payload->>'duration_ms')::numeric) AS shadow_audit_p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY (payload->>'duration_ms')::numeric) AS shadow_audit_p95_ms,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY (payload->>'duration_ms')::numeric) AS shadow_audit_p99_ms
FROM audit_events
WHERE tenant_id = :tenant_id
  AND event_type IN ('shadow_mode_rcm', 'shadow_mode_rcm_demo')
  AND (payload->>'duration_ms') IS NOT NULL
  AND timestamp >= now() - interval '24 hours';

-- 2) Prior-auth draft latency p95 (last 24h), milliseconds.
SELECT
    percentile_cont(0.95) WITHIN GROUP (ORDER BY (payload->>'duration_ms')::numeric) AS prior_auth_p95_ms
FROM audit_events
WHERE tenant_id = :tenant_id
  AND event_type IN ('prior_auth_draft_generated', 'prior_auth_draft_generated_demo')
  AND (payload->>'duration_ms') IS NOT NULL
  AND timestamp >= now() - interval '24 hours';

-- 3) Suggestions approved in the last 7 days.
SELECT count(*) AS suggestions_approved_7d
FROM hcc_suggestions
WHERE tenant_id = :tenant_id
  AND status = 'approved'
  AND created_at >= now() - interval '7 days';

-- 4) Abstentions in the last 7 days (safety-floor / judge events).
SELECT count(*) AS suggestions_abstained_7d
FROM audit_events
WHERE tenant_id = :tenant_id
  AND event_type ILIKE '%abstain%'
  AND timestamp >= now() - interval '7 days';
