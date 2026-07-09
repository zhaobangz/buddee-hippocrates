import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  Download,
  Lock,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Info,
  CheckCircle2,
  Copy,
} from 'lucide-react';
import useStore from '../store/useStore';

const truncate = (value, length = 18) => {
  if (!value) return '—';
  return value.length > length ? `${value.slice(0, length)}…` : value;
};

const AuditPage = () => {
  const auditEvents = useStore((state) => state.auditEvents);
  const auditVerification = useStore((state) => state.auditVerification);
  const fetchAuditLogs = useStore((state) => state.fetchAuditLogs);
  const verifyAuditTrail = useStore((state) => state.verifyAuditTrail);
  const [expandedRow, setExpandedRow] = useState(null);
  const [verifyMsg, setVerifyMsg] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [isVerifying, setIsVerifying] = useState(false);

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  const handleVerify = async () => {
    setIsVerifying(true);
    const result = await verifyAuditTrail();
    setIsVerifying(false);
    if (!result) {
      setVerifyMsg({ tone: 'error', text: 'Verification request failed.' });
      return;
    }
    if (result.verified) {
      setVerifyMsg({
        tone: 'ok',
        text: `Integrity verified across ${result.events_checked} record(s).`,
      });
    } else {
      setVerifyMsg({
        tone: 'error',
        text: `Verification failed${result.broken_at ? ` at record ${result.broken_at}` : ''}. Contact support.`,
      });
    }
    setTimeout(() => setVerifyMsg(null), 8000);
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(auditEvents, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `buddee-health-audit-trail-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(text.slice(0, 12));
      setTimeout(() => setCopiedId(null), 1500);
    } catch {
      // fallback
    }
  };

  // Build persistent status
  const eventsChecked = auditVerification?.events_checked || auditEvents.length;

  const eventActionLabel = (event) => {
    const action = event.event_type || event.action || 'Unknown';
    // Translate if needed
    if (action === 'shadow_audit_completed') return 'Coding review completed';
    if (action === 'suggestion_accepted') return 'Suggestion accepted';
    if (action === 'suggestion_dismissed') return 'Suggestion dismissed';
    if (action === 'prior_auth_generated') return 'Prior auth draft generated';
    return action.replace(/_/g, ' ');
  };

  const formatActor = (event) => {
    const actor = event.actor || event.user || 'system';
    return actor;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--color-ink)' }}>
            Audit trail
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-secondary)' }}>
            A permanent, verifiable record of every review.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleExport} className="btn-secondary btn-sm">
            <Download size={16} />
            Export (JSON)
          </button>
          <button
            onClick={handleVerify}
            disabled={isVerifying}
            className="btn-secondary btn-sm"
          >
            <Lock size={16} />
            {isVerifying ? 'Verifying…' : 'Verify integrity'}
          </button>
        </div>
      </div>

      {/* Persistent status banner */}
      {(verifyMsg || eventsChecked > 0) && (
        <div
          className={`flex items-center gap-3 px-4 py-3 rounded-card border text-sm ${
            verifyMsg?.tone === 'error'
              ? 'border-[#BE123C]'
              : 'border-[#047857]'
          }`}
          style={{
            backgroundColor: verifyMsg?.tone === 'error'
              ? 'var(--color-risk-bg, #FDECEF)'
              : 'var(--color-positive-bg, #ECFDF3)',
            color: verifyMsg?.tone === 'error' ? '#BE123C' : '#047857',
          }}
          role="status"
          aria-live="polite"
        >
          {verifyMsg?.tone === 'error' || (!verifyMsg && auditVerification?.verified === false) ? (
            <AlertTriangle size={18} />
          ) : (
            <CheckCircle2 size={18} />
          )}
          <span>
            {verifyMsg
              ? verifyMsg.text
              : auditVerification?.verified === false
              ? 'Verification failed. Contact support.'
              : `Integrity verified across ${eventsChecked} record${eventsChecked !== 1 ? 's' : ''}.`}
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Event table */}
        <div className="lg:col-span-2 card overflow-hidden">
          <div className="card-body !p-0">
            {auditEvents.length === 0 ? (
              <div className="p-6 text-center">
                <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
                  No audit events recorded yet.
                </p>
              </div>
            ) : (
              <table className="w-full" role="table">
                <thead>
                  <tr
                    className="text-xs font-medium text-left"
                    style={{ color: 'var(--color-muted)', borderBottom: '1px solid var(--color-border)' }}
                  >
                    <th className="px-5 py-3 font-medium">Event</th>
                    <th className="px-5 py-3 font-medium">Actor</th>
                    <th className="px-5 py-3 font-medium">Patient / Encounter</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {auditEvents.map((event) => {
                    const isExpanded = expandedRow === event.id || expandedRow === event.event_id;
                    return (
                      <React.Fragment key={event.id || event.event_id}>
                        <tr
                          className="cursor-pointer transition-colors text-sm"
                          style={{
                            color: 'var(--color-ink)',
                            borderBottom: '1px solid var(--color-border)',
                          }}
                          onMouseEnter={(e) => {
                            if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--color-fill)';
                          }}
                          onMouseLeave={(e) => {
                            if (!isExpanded) e.currentTarget.style.backgroundColor = 'transparent';
                          }}
                          onClick={() => {
                            const id = event.id || event.event_id;
                            setExpandedRow(isExpanded ? null : id);
                          }}
                        >
                          <td className="px-5 py-3">
                            <div>
                              <p className="font-medium" style={{ color: 'var(--color-ink)' }}>
                                {eventActionLabel(event)}
                              </p>
                              <p className="text-xs mt-0.5" style={{ color: 'var(--color-muted)' }}>
                                {event.timestamp ? new Date(event.timestamp).toLocaleString() : event.timestamp}
                              </p>
                            </div>
                          </td>
                          <td className="px-5 py-3 text-sm" style={{ color: 'var(--color-secondary)' }}>
                            {formatActor(event)}
                          </td>
                          <td className="px-5 py-3">
                            <span className="font-mono text-xs" style={{ color: 'var(--color-secondary)' }}>
                              {event.patient_id || event.payload?.patient_id || '—'}
                            </span>
                          </td>
                          <td className="px-5 py-3">
                            {(() => {
                              const vs = event.verification_status || 'verified';
                              if (vs.includes('broken') || vs.includes('mismatch')) {
                                return <span className="badge-risk">Needs review</span>;
                              }
                              if (vs === 'verified') {
                                return <span className="badge-positive">Verified</span>;
                              }
                              return <span className="badge-neutral">Not yet verified</span>;
                            })()}
                          </td>
                          <td className="px-5 py-3">
                            {isExpanded ? (
                              <ChevronDown size={16} style={{ color: 'var(--color-muted)' }} />
                            ) : (
                              <ChevronRight size={16} style={{ color: 'var(--color-muted)' }} />
                            )}
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr
                            style={{
                              borderBottom: '1px solid var(--color-border)',
                              backgroundColor: 'var(--color-fill)',
                            }}
                          >
                            <td colSpan={5} className="px-5 py-4">
                              <div className="space-y-3">
                                {/* Record ID */}
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-medium" style={{ color: 'var(--color-secondary)' }}>
                                    Record ID
                                  </span>
                                  <code
                                    className="text-xs font-mono px-2 py-0.5 rounded"
                                    style={{
                                      backgroundColor: 'var(--color-surface)',
                                      border: '1px solid var(--color-border)',
                                      color: 'var(--color-ink)',
                                    }}
                                  >
                                    {event.current_hash || event.cryptographic_hash || '—'}
                                  </code>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleCopy(event.current_hash || event.cryptographic_hash || '');
                                    }}
                                    className="btn-ghost btn-xs !min-h-[24px] !px-1"
                                    aria-label="Copy record ID"
                                  >
                                    {copiedId === (event.current_hash || '').slice(0, 12) ? (
                                      <CheckCircle2 size={12} style={{ color: '#047857' }} />
                                    ) : (
                                      <Copy size={12} />
                                    )}
                                  </button>
                                </div>

                                {/* Linked previous record */}
                                {event.previous_hash && (
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-medium" style={{ color: 'var(--color-secondary)' }}>
                                      Previous record
                                    </span>
                                    <code
                                      className="text-xs font-mono px-2 py-0.5 rounded"
                                      style={{
                                        backgroundColor: 'var(--color-surface)',
                                        border: '1px solid var(--color-border)',
                                        color: 'var(--color-ink)',
                                      }}
                                    >
                                      {truncate(event.previous_hash, 24)}
                                    </code>
                                  </div>
                                )}

                                {/* Revenue recovery event */}
                                {event.payload?.recovered_revenue !== undefined && (
                                  <p className="text-sm" style={{ color: '#047857' }}>
                                    Recovery event: ${Number(event.payload.recovered_revenue || 0).toLocaleString()}
                                  </p>
                                )}

                                {/* Summary / payload details */}
                                {event.payload?.summary && (
                                  <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                                    {event.payload.summary}
                                  </p>
                                )}

                                {/* Technical details disclosure */}
                                <details className="text-sm">
                                  <summary
                                    className="cursor-pointer text-xs font-medium"
                                    style={{ color: 'var(--color-muted)' }}
                                  >
                                    Technical details
                                  </summary>
                                  <div
                                    className="mt-2 p-3 rounded text-xs font-mono space-y-1 overflow-x-auto"
                                    style={{
                                      backgroundColor: 'var(--color-surface)',
                                      border: '1px solid var(--color-border)',
                                      color: 'var(--color-secondary)',
                                    }}
                                  >
                                    <p>Previous hash: {truncate(event.previous_hash || '—', 32)}</p>
                                    <p>Current hash: {truncate(event.current_hash || event.cryptographic_hash || '—', 32)}</p>
                                    {event.merkle_root && <p>Merkle root: {truncate(event.merkle_root, 32)}</p>}
                                    {event.sequence_number && <p>Sequence: {event.sequence_number}</p>}
                                  </div>
                                </details>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* How verification works */}
          <div className="card">
            <div className="card-body">
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-ink)' }}>
                How it works
              </h3>
              <div className="space-y-3 text-sm" style={{ color: 'var(--color-secondary)' }}>
                <p>
                  Every review is permanently recorded. Records are cryptographically
                  linked so any alteration is detectable.
                </p>
                <p>
                  Each record contains a cryptographic hash of the previous record,
                  forming a chain. The integrity of the entire chain can be verified
                  with a single check.
                </p>
                <p>
                  Daily snapshots are signed and stored in an immutable bucket for
                  long-term assurance.
                </p>
              </div>
              <details className="mt-4 text-sm">
                <summary
                  className="cursor-pointer text-xs font-medium"
                  style={{ color: 'var(--color-primary)' }}
                >
                  Technical details
                </summary>
                <div
                  className="mt-2 p-3 rounded text-xs font-mono space-y-1 overflow-x-auto"
                  style={{
                    backgroundColor: 'var(--color-fill)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-secondary)',
                  }}
                >
                  <p>Algorithm: SHA-256 hash chain</p>
                  <p>Signing: Ed25519 (Cloud KMS)</p>
                  <p>Daily root: Merkle tree with signed root</p>
                  <p>Storage: Object Lock (WORM) compliant bucket</p>
                </div>
              </details>
            </div>
          </div>

          {/* Compliance posture */}
          <div className="card">
            <div className="card-body">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--color-ink)' }}>
                <Info size={16} style={{ color: 'var(--color-muted)' }} />
                Compliance posture
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--color-secondary)' }}>
                Buddee Health is currently pre-certification. HIPAA, FedRAMP, and SOC 2
                Type II attestations are in scope but are not yet in effect. No
                compliance badges will be displayed until the corresponding audits
                have been completed and signed by an external QSA/3PAO.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuditPage;
