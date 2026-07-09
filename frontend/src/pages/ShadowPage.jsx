import React, { useMemo, useState } from 'react';
import {
  ClipboardList,
  DollarSign,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  FileText,
  ChevronDown,
  ChevronRight,
  Search,
  X,
  Eye,
  EyeOff,
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
  const shadowProgress = useStore((state) => state.shadowProgress);

  const [selectedCode, setSelectedCode] = useState(null);
  const [queueFilter, setQueueFilter] = useState('all');
  const [showManualCheck, setShowManualCheck] = useState(false);
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
    setShowManualCheck(false);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    await runShadowAudit({
      note,
      billedCodes: parsedCodes,
      patientId: currentPatient.id,
    });
    setShowManualCheck(false);
  };

  const handleSelectCode = (code) => {
    if (selectedCode?.code === code.code) {
      setSelectedCode(null);
    } else {
      setSelectedCode(code);
    }
  };

  // Build queue items from shadowResult
  const queueItems = useMemo(() => {
    const codes = shadowResult?.identified_codes || [];
    const abstainedItems = shadowResult?.abstained_codes || [];
    return { codes, abstainedItems };
  }, [shadowResult]);

  const filteredCodes = useMemo(() => {
    if (queueFilter === 'needs_review') {
      return queueItems.codes.filter(
        (c) => !c.review_status || c.review_status === 'human_review_required'
      );
    }
    if (queueFilter === 'reviewed') {
      return queueItems.codes.filter((c) => c.review_status === 'verified');
    }
    return queueItems.codes;
  }, [queueItems.codes, queueFilter]);

  const totalValue = useMemo(
    () => queueItems.codes.reduce((sum, c) => sum + (c.est_value || 0), 0),
    [queueItems.codes]
  );

  const statusLabel = (code) => {
    const status = code.review_status || 'human_review_required';
    switch (status) {
      case 'verified':
        return { text: 'Verified', badge: 'badge-positive' };
      case 'human_review_required':
        return { text: 'Needs coder review', badge: 'badge-caution' };
      default:
        return { text: status, badge: 'badge-neutral' };
    }
  };

  const confidenceLabel = (confidence) => {
    const pct = Math.round((confidence || 0) * 100);
    if (pct >= 85) return { label: 'High confidence', pct };
    if (pct >= 70) return { label: 'Medium confidence', pct };
    return { label: 'Low confidence', pct };
  };

  // Dismiss reasons
  const dismissReasons = [
    'Not supported by documentation',
    'Already captured in another code',
    'Incorrect code for diagnosis',
    'Not clinically relevant',
  ];
  const [activeDismiss, setActiveDismiss] = useState(null);
  const [dismissReason, setDismissReason] = useState('');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--color-ink)' }}>
            Review Queue
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-secondary)' }}>
            Buddee reviews encounters in the background and suggests codes.
            Nothing is billed or submitted without your team's approval.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowManualCheck(!showManualCheck)}
            className="btn-secondary btn-sm"
          >
            <FileText size={16} />
            {showManualCheck ? 'Back to queue' : 'Manual check'}
          </button>
          <button
            onClick={handleTrySamplePatient}
            disabled={isShadowLoading}
            className="btn-primary btn-sm"
          >
            {isShadowLoading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <ClipboardList size={16} />
            )}
            Sample patient
          </button>
        </div>
      </div>

      {showManualCheck ? (
        /* Manual check tab — paste-a-note form */
        <div className="card">
          <div className="card-header">
            <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
              Manual audit check
            </h2>
          </div>
          <form onSubmit={handleSubmit} className="card-body space-y-5">
            <div>
              <label className="label" htmlFor="patient-display">
                Patient
              </label>
              <div
                className="input cursor-default"
                id="patient-display"
              >
                <span className="font-medium">{currentPatient.name}</span>
                {currentPatient.demo && (
                  <span className="badge-neutral ml-2">Sample — synthetic data</span>
                )}
              </div>
            </div>

            <div>
              <label className="label" htmlFor="clinical-note">
                Clinical note
              </label>
              <textarea
                id="clinical-note"
                value={note}
                onChange={(event) => setNoteOverride(event.target.value)}
                rows={12}
                className="input !rounded-card resize-y font-mono text-sm"
                placeholder="Paste encounter note..."
              />
            </div>

            <div>
              <label className="label" htmlFor="billed-codes">
                Already billed codes
              </label>
              <input
                id="billed-codes"
                value={billedCodes}
                onChange={(event) => setBilledCodesOverride(event.target.value)}
                className="input"
                placeholder="E11.9, I10"
              />
            </div>

            {shadowError && (
              <div className="flex items-start gap-2 text-sm p-3 rounded-control" style={{ backgroundColor: 'var(--color-risk-bg)', color: 'var(--color-risk, #BE123C)' }}>
                <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                {shadowError}
              </div>
            )}

            <button
              type="submit"
              disabled={isShadowLoading || !note.trim()}
              className="btn-primary"
            >
              {isShadowLoading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Running analysis…
                </>
              ) : (
                <>
                  <ClipboardList size={16} />
                  Run audit
                </>
              )}
            </button>
          </form>
        </div>
      ) : (
        /* Two-pane queue view */
        <div className="flex gap-0" style={{ minHeight: 'calc(100vh - 280px)' }}>
          {/* Left pane — queue list */}
          <div className="w-[420px] flex-shrink-0 card flex flex-col overflow-hidden">
            {/* Queue header */}
            <div className="card-header">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
                  Encounters
                </h2>
                <span className="text-xs" style={{ color: 'var(--color-muted)' }}>
                  {filteredCodes.length > 0
                    ? `${filteredCodes.length} suggestion${filteredCodes.length !== 1 ? 's' : ''}`
                    : ''}
                </span>
              </div>

              {/* Filter pills */}
              <div className="flex gap-2">
                {['all', 'needs_review', 'reviewed'].map((f) => (
                  <button
                    key={f}
                    onClick={() => setQueueFilter(f)}
                    className={`btn-xs rounded-control transition-colors ${
                      queueFilter === f
                        ? 'btn-primary'
                        : 'btn-ghost'
                    }`}
                  >
                    {f === 'all'
                      ? 'All'
                      : f === 'needs_review'
                      ? 'Needs review'
                      : 'Reviewed'}
                  </button>
                ))}
              </div>
            </div>

            {/* Queue items */}
            <div className="flex-1 overflow-y-auto">
              {filteredCodes.length === 0 && !isShadowLoading && (
                <div className="p-5 text-center">
                  <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
                    {queueItems.codes.length === 0
                      ? 'No audit results yet. Try the sample patient or submit a note.'
                      : 'No suggestions match the selected filter.'}
                  </p>
                </div>
              )}

              {isShadowLoading && shadowProgress && (
                <div className="p-5 flex items-center gap-3">
                  <Loader2 size={16} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
                  <span className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                    {shadowProgress}
                  </span>
                </div>
              )}

              {filteredCodes.map((code) => {
                const status = statusLabel(code);
                const isSelected = selectedCode?.code === code.code &&
                  selectedCode?.description === code.description;
                return (
                  <button
                    key={`${code.code}-${code.description}`}
                    onClick={() => handleSelectCode(code)}
                    className={`queue-row w-full text-left ${
                      isSelected ? 'selected' : ''
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate" style={{ color: 'var(--color-ink)' }}>
                        {code.code}
                      </p>
                      <p className="text-xs truncate mt-0.5" style={{ color: 'var(--color-secondary)' }}>
                        {code.description}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                        {formatCurrency(code.est_value)}
                      </p>
                    </div>
                    <div className="ml-2 flex-shrink-0">
                      <span className={status.badge}>{status.text}</span>
                    </div>
                  </button>
                );
              })}

              {queueItems.abstainedItems.length > 0 && (
                <details className="border-t" style={{ borderColor: 'var(--color-border)' }}>
                  <summary
                    className="queue-row cursor-pointer text-sm font-medium"
                    style={{ color: 'var(--color-secondary)' }}
                  >
                    Buddee abstained on {queueItems.abstainedItems.length} item{queueItems.abstainedItems.length !== 1 ? 's' : ''}
                  </summary>
                  <div className="px-4 py-3 space-y-2 text-sm" style={{ color: 'var(--color-muted)' }}>
                    {queueItems.abstainedItems.map((item, i) => (
                      <p key={i} className="text-xs">
                        <span className="font-medium">{item.code || 'Item'}:</span>{' '}
                        {item.abstain_reason || 'Confidence below threshold'}
                      </p>
                    ))}
                  </div>
                </details>
              )}
            </div>

            {/* Queue footer */}
            <div
              className="card-header flex items-center justify-between"
            >
              <span className="text-sm font-medium" style={{ color: 'var(--color-secondary)' }}>
                Total identified value
              </span>
              <span className="text-base font-bold" style={{ color: 'var(--color-ink)' }}>
                {formatCurrency(totalValue)}
              </span>
            </div>
          </div>

          {/* Right pane — encounter detail */}
          <div
            className="flex-1 ml-4 card overflow-y-auto"
            style={{ minHeight: '400px' }}
          >
            {isShadowLoading && !shadowProgress && (
              <div className="card-body flex items-center justify-center" style={{ minHeight: '300px' }}>
                <div className="text-center">
                  <Loader2 size={24} className="animate-spin mx-auto mb-3" style={{ color: 'var(--color-primary)' }} />
                  <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                    Running analysis…
                  </p>
                </div>
              </div>
            )}

            {selectedCode && !isShadowLoading && (
              <div>
                {/* Encounteer header */}
                <div className="card-header">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
                        {currentPatient.name}
                      </p>
                      <p className="text-sm mt-0.5" style={{ color: 'var(--color-secondary)' }}>
                        MRN {currentPatient.id}
                        <span className="mx-2" style={{ color: 'var(--color-border)' }}>·</span>
                        {currentPatient.age || '67'}y
                        <span className="mx-2" style={{ color: 'var(--color-border)' }}>·</span>
                        {currentPatient.gender || 'Male'}
                      </p>
                    </div>
                    {currentPatient.demo && (
                      <span className="badge-neutral">Sample — synthetic data</span>
                    )}
                  </div>
                </div>

                {/* Suggested code card */}
                <div className="card-body space-y-5">
                  <div
                    className="rounded-control border p-4"
                    style={{
                      borderColor: 'var(--color-border)',
                      backgroundColor: 'var(--color-surface)',
                    }}
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <p className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
                          {selectedCode.code}
                        </p>
                        <p className="text-sm mt-0.5" style={{ color: 'var(--color-secondary)' }}>
                          {selectedCode.description}
                        </p>
                      </div>
                      <p className="text-xl font-bold" style={{ color: '#047857' }}>
                        {formatCurrency(selectedCode.est_value)}
                      </p>
                    </div>

                    {/* Confidence band */}
                    <div className="flex items-center gap-2 mb-4">
                      {(() => {
                        const cl = confidenceLabel(selectedCode.confidence);
                        const dotColor =
                          cl.pct >= 85 ? '#047857' :
                          cl.pct >= 70 ? '#B45309' : '#BE123C';
                        return (
                          <>
                            <span className="status-dot" style={{ backgroundColor: dotColor }} />
                            <span className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
                              {cl.label}
                            </span>
                            <span className="text-sm" style={{ color: 'var(--color-muted)' }}>
                              · {cl.pct}%
                            </span>
                          </>
                        );
                      })()}
                    </div>

                    {/* Evidence quote */}
                    {selectedCode.evidence_quote && (
                      <div
                        className="rounded-control p-3 mb-4"
                        style={{ backgroundColor: 'var(--color-fill)' }}
                      >
                        <p className="text-xs font-medium mb-1" style={{ color: 'var(--color-secondary)' }}>
                          From the clinical note
                        </p>
                        <p className="text-sm leading-relaxed" style={{ color: 'var(--color-ink)' }}>
                          &ldquo;{selectedCode.evidence_quote}&rdquo;
                        </p>
                      </div>
                    )}

                    {/* Justification */}
                    {selectedCode.justification && (
                      <p className="text-sm mb-4 leading-relaxed" style={{ color: 'var(--color-secondary)' }}>
                        {selectedCode.justification}
                      </p>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-3 pt-3 border-t" style={{ borderColor: 'var(--color-border)' }}>
                      <button className="btn-primary btn-sm">
                        <CheckCircle2 size={16} />
                        Accept
                      </button>
                      <div className="relative">
                        <button
                          onClick={() =>
                            setActiveDismiss(
                              activeDismiss === selectedCode.code ? null : selectedCode.code
                            )
                          }
                          className="btn-secondary btn-sm"
                        >
                          <XCircle size={16} />
                          Dismiss
                        </button>
                        {activeDismiss === selectedCode.code && (
                          <div
                            className="absolute left-0 top-full mt-1 w-64 rounded-card border p-3 z-10"
                            style={{
                              backgroundColor: 'var(--color-surface)',
                              borderColor: 'var(--color-border)',
                              boxShadow: '0 4px 12px rgba(21,48,45,0.12)',
                            }}
                          >
                            <p className="text-xs font-medium mb-2" style={{ color: 'var(--color-secondary)' }}>
                              Reason for dismissal
                            </p>
                            <div className="space-y-1">
                              {dismissReasons.map((r) => (
                                <button
                                  key={r}
                                  onClick={() => setDismissReason(r)}
                                  className="w-full text-left px-2 py-1.5 rounded text-xs transition-colors"
                                  style={{
                                    backgroundColor:
                                      dismissReason === r ? 'var(--color-fill)' : 'transparent',
                                    color: 'var(--color-ink)',
                                  }}
                                >
                                  {r}
                                </button>
                              ))}
                            </div>
                            {dismissReason && (
                              <button
                                className="btn-primary btn-xs mt-2 w-full"
                                onClick={() => {
                                  setActiveDismiss(null);
                                  setDismissReason('');
                                }}
                              >
                                Confirm dismissal
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Citations */}
                  {shadowResult?.citations && shadowResult.citations.length > 0 && (
                    <div>
                      <p className="text-xs font-medium mb-2" style={{ color: 'var(--color-secondary)' }}>
                        Sources
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {shadowResult.citations.map((cite, i) => (
                          <span
                            key={i}
                            className="badge-neutral text-xs"
                          >
                            {cite}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Footer note */}
                <div
                  className="card-header text-xs"
                  style={{ color: 'var(--color-muted)' }}
                >
                  Accepted codes are exported for your billing workflow — Buddee never submits claims.
                </div>
              </div>
            )}

            {!selectedCode && !isShadowLoading && (
              <div className="card-body flex items-center justify-center" style={{ minHeight: '300px' }}>
                <div className="text-center max-w-sm">
                  <ClipboardList
                    size={32}
                    className="mx-auto mb-3"
                    style={{ color: 'var(--color-muted)' }}
                  />
                  <p className="text-sm font-medium" style={{ color: 'var(--color-secondary)' }}>
                    {filteredCodes.length > 0
                      ? 'Select a suggestion to review'
                      : 'No results to review'}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-muted)' }}>
                    {queueItems.codes.length === 0
                      ? 'Run an audit or try the sample patient to populate the queue.'
                      : 'Adjust the filter to see more results.'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Shadow result summary — only when there are results */}
      {shadowResult?.summary && !showManualCheck && !isShadowLoading && (
        <div className="card">
          <div className="card-body flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm leading-relaxed" style={{ color: 'var(--color-secondary)' }}>
                {shadowResult.summary}
              </p>
              {shadowResult.audit_hash && (
                <p className="text-xs mt-2 font-mono" style={{ color: 'var(--color-muted)' }}>
                  Record ID: {shadowResult.audit_hash.slice(0, 16)}…
                </p>
              )}
            </div>
            {shadowResult.demo && (
              <span className="badge-neutral flex-shrink-0">Sample — synthetic data</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ShadowPage;
