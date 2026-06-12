import React, { useEffect, useState } from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import ChatPage from './pages/ChatPage';
import ShadowPage from './pages/ShadowPage';
import AuditPage from './pages/AuditPage';
import useStore, { subscribeApiKey, getRuntimeApiKey } from './store/useStore';

/**
 * Lightweight in-app prompt for the X-API-Key header.
 *
 * The launch deploy uses a build-time `VITE_API_KEY`, but local-dev runs
 * (and any environment where baking the secret into the bundle is
 * unacceptable) need a way to provide the key after page load. We listen
 * for 401s on the shared axios instance, prompt the user once, and keep
 * the value in memory only — never localStorage.
 */
function ApiKeyPrompt() {
  const setApiKey = useStore((state) => state.setApiKey);
  const [needsKey, setNeedsKey] = useState(!getRuntimeApiKey());
  const [draft, setDraft] = useState('');

  useEffect(() => {
    const unsubscribe = subscribeApiKey((key, meta) => {
      if (!key && meta?.unauthorized) setNeedsKey(true);
      if (key) setNeedsKey(false);
    });
    return () => unsubscribe();
  }, []);

  if (!needsKey) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm flex items-center justify-center">
      <div className="glass-panel rounded-2xl p-6 max-w-md w-full mx-4">
        <h3 className="text-sm font-bold text-slate-100 mb-2">Connect to Buddi</h3>
        <p className="text-xs text-slate-500 mb-4">
          Enter your Buddi API key to get started. Your key stays in browser memory only —
          it's never saved to disk or localStorage.
        </p>
        <input
          type="password"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="API key"
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-slate-100 text-sm mb-3"
        />
        <button
          type="button"
          onClick={() => {
            if (draft.trim()) {
              setApiKey(draft.trim());
              setNeedsKey(false);
            }
          }}
          className="btn-primary w-full py-2 rounded-xl text-xs font-bold"
        >
          Connect
        </button>
      </div>
    </div>
  );
}

/**
 * Reads `?demo=true` and triggers the canonical demo bootstrap exactly
 * once. Sits inside <Router> so it can use `useLocation`. Removing the
 * query param afterward keeps the URL clean for screenshots.
 */
function DemoQueryHandler() {
  const location = useLocation();
  const navigate = useNavigate();
  const runDemoBootstrap = useStore((state) => state.runDemoBootstrap);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('demo') === 'true') {
      runDemoBootstrap();
      params.delete('demo');
      const cleaned = params.toString();
      navigate(
        { pathname: location.pathname, search: cleaned ? `?${cleaned}` : '' },
        { replace: true },
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);
  return null;
}


function PatientBootstrap() {
  const fetchPatientProfile = useStore((state) => state.fetchPatientProfile);

  useEffect(() => {
    fetchPatientProfile('PT-9012');
  }, [fetchPatientProfile]);

  return null;
}

/**
 * Buddee Health shell.
 *
 * FE-06 (April-21 re-audit): each top-level route is wrapped in its own
 * `<ErrorBoundary>` so that a thrown exception inside one page cannot
 * crash the entire app. The boundary renders a fallback UI and leaves the
 * router / layout in a usable state.
 */
function App() {
  return (
    <Router>
      <div className="mesh-background" />
      <ApiKeyPrompt />
      <PatientBootstrap />
      <DemoQueryHandler />
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route
              index
              element={
                <ErrorBoundary>
                  <Dashboard />
                </ErrorBoundary>
              }
            />
            <Route
              path="chat"
              element={
                <ErrorBoundary>
                  <ChatPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="shadow"
              element={
                <ErrorBoundary>
                  <ShadowPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="audit"
              element={
                <ErrorBoundary>
                  <AuditPage />
                </ErrorBoundary>
              }
            />
          </Route>
        </Routes>
      </ErrorBoundary>
    </Router>
  );
}

export default App;
