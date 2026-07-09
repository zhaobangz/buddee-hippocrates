import React, { useState } from 'react';
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
 * `generatePriorAuth` action. The component never auto-submits to a payer
 * — that is a structural property of the product.
 */
const PriorAuthModal = ({ open, onClose }) => {
  const generatePriorAuth = useStore((s) => s.generatePriorAuth);
  const priorAuthDraft = useStore((s) => s.priorAuthDraft);
  const isPriorAuthLoading = useStore((s) => s.isPriorAuthLoading);
  const priorAuthError = useStore((s) => s.priorAuthError);
  const currentPatient = useStore((s) => s.currentPatient);

  const [procedureCode, setProcedureCode] = useState('CPT-99213');
  const [payer, setPayer] = useState('Medicare');
  const [clinicalContextOverride, setClinicalContextOverride] = useState(null);
  const [demo, setDemo] = useState(true);
  const [copied, setCopied] = useState(false);

  const clinicalContext =
    clinicalContextOverride ?? currentPatient?.clinical_note ?? '';

  const handleClose = () => {
    setCopied(false);
    onClose?.();
  };

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
    } catch {
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

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div
        className="relative w-full max-w-3xl max-h-[90vh] overflow-hidden rounded-card border flex flex-col"
        style={{
          backgroundColor: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
        }}
        role="dialog"
        aria-modal="true"
        aria-label="Generate prior authorization draft"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-5 border-b" style={{ borderColor: 'var(--color-border)' }}>
          <div className="flex items-start gap-3">
            <div
              className="p-2 rounded-control"
              style={{ backgroundColor: 'var(--color-fill)' }}
            >
              <FileText size={20} style={{ color: 'var(--color-primary)' }} />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
                Generate prior-authorization draft
              </h2>
              <p className="text-sm mt-1" style={{ color: 'var(--color-secondary)' }}>
                Buddee drafts a payer-ready letter from the clinical note.
                Your team reviews and submits — Buddee never auto-files.
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="btn-ghost btn-sm !min-h-[32px] !min-w-[32px] !p-1 rounded-control"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <form className="grid grid-cols-1 md:grid-cols-2 gap-4" onSubmit={handleGenerate}>
            <div>
              <label className="label" htmlFor="pa-procedure-code">
                Procedure / CPT code
              </label>
              <input
                id="pa-procedure-code"
                type="text"
                value={procedureCode}
                onChange={(e) => setProcedureCode(e.target.value)}
                className="input"
                placeholder="CPT-99213"
              />
            </div>
            <div>
              <label className="label" htmlFor="pa-payer">
                Payer
              </label>
              <input
                id="pa-payer"
                type="text"
                value={payer}
                onChange={(e) => setPayer(e.target.value)}
                className="input"
                placeholder="Medicare"
              />
            </div>
            <div className="md:col-span-2">
              <label className="label" htmlFor="pa-clinical-context">
                Clinical context
              </label>
              <textarea
                id="pa-clinical-context"
                value={clinicalContext}
                onChange={(e) => setClinicalContextOverride(e.target.value)}
                rows={4}
                className="input font-mono text-sm resize-y"
                placeholder="Paste the encounter note here..."
              />
            </div>
            <div className="md:col-span-2 flex items-center justify-between flex-wrap gap-3">
              <label className="flex items-center gap-2 text-sm select-none" style={{ color: 'var(--color-secondary)' }}>
                <input
                  type="checkbox"
                  checked={demo}
                  onChange={(e) => setDemo(e.target.checked)}
                  className="w-4 h-4 rounded"
                  style={{ accentColor: 'var(--color-primary)' }}
                />
                Use deterministic demo draft (skip live LLM call)
              </label>
              <button
                type="submit"
                disabled={isPriorAuthLoading || !procedureCode}
                className="btn-primary btn-sm"
              >
                {isPriorAuthLoading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Drafting…
                  </>
                ) : (
                  <>
                    <FileText size={16} />
                    Generate draft
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Error */}
          {priorAuthError && (
            <div
              className="flex items-start gap-3 p-3 rounded-card text-sm"
              style={{
                backgroundColor: 'var(--color-risk-bg, #FDECEF)',
                color: '#BE123C',
              }}
            >
              <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
              <span>{priorAuthError}</span>
            </div>
          )}

          {/* Draft output */}
          {priorAuthDraft && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm" style={{ color: '#047857' }}>
                  <CheckCircle2 size={16} />
                  Draft ready
                  <span style={{ color: 'var(--color-muted)' }}>
                    · {priorAuthDraft.demo ? 'deterministic demo' : 'live agent'}
                  </span>
                </div>
                {priorAuthDraft.audit_hash && (
                  <span className="text-xs font-mono" style={{ color: 'var(--color-muted)' }} title={priorAuthDraft.audit_hash}>
                    Record: {priorAuthDraft.audit_hash.slice(0, 12)}…
                  </span>
                )}
              </div>

              <div
                className="rounded-card border p-4 space-y-3"
                style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-fill)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium" style={{ color: 'var(--color-secondary)' }}>
                    Draft letter (review before sending)
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyLetter}
                    className="btn-ghost btn-xs"
                  >
                    {copied ? (
                      <>
                        <ClipboardCheck size={12} />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy size={12} />
                        Copy
                      </>
                    )}
                  </button>
                </div>
                <pre
                  className="whitespace-pre-wrap text-sm leading-relaxed font-sans"
                  style={{ color: 'var(--color-ink)' }}
                >
                  {priorAuthDraft.draft_letter}
                </pre>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div
                  className="rounded-card border p-4"
                  style={{ borderColor: 'var(--color-border)' }}
                >
                  <h3 className="text-xs font-medium mb-2" style={{ color: 'var(--color-secondary)' }}>
                    Supporting codes
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {(priorAuthDraft.supporting_codes || []).map((code) => (
                      <span
                        key={code}
                        className="px-2 py-1 rounded text-xs font-mono"
                        style={{
                          backgroundColor: 'var(--color-fill)',
                          color: 'var(--color-ink)',
                          border: '1px solid var(--color-border)',
                        }}
                      >
                        {code}
                      </span>
                    ))}
                    {(!priorAuthDraft.supporting_codes ||
                      priorAuthDraft.supporting_codes.length === 0) && (
                      <span className="text-xs" style={{ color: 'var(--color-muted)' }}>
                        (none cited)
                      </span>
                    )}
                  </div>
                </div>
                <div
                  className="rounded-card border p-4"
                  style={{ borderColor: 'var(--color-border)' }}
                >
                  <h3 className="text-xs font-medium mb-2" style={{ color: 'var(--color-secondary)' }}>
                    Payer rationale
                  </h3>
                  <p className="text-sm leading-relaxed" style={{ color: 'var(--color-secondary)' }}>
                    {priorAuthDraft.payer_rationale || '(no rationale generated)'}
                  </p>
                </div>
              </div>

              {priorAuthDraft.evidence_snippets &&
                priorAuthDraft.evidence_snippets.length > 0 && (
                  <div
                    className="rounded-card border p-4"
                    style={{ borderColor: 'var(--color-border)' }}
                  >
                    <h3 className="text-xs font-medium mb-2" style={{ color: 'var(--color-secondary)' }}>
                      Evidence quotes from the chart
                    </h3>
                    <ul className="space-y-2">
                      {priorAuthDraft.evidence_snippets.map((snip, idx) => (
                        <li
                          key={idx}
                          className="text-sm italic border-l-2 pl-3"
                          style={{
                            color: 'var(--color-secondary)',
                            borderColor: 'var(--color-primary)',
                          }}
                        >
                          &ldquo;{snip.quote}&rdquo;
                          <span className="not-italic ml-2" style={{ color: 'var(--color-muted)' }}>
                            — {snip.source}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {priorAuthDraft.missing_information &&
                priorAuthDraft.missing_information.length > 0 && (
                  <div
                    className="rounded-card border p-4"
                    style={{
                      borderColor: 'rgba(180, 83, 9, 0.2)',
                      backgroundColor: 'var(--color-caution-bg, #FEF3E2)',
                    }}
                  >
                    <div className="flex items-center gap-2 text-sm font-medium mb-2" style={{ color: '#B45309' }}>
                      <AlertTriangle size={14} />
                      Clinician must add before sending
                    </div>
                    <ul className="list-disc list-inside text-sm space-y-1" style={{ color: 'var(--color-secondary)' }}>
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
        <div
          className="border-t p-4 flex items-center justify-between"
          style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-fill)' }}
        >
          <span className="text-xs" style={{ color: 'var(--color-muted)' }}>
            Shadow-mode product · No automated submission
          </span>
          <button onClick={handleClose} className="btn-secondary btn-sm">
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default PriorAuthModal;
