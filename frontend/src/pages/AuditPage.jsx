import React, { useEffect } from 'react';
import {
  ShieldCheck,
  Lock,
  ExternalLink,
  History,
  AlertTriangle,
  Info,
} from 'lucide-react';
import useStore from '../store/useStore';

/**
 * Audit & Safety surface.
 *
 * FE-04 (April-21 verification): the previous revision hard-coded
 * CheckCircle2 badges for HIPAA / FedRAMP / SOC2 / AES-256 compliance.
 * Those were not tied to any runtime state — displaying them in a
 * HIPAA-scope product before the actual certifications exist is a
 * regulatory and legal risk and has been removed.
 *
 * FE-03: the page now fetches the audit log on mount instead of
 * relying on another page to populate the store first.
 */
const AuditPage = () => {
  const auditEvents = useStore((state) => state.auditEvents);
  const fetchAuditLogs = useStore((state) => state.fetchAuditLogs);

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-12">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-slate-100 tracking-tight flex items-center">
            <ShieldCheck className="w-8 h-8 mr-3 text-emerald-500 fill-emerald-500/10" />
            Safety & Audit System
          </h1>
          <p className="text-slate-500 mt-1">
            Verifiable transparency for all Agentic AI actions
          </p>
        </div>
        <button className="btn-secondary text-xs flex items-center">
          <Lock className="w-3 h-3 mr-2" />
          Download Signed Audit Log (PDF)
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          {auditEvents.length === 0 && (
            <div className="glass-panel p-5 rounded-2xl text-sm text-slate-400">
              No audit events recorded yet.
            </div>
          )}
          {auditEvents.map((event) => (
            <div
              key={event.id}
              className="glass-panel p-5 rounded-2xl flex items-center justify-between group hover:border-white/20 transition-all"
            >
              <div className="flex items-center space-x-4">
                <div
                  className={`p-3 rounded-xl ${
                    event.risk === 'high'
                      ? 'bg-rose-500/10 text-rose-500'
                      : 'bg-emerald-500/10 text-emerald-500'
                  }`}
                >
                  <History className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-sm font-bold text-slate-200">
                    {event.action}
                  </p>
                  <div className="flex items-center space-x-3 mt-1">
                    <span className="text-[10px] text-slate-500 font-medium">
                      User: {event.user}
                    </span>
                    <span className="text-[10px] text-slate-600">•</span>
                    <span className="text-[10px] text-slate-500">
                      {event.timestamp}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center space-x-4">
                <span
                  className={`text-[10px] font-bold px-2 py-1 rounded-lg uppercase tracking-wider ${
                    event.risk === 'high'
                      ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
                      : event.risk === 'medium'
                      ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                      : 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                  }`}
                >
                  {event.risk} RISK
                </span>
                <button className="p-2 text-slate-600 hover:text-white transition-colors">
                  <ExternalLink className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-6">
          {/* FE-04: Compliance certification badges removed. This panel
              now describes the posture work that is still in progress
              instead of asserting certifications that do not yet exist. */}
          <div className="glass-panel p-6 rounded-3xl bg-slate-500/5 border-slate-500/10">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center">
              <Info className="w-4 h-4 mr-2" />
              Compliance Posture
            </h3>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Buddi is currently pre-certification. HIPAA, FedRAMP, and SOC 2
              Type II attestations are in scope for the launch roadmap but
              are not yet in effect. No compliance badges will be shown here
              until the corresponding audits have been completed and signed
              by an external QSA/3PAO.
            </p>
          </div>

          <div className="glass-panel p-6 rounded-3xl bg-rose-500/5 border-rose-500/10">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">
              Pending Confirmations
            </h3>
            <p className="text-[10px] text-slate-500 mb-4">
              The following AI-generated actions require direct human
              validation before execution.
            </p>
            <div className="p-3 rounded-xl bg-white/5 border border-white/5 space-y-3">
              <div className="flex items-start">
                <AlertTriangle className="w-4 h-4 text-amber-500 mr-3 mt-0.5" />
                <div>
                  <p className="text-[11px] font-bold text-slate-200">
                    EHR Write: Note Addition
                  </p>
                  <p className="text-[10px] text-slate-500 mt-1">
                    Adding "Refined T2D Plan" to active visit note.
                  </p>
                </div>
              </div>
              <div className="flex space-x-2">
                <button className="flex-1 py-1.5 rounded-lg bg-emerald-500 text-white text-[10px] font-bold">
                  APPROVE
                </button>
                <button className="flex-1 py-1.5 rounded-lg bg-white/5 text-slate-400 text-[10px] font-bold">
                  REJECT
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuditPage;
