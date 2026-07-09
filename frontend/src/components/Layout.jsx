import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import useStore from '../store/useStore';

const Layout = () => {
  const fetchPatientProfile = useStore((state) => state.fetchPatientProfile);
  const auditVerification = useStore((state) => state.auditVerification);
  const auditEvents = useStore((state) => state.auditEvents);
  const fetchAuditLogs = useStore((state) => state.fetchAuditLogs);
  const navigate = useNavigate();
  const [dark, setDark] = useState(() => {
    if (typeof window === 'undefined') return false;
    const stored = localStorage.getItem('buddee-theme');
    if (stored) return stored === 'dark';
    return false; // light is default
  });

  useEffect(() => {
    fetchPatientProfile();
    fetchAuditLogs();
  }, [fetchPatientProfile, fetchAuditLogs]);

  useEffect(() => {
    const root = document.documentElement;
    if (dark) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('buddee-theme', dark ? 'dark' : 'light');
  }, [dark]);

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ backgroundColor: 'var(--color-bg)' }}>
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <TopBar dark={dark} onToggleTheme={() => setDark((d) => !d)} />
        {/* Trust bar */}
        <div className="trust-bar">
          <span className="font-medium" style={{ color: 'var(--color-ink)' }}>
            Shadow mode
          </span>
          <span>— Buddee suggests, your team approves. Nothing is submitted automatically.</span>
          <span className="mx-1" style={{ color: 'var(--color-border)' }}>·</span>
          <button
            onClick={() => navigate('/audit')}
            className="text-sm hover:underline"
            style={{ color: 'var(--color-primary)' }}
          >
            <span className="status-dot-positive inline-block align-middle mr-1.5" />
            Audit trail verified
            {auditVerification?.events_checked
              ? ` · ${auditVerification.events_checked.toLocaleString()} records`
              : ` · ${auditEvents.length.toLocaleString()} records`}
          </button>
        </div>
        {/* Main content area */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-content mx-auto p-6 lg:p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};

export default Layout;
