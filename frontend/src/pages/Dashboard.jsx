import React, { useEffect, useState } from 'react';
import {
  ClipboardList,
  DollarSign,
  TrendingUp,
  CheckCircle2,
  XCircle,
  Gauge,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Beaker,
  ArrowRight,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import useStore from '../store/useStore';
import SLOPanel from '../components/SLOPanel';

const formatCurrency = (value) =>
  Number(value || 0).toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });

const Dashboard = () => {
  const navigate = useNavigate();
  const loadDemoPatient = useStore((state) => state.loadDemoPatient);
  const runShadowAudit = useStore((state) => state.runShadowAudit);
  const fetchDashboardMetrics = useStore((state) => state.fetchDashboardMetrics);
  const shadowResult = useStore((state) => state.shadowResult);
  const metrics = useStore((state) => state.dashboardMetrics);
  const auditVerification = useStore((state) => state.auditVerification);
  const [sloOpen, setSloOpen] = useState(false);

  useEffect(() => {
    fetchDashboardMetrics();
    const intervalId = window.setInterval(fetchDashboardMetrics, 30_000);
    return () => window.clearInterval(intervalId);
  }, [fetchDashboardMetrics]);

  useEffect(() => {
    if (shadowResult) fetchDashboardMetrics();
  }, [shadowResult, fetchDashboardMetrics]);

  const greeting = (() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 18) return 'Good afternoon';
    return 'Good evening';
  })();

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  const handleTrySample = async () => {
    const demoPatient = await loadDemoPatient();
    await runShadowAudit({
      note: demoPatient.clinical_note,
      billedCodes: demoPatient.billed_codes,
      patientId: demoPatient.id,
      demo: true,
    });
    navigate('/shadow');
  };

  const queueCount = metrics.missed_codes_found || shadowResult?.identified_codes?.length || 0;
  const revenue = metrics.total_recovered_revenue || 0;
  const acceptedRate = metrics.accepted_rate || 0;
  const rejectedRate = metrics.rejected_rate || 0;
  const auditStatus = auditVerification?.status || metrics.audit_integrity_status || 'not_verified';
  const eventsChecked = auditVerification?.events_checked || 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--color-ink)' }}>
          {greeting}, Operator
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-secondary)' }}>
          {today}
        </p>
      </div>

      {/* Primary: Your queue */}
      <div className="card">
        <div className="card-body">
          <div className="flex items-start justify-between gap-6">
            <div className="flex items-start gap-4">
              <div
                className="p-3 rounded-control"
                style={{ backgroundColor: 'var(--color-fill)' }}
              >
                <ClipboardList
                  size={24}
                  style={{ color: 'var(--color-primary)' }}
                />
              </div>
              <div>
                <h2 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
                  Your queue
                </h2>
                <p className="text-sm mt-1" style={{ color: 'var(--color-secondary)' }}>
                  {queueCount > 0
                    ? `${queueCount} encounter${queueCount !== 1 ? 's' : ''} awaiting review`
                    : 'No encounters currently pending review'}
                </p>
              </div>
            </div>
            <button
              onClick={() => navigate('/shadow')}
              className="btn-primary btn-sm flex-shrink-0"
            >
              Open review queue
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Revenue MTD */}
        <div className="card">
          <div className="card-body">
            <div className="flex items-center gap-2 mb-3">
              <DollarSign size={16} style={{ color: 'var(--color-primary)' }} />
              <span className="text-sm font-medium" style={{ color: 'var(--color-secondary)' }}>
                Identified revenue (MTD)
              </span>
            </div>
            <p className="text-2xl font-bold" style={{ color: 'var(--color-ink)' }}>
              {formatCurrency(revenue)}
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--color-muted)' }}>
              Pending your team's review
            </p>
          </div>
        </div>

        {/* Suggestions accepted vs dismissed */}
        <div className="card">
          <div className="card-body">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp size={16} style={{ color: 'var(--color-ink)' }} />
              <span className="text-sm font-medium" style={{ color: 'var(--color-secondary)' }}>
                Suggestions (this week)
              </span>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 size={16} style={{ color: '#047857' }} />
                <span className="text-lg font-bold" style={{ color: 'var(--color-ink)' }}>
                  {Math.round(acceptedRate * 100)}%
                </span>
                <span className="text-xs" style={{ color: 'var(--color-muted)' }}>
                  accepted
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <XCircle size={16} style={{ color: '#BE123C' }} />
                <span className="text-lg font-bold" style={{ color: 'var(--color-ink)' }}>
                  {Math.round(rejectedRate * 100)}%
                </span>
                <span className="text-xs" style={{ color: 'var(--color-muted)' }}>
                  dismissed
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Audit trail status */}
        <div className="card">
          <div className="card-body">
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck size={16} style={{ color: '#047857' }} />
              <span className="text-sm font-medium" style={{ color: 'var(--color-secondary)' }}>
                Audit trail status
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="status-dot-positive" />
              <span className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                {auditStatus === 'verified'
                  ? 'Verified'
                  : auditStatus === 'failed'
                  ? 'Verification failed'
                  : 'Not yet verified'}
              </span>
            </div>
            <p className="text-xs mt-1" style={{ color: 'var(--color-muted)' }}>
              {eventsChecked > 0 ? `${eventsChecked.toLocaleString()} records` : 'No records yet'}
            </p>
          </div>
        </div>
      </div>

      {/* Sandbox card */}
      <div
        className="card border-2 border-dashed"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div className="card-body flex items-start gap-4">
          <div
            className="p-3 rounded-control flex-shrink-0"
            style={{ backgroundColor: 'var(--color-fill)' }}
          >
            <Beaker size={20} style={{ color: 'var(--color-secondary)' }} />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
              Sandbox
            </h3>
            <p className="text-sm mt-1" style={{ color: 'var(--color-secondary)' }}>
              Try Buddee on a synthetic patient. No PHI, nothing is recorded against your organization.
            </p>
            <button
              onClick={handleTrySample}
              className="btn-secondary btn-sm mt-3"
            >
              Try sample patient
            </button>
          </div>
        </div>
      </div>

      {/* System status — collapsed for IT admins */}
      <div
        className="card"
        style={{ backgroundColor: 'var(--color-fill)' }}
      >
        <button
          onClick={() => setSloOpen(!sloOpen)}
          className="card-body w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-2">
            <Gauge size={16} style={{ color: 'var(--color-muted)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--color-secondary)' }}>
              System status
            </span>
          </div>
          {sloOpen ? (
            <ChevronDown size={16} style={{ color: 'var(--color-muted)' }} />
          ) : (
            <ChevronRight size={16} style={{ color: 'var(--color-muted)' }} />
          )}
        </button>
        {sloOpen && (
          <div className="px-5 pb-5">
            <SLOPanel />
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
