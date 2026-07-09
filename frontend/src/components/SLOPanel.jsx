import React, { useEffect } from 'react';
import {
  Gauge,
  ShieldCheck,
  AlertTriangle,
  WifiOff,
} from 'lucide-react';
import useStore from '../store/useStore';

const tone = (value, green, yellow) => {
  if (value == null) return 'var(--color-muted)';
  if (value < green) return '#047857';
  if (value <= yellow) return '#B45309';
  return '#BE123C';
};

const rateTone = (rate) => {
  if (rate == null) return 'var(--color-muted)';
  if (rate >= 0.65) return '#047857';
  if (rate >= 0.5) return '#B45309';
  return '#BE123C';
};

const Tile = ({ label, value, color }) => (
  <div
    className="rounded-card p-4"
    style={{
      backgroundColor: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
    }}
  >
    <p className="text-xs font-medium mb-1" style={{ color: 'var(--color-secondary)' }}>
      {label}
    </p>
    <p className="text-xl font-bold" style={{ color: color || 'var(--color-ink)' }}>
      {value}
    </p>
  </div>
);

const SLOPanel = () => {
  const sloMetrics = useStore((state) => state.sloMetrics);
  const sloError = useStore((state) => state.sloError);
  const demoMode = useStore((state) => state.demoMode);
  const fetchSloMetrics = useStore((state) => state.fetchSloMetrics);

  useEffect(() => {
    fetchSloMetrics();
    const id = window.setInterval(fetchSloMetrics, 30_000);
    return () => window.clearInterval(id);
  }, [fetchSloMetrics]);

  if (sloError) {
    return (
      <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
        SLO data unavailable.
      </p>
    );
  }

  const m = sloMetrics || {};
  const shadowP95 = m.shadow_audit_p95_ms;
  const priorP95 = m.prior_auth_p95_ms;
  const rate = m.suggestion_approval_rate_7d;
  const chainOk = m.audit_chain_verify_ok;

  const fmtMs = (v) => (v == null ? '—' : `${(v / 1000).toFixed(1)}s`);
  const fmtRate = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);

  return (
    <div className="space-y-4">
      {demoMode && (
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-card text-sm"
          style={{
            backgroundColor: 'var(--color-caution-bg, #FEF3E2)',
            color: '#B45309',
            border: '1px solid rgba(180, 83, 9, 0.2)',
          }}
        >
          <WifiOff size={16} />
          Demo mode — figures are canned, not from a live backend.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Tile
          label="Shadow audit p95"
          value={fmtMs(shadowP95)}
          color={tone(shadowP95, 20_000, 30_000)}
        />
        <Tile
          label="Prior-auth p95"
          value={fmtMs(priorP95)}
          color={tone(priorP95, 8_000, 10_000)}
        />
        <Tile
          label="Approval rate (7d)"
          value={fmtRate(rate)}
          color={rateTone(rate)}
        />
        <Tile
          label="Encounters (24h)"
          value={m.encounters_processed_24h ?? '—'}
          color="var(--color-ink)"
        />
      </div>

      <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-secondary)' }}>
        {chainOk ? (
          <ShieldCheck size={16} style={{ color: '#047857' }} />
        ) : (
          <AlertTriangle size={16} style={{ color: '#BE123C' }} />
        )}
        <span>
          Audit chain:{' '}
          <span
            style={{
              fontWeight: 600,
              color: chainOk ? '#047857' : chainOk === false ? '#BE123C' : 'var(--color-muted)',
            }}
          >
            {chainOk == null ? 'unknown' : chainOk ? 'verified' : 'FAILED'}
          </span>
          {m.audit_chain_last_verified_at && (
            <span className="ml-2" style={{ color: 'var(--color-muted)' }}>
              (last verified {new Date(m.audit_chain_last_verified_at).toLocaleString()})
            </span>
          )}
        </span>
      </div>
    </div>
  );
};

export default SLOPanel;
