import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Zap,
  Brain,
  DollarSign,
  ShieldCheck,
  ClipboardList,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import useStore from '../store/useStore';

const formatCurrency = (value) =>
  Number(value || 0).toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });

const ShadowPage = () => {
  const currentPatient = useStore((state) => state.currentPatient);
  const loadDemoPatient = useStore((state) => state.loadDemoPatient);
  const runShadowAudit = useStore((state) => state.runShadowAudit);
  const shadowResult = useStore((state) => state.shadowResult);
  const isShadowLoading = useStore((state) => state.isShadowLoading);
  const shadowError = useStore((state) => state.shadowError);

  const [noteOverride, setNoteOverride] = useState(null);
  const [billedCodesOverride, setBilledCodesOverride] = useState(null);

  const note = noteOverride ?? currentPatient.clinical_note ?? '';
  const billedCodes =
    billedCodesOverride ?? (currentPatient.billed_codes || []).join(', ');

  const parsedCodes = useMemo(
    () =>
      billedCodes
        .split(',')
        .map((code) => code.trim())
        .filter(Boolean),
    [billedCodes]
  );

  const handleTrySamplePatient = async () => {
    const patient = await loadDemoPatient();
    setNoteOverride(patient.clinical_note || '');
    setBilledCodesOverride((patient.billed_codes || []).join(', '));
    await runShadowAudit({
      note: patient.clinical_note,
      billedCodes: patient.billed_codes,
      patientId: patient.id,
      demo: true,
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    await runShadowAudit({
      note,
      billedCodes: parsedCodes,
      patientId: currentPatient.id,
    });
  };

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-12">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-100 tracking-tight flex items-center">
            <Zap className="w-8 h-8 mr-3 text-amber-400 fill-amber-400/20" />
            Shadow-Mode Revenue Audit
          </h1>
          <p className="text-slate-500 mt-1 max-w-2xl">
            Paste a clinical note and billed codes. Buddi finds missed reimbursable documentation opportunities and writes the review to a tamper-evident audit trail.
          </p>
        </div>
        <button
          onClick={handleTrySamplePatient}
          disabled={isShadowLoading}
          className="btn-primary px-5 py-3 rounded-xl text-xs font-bold flex items-center justify-center disabled:opacity-60"
        >
          {isShadowLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ClipboardList className="w-4 h-4 mr-2" />}
          Try Sample Patient PT-9012
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <form onSubmit={handleSubmit} className="lg:col-span-2 glass-panel p-6 rounded-3xl space-y-5">
          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
              Patient
            </p>
            <div className="p-4 rounded-2xl bg-white/5 border border-white/5">
              <p className="text-sm font-bold text-slate-100">{currentPatient.name}</p>
              <p className="text-xs text-slate-500 mt-1">
                {currentPatient.demo ? 'Synthetic demo data — no PHI' : `Patient ${currentPatient.id}`}
              </p>
            </div>
          </div>

          <label className="block">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
              Clinical Note
            </span>
            <textarea
              value={note}
              onChange={(event) => setNoteOverride(event.target.value)}
              rows={12}
              className="mt-2 w-full rounded-2xl bg-slate-950/80 border border-white/10 text-sm text-slate-200 p-4 focus:outline-none focus:ring-2 focus:ring-medical-500/50"
              placeholder="Paste encounter note..."
            />
          </label>

          <label className="block">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
              Already Billed Codes
            </span>
            <input
              value={billedCodes}
              onChange={(event) => setBilledCodesOverride(event.target.value)}
              className="mt-2 w-full rounded-2xl bg-slate-950/80 border border-white/10 text-sm text-slate-200 p-4 focus:outline-none focus:ring-2 focus:ring-medical-500/50"
              placeholder="E11.9, I10"
            />
          </label>

          {shadowError && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300 flex items-start">
              <AlertCircle className="w-4 h-4 mr-2 mt-0.5" />
              {shadowError}
            </div>
          )}

          <button
            type="submit"
            disabled={isShadowLoading || !note.trim()}
            className="w-full bg-medical-500 hover:bg-medical-400 text-white py-3 rounded-2xl text-sm font-bold flex items-center justify-center disabled:opacity-50"
          >
            {isShadowLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Brain className="w-4 h-4 mr-2" />}
            Run Shadow-Mode Audit
          </button>
        </form>

        <div className="lg:col-span-3 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <motion.div whileHover={{ y: -4 }} className="glass-panel p-5 rounded-3xl border-emerald-500/20 bg-emerald-500/5">
              <DollarSign className="w-5 h-5 text-emerald-400 mb-3" />
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Recoverable Annual Revenue</p>
              <p className="text-3xl font-bold text-slate-100 mt-1">{formatCurrency(shadowResult.recovered_revenue)}</p>
            </motion.div>
            <motion.div whileHover={{ y: -4 }} className="glass-panel p-5 rounded-3xl border-indigo-500/20 bg-indigo-500/5">
              <ClipboardList className="w-5 h-5 text-indigo-400 mb-3" />
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Missed Codes Found</p>
              <p className="text-3xl font-bold text-slate-100 mt-1">{shadowResult.identified_codes?.length || 0}</p>
            </motion.div>
            <motion.div whileHover={{ y: -4 }} className="glass-panel p-5 rounded-3xl border-amber-500/20 bg-amber-500/5">
              <ShieldCheck className="w-5 h-5 text-amber-400 mb-3" />
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Review Status</p>
              <p className="text-lg font-bold text-slate-100 mt-2 uppercase">
                {shadowResult.audit_hash ? 'Audit Logged' : 'Ready'}
              </p>
            </motion.div>
          </div>

          <div className="glass-panel p-6 rounded-3xl">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-lg font-bold text-slate-100">Ranked Missing-Code Suggestions</h2>
                <p className="text-xs text-slate-500 mt-1">Recommendations require human coder review before billing.</p>
              </div>
              {shadowResult.demo && (
                <span className="text-[10px] font-bold px-3 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  DEMO DATA
                </span>
              )}
            </div>

            <div className="space-y-4">
              {(shadowResult.identified_codes || []).length === 0 && (
                <div className="p-5 rounded-2xl bg-white/5 border border-white/5 text-sm text-slate-400">
                  No audit result yet. Run the sample patient or submit a note to see missed codes, rationale, revenue, and citations.
                </div>
              )}
              {(shadowResult.identified_codes || []).map((item) => (
                <div key={item.code} className="p-5 rounded-2xl bg-white/5 border border-white/5">
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-slate-100">
                        {item.code} — {item.description}
                      </p>
                      <p className="text-xs text-slate-400 mt-2 leading-relaxed">{item.justification}</p>
                    </div>
                    <div className="text-left md:text-right flex-shrink-0">
                      <p className="text-lg font-bold text-emerald-400">{formatCurrency(item.est_value)}</p>
                      <p className="text-[10px] text-slate-500 uppercase tracking-widest">
                        {Math.round((item.confidence || 0) * 100)}% confidence
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center mt-4 text-[10px] font-bold text-amber-400 uppercase tracking-widest">
                    <CheckCircle2 className="w-3 h-3 mr-2" />
                    {item.review_status || 'human_review_required'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-panel p-6 rounded-3xl border-medical-500/10">
            <h3 className="text-sm font-bold text-slate-100 mb-3">Evidence & Audit Summary</h3>
            <p className="text-xs text-slate-400 leading-relaxed mb-4">{shadowResult.summary}</p>
            <div className="flex flex-wrap gap-2">
              {(shadowResult.citations || []).map((citation) => (
                <span key={citation} className="text-[10px] bg-white/5 border border-white/10 px-3 py-1.5 rounded-full text-slate-400">
                  {citation}
                </span>
              ))}
            </div>
            {shadowResult.audit_hash && (
              <p className="text-[10px] text-slate-500 mt-4 font-mono break-all">
                Audit hash: {shadowResult.audit_hash}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ShadowPage;
