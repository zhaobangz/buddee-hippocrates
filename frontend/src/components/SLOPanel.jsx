import React, { useEffect } from 'react';
import { Gauge, ShieldCheck, AlertTriangle, WifiOff } from 'lucide-react';
import useStore from '../store/useStore';

// Color thresholds (PROMPT_07 Task 3). Latencies are in milliseconds.
const tone = (value, green, yellow) => {
  if (value == null) return 'text-slate-400';
  if (value < green) return 'text-emerald-400';
  if (value <= yellow) return 'text-amber-400';
  return 'text-rose-400';
};

// Approval rate: higher is better, so the comparison is inverted.
const rateTone = (rate) => {
  if (rate == null) return 'text-slate-400';
  if (rate >= 0.65) return 'text-emerald-400';
  if (rate >= 0.5) return 'text-amber-400';
  return 'text-rose-400';
};

const Tile = ({ label, value, toneClass }) => (
  <div className="p-4 rounded-2xl bg-white/5 border border-white/5">
    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{label}</p>
    <p className={`text-2xl font-bold mt-1 ${toneClass}`}>{value}</p>
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
      <div className="glass-panel rounded-3xl p-6">
        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
          <Gauge className="w-4 h-4" /> SLO Health
        </h3>
        <p className="text-sm text-slate-500">SLO data unavailable.</p>
      </div>
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
    <div className="glass-panel rounded-3xl p-6">
      <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-5 flex items-center gap-2">
        <Gauge className="w-4 h-4 text-medical-400" /> SLO Health — last 24h / 7d
      </h3>

      {demoMode && (
        <div className="mb-4 flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-semibold">
          <WifiOff className="w-3.5 h-3.5" />
          Demo mode — figures are canned, not from a live backend.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Tile label="Shadow audit p95" value={fmtMs(shadowP95)} toneClass={tone(shadowP95, 20_000, 30_000)} />
        <Tile label="Prior-auth p95" value={fmtMs(priorP95)} toneClass={tone(priorP95, 8_000, 10_000)} />
        <Tile label="Approval rate (7d)" value={fmtRate(rate)} toneClass={rateTone(rate)} />
        <Tile
          label="Encounters (24h)"
          value={m.encounters_processed_24h ?? '—'}
          toneClass="text-slate-100"
        />
      </div>

      <div className="mt-4 flex items-center gap-2 text-xs">
        {chainOk ? (
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-rose-400" />
        )}
        <span className="text-slate-400">
          Audit chain:{' '}
          <span className={chainOk ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
            {chainOk == null ? 'unknown' : chainOk ? 'verified' : 'FAILED'}
          </span>
          {m.audit_chain_last_verified_at && (
            <span className="text-slate-600 ml-2">
              (last verified {new Date(m.audit_chain_last_verified_at).toLocaleString()})
            </span>
          )}
        </span>
      </div>
    </div>
  );
};

export default SLOPanel;
