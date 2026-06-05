import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  FileText,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Copy,
  ClipboardCheck,
} from 'lucide-react';
import useStore from '../store/useStore';

/**
 * Prior-Authorization draft modal.
 *
 * Drives the `/api/prior-auth/generate` endpoint via the store's
 * `generatePriorAuth` action. Shows the structured PriorAuthDraft fields
 * the backend returns (draft_letter, supporting_codes, payer_rationale,
 * evidence_snippets, missing_information) plus the audit hash so the
 * operator can see the request was logged.
 *
 * The component never auto-submits to a payer — that is a structural
 * property of the product (manual §1.3 #10). The footer surfaces this
 * explicitly so a hurried clinician cannot mistake the draft for a
 * filed submission.
 */
const PriorAuthModal = ({ open, onClose }) => {
  const generatePriorAuth = useStore((s) => s.generatePriorAuth);
  const priorAuthDraft = useStore((s) => s.priorAuthDraft);
  const isPriorAuthLoading = useStore((s) => s.isPriorAuthLoading);
  const priorAuthError = useStore((s) => s.priorAuthError);
  const currentPatient = useStore((s) => s.currentPatient);

  const [procedureCode, setProcedureCode] = useState('CPT-99213');
  const [payer, setPayer] = useState('Medicare');
  const [clinicalContext, setClinicalContext] = useState(
    currentPatient?.clinical_note || '',
  );
  const [demo, setDemo] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open && currentPatient?.clinical_note && !clinicalContext) {
      setClinicalContext(currentPatient.clinical_note);
    }
  }, [open, currentPatient, clinicalContext]);

  useEffect(() => {
    if (!open) setCopied(false);
  }, [open]);

  const handleGenerate = async (e) => {
    e?.preventDefault?.();
    try {
      await generatePriorAuth({
        procedureCode,
        payer,
        encounterId: currentPatient?.id,
        clinicalContext,
        demo,
      });
    } catch (err) {
      // Error surfaces via the priorAuthError selector below.
    }
  };

  const handleCopyLetter = async () => {
    const text = priorAuthDraft?.draft_letter || '';
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error('Clipboard write failed', err);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose?.();
          }}
        >
          <motion.div
            initial={{ scale: 0.96, y: 16, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.96, y: 16, opacity: 0 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="relative w-full max-w-3xl max-h-[90vh] overflow-hidden rounded-3xl border border-white/10 bg-slate-900/95 shadow-2xl flex flex-col"
            role="dialog"
            aria-modal="true"
            aria-label="Generate prior authorization draft"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 p-6 border-b border-white/5">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-100">
                    Generate Prior-Authorization Draft
                  </h2>
                  <p className="text-xs text-slate-500 mt-1 max-w-md">
                    Buddi drafts a payer-ready letter from the clinical note.
                    The clinician reviews and submits — Buddi never auto-files.
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-lg text-slate-500 hover:bg-white/5 hover:text-slate-200 transition-colors"
                aria-label="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <form className="grid grid-cols-1 md:grid-cols-2 gap-4" onSubmit={handleGenerate}>
                <div>
                  <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                    Procedure / CPT code
                  </label>
                  <input
                    type="text"
                    value={procedureCode}
                    onChange={(e) => setProcedureCode(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="CPT-99213"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                    Payer
                  </label>
                  <input
                    type="text"
                    value={payer}
                    onChange={(e) => setPayer(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Medicare"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                    Clinical context (will be wrapped in `&lt;clinical_context&gt;` tags)
                  </label>
                  <textarea
                    value={clinicalContext}
                    onChange={(e) => setClinicalContext(e.target.value)}
                    rows={4}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                    placeholder="Paste the encounter note here..."
                  />
                </div>
                <div className="md:col-span-2 flex items-center justify-between flex-wrap gap-3">
                  <label className="flex items-center gap-2 text-xs text-slate-400 select-none">
                    <input
                      type="checkbox"
                      checked={demo}
                      onChange={(e) => setDemo(e.target.checked)}
                      className="w-4 h-4 rounded border-white/20 bg-white/5 text-indigo-500 focus:ring-indigo-500"
                    />
                    <span>
                      Use deterministic demo draft (skip live LLM call)
                    </span>
                  </label>
                  <button
                    type="submit"
                    disabled={isPriorAuthLoading || !procedureCode}
                    className="btn-primary px-4 py-2 rounded-lg text-xs font-bold flex items-center disabled:opacity-50"
                  >
                    {isPriorAuthLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Drafting…
                      </>
                    ) : (
                      <>
                        <FileText className="w-4 h-4 mr-2" />
                        Generate draft
                      </>
                    )}
                  </button>
                </div>
              </form>

              {/* Error */}
              {priorAuthError && (
                <div className="flex items-start gap-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
                  <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>{priorAuthError}</span>
                </div>
              )}

              {/* Draft output */}
              {priorAuthDraft && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold uppercase tracking-widest">
                      <CheckCircle2 className="w-4 h-4" />
                      Draft ready ·{' '}
                      <span className="text-slate-400 font-normal normal-case">
                        {priorAuthDraft.demo
                          ? 'deterministic demo'
                          : 'live agent'}
                      </span>
                    </div>
                    {priorAuthDraft.audit_hash && (
                      <span className="text-[10px] font-mono text-slate-500" title={priorAuthDraft.audit_hash}>
                        audit: {priorAuthDraft.audit_hash.slice(0, 12)}…
                      </span>
                    )}
                  </div>

                  <div className="rounded-2xl bg-white/5 border border-white/10 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                        Draft letter (clinician must review before sending)
                      </span>
                      <button
                        type="button"
                        onClick={handleCopyLetter}
                        className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 flex items-center"
                      >
                        {copied ? (
                          <>
                            <ClipboardCheck className="w-3 h-3 mr-1" />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3 mr-1" />
                            Copy
                          </>
                        )}
                      </button>
                    </div>
                    <pre className="whitespace-pre-wrap text-xs text-slate-300 leading-relaxed font-sans">
                      {priorAuthDraft.draft_letter}
                    </pre>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="rounded-2xl bg-white/5 border border-white/10 p-4">
                      <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                        Supporting codes
                      </h3>
                      <div className="flex flex-wrap gap-2">
                        {(priorAuthDraft.supporting_codes || []).map((code) => (
                          <span
                            key={code}
                            className="px-2 py-1 rounded-md text-[11px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20"
                          >
                            {code}
                          </span>
                        ))}
                        {(!priorAuthDraft.supporting_codes ||
                          priorAuthDraft.supporting_codes.length === 0) && (
                          <span className="text-xs text-slate-500 italic">
                            (none cited)
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="rounded-2xl bg-white/5 border border-white/10 p-4">
                      <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                        Payer rationale
                      </h3>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {priorAuthDraft.payer_rationale || '(no rationale generated)'}
                      </p>
                    </div>
                  </div>

                  {priorAuthDraft.evidence_snippets &&
                    priorAuthDraft.evidence_snippets.length > 0 && (
                      <div className="rounded-2xl bg-white/5 border border-white/10 p-4">
                        <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                          Evidence quotes from the chart
                        </h3>
                        <ul className="space-y-2">
                          {priorAuthDraft.evidence_snippets.map((snip, idx) => (
                            <li
                              key={idx}
                              className="text-xs text-slate-300 italic border-l-2 border-indigo-500/40 pl-3"
                            >
                              &ldquo;{snip.quote}&rdquo;
                              <span className="not-italic text-slate-500 ml-2">
                                — {snip.source}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  {priorAuthDraft.missing_information &&
                    priorAuthDraft.missing_information.length > 0 && (
                      <div className="rounded-2xl bg-amber-500/5 border border-amber-500/20 p-4">
                        <div className="flex items-center gap-2 text-amber-400 text-[10px] font-bold uppercase tracking-widest mb-2">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          Clinician must add before sending
                        </div>
                        <ul className="list-disc list-inside text-xs text-slate-300 space-y-1">
                          {priorAuthDraft.missing_information.map((item, idx) => (
                            <li key={idx}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                </div>
              )}
            </div>

            {/* Footer — non-removable safety reminder */}
            <div className="border-t border-white/5 p-4 flex items-center justify-between bg-slate-900/80">
              <span className="text-[10px] text-slate-500 uppercase tracking-widest">
                Shadow-mode product · No automated submission
              </span>
              <button
                onClick={onClose}
                className="btn-secondary px-4 py-2 rounded-lg text-xs font-bold"
              >
                Close
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default PriorAuthModal;
