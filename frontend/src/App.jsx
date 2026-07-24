import React, { useEffect, useState } from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import ChatPage from './pages/ChatPage';
import ShadowPage from './pages/ShadowPage';
import AuditPage from './pages/AuditPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import useStore, { subscribeApiKey, getRuntimeApiKey, getRuntimeSession } from './store/useStore';

/**
 * Full-page sign-in / connect screen.
 *
 * Replaces the old modal-over-broken-app approach with a centered card
 * on the light background. On 401 mid-session, shows the same page with
 * "Your session key is no longer valid."
 */
function ApiKeyPrompt() {
  const setApiKey = useStore((state) => state.setApiKey);
  const [needsKey, setNeedsKey] = useState(!getRuntimeApiKey());
  const [draft, setDraft] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [isReAuth, setIsReAuth] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribeApiKey((key, meta) => {
      if (!key && meta?.unauthorized) {
        setNeedsKey(true);
        setIsReAuth(true);
      }
      if (key) {
        setNeedsKey(false);
        setIsReAuth(false);
      }
    });
    return () => unsubscribe();
  }, []);

  if (!needsKey) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      style={{ backgroundColor: 'var(--color-bg)' }}
    >
      <div className="w-full max-w-sm mx-6">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-6">
          <img
            src="/Buddee_Health.png"
            alt="Buddee Health"
            className="w-10 h-10 rounded object-contain"
          />
          <div>
            <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
              Buddee Health
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
              Coding review and audit support for your revenue-cycle team
            </p>
          </div>
        </div>

        <div
          className="card"
        >
          <div className="card-body space-y-4">
            {isReAuth && (
              <div
                className="text-sm p-3 rounded-control"
                style={{
                  backgroundColor: 'var(--color-caution-bg, #FEF3E2)',
                  color: '#B45309',
                }}
              >
                Your session key is no longer valid. Please re-enter it.
              </div>
            )}

            <div>
              <label className="label" htmlFor="api-key-input">
                API key
              </label>
              <div className="relative">
                <input
                  id="api-key-input"
                  type={showKey ? 'text' : 'password'}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Enter your API key"
                  className="input pr-10"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--color-muted)' }}
                  aria-label={showKey ? 'Hide key' : 'Show key'}
                >
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <p className="text-xs mt-1.5" style={{ color: 'var(--color-muted)' }}>
                Your key stays in this browser's memory — never saved to disk.
              </p>
            </div>

            <button
              type="button"
              onClick={() => {
                if (draft.trim()) {
                  setApiKey(draft.trim());
                  setNeedsKey(false);
                }
              }}
              disabled={!draft.trim()}
              className="btn-primary w-full"
            >
              Connect
            </button>

            <div className="text-center">
              <a
                href="#"
                className="text-xs hover:underline"
                style={{ color: 'var(--color-primary)' }}
                onClick={(e) => {
                  e.preventDefault();
                  // TODO: link to docs
                }}
              >
                Where do I find my key?
              </a>
            </div>
          </div>
        </div>

        {/* Product footnotes */}
        <div
          className="flex items-center justify-center gap-4 mt-6 text-xs"
          style={{ color: 'var(--color-muted)' }}
        >
          <span>Shadow mode only</span>
          <span style={{ color: 'var(--color-border)' }}>·</span>
          <span>Verifiable audit trail</span>
          <span style={{ color: 'var(--color-border)' }}>·</span>
          <span>No auto-submission</span>
        </div>
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
/**
 * Portal auth gate: the operator UI requires a live identity — a portal
 * session (human lane), an API key (machine lane), or the public synthetic
 * demo (`?demo=true`). Anything else is redirected to the login page.
 */
function RequireAuth({ children }) {
  const session = useStore((state) => state.session);
  const preferApiKey = useStore((state) => state.preferApiKey);
  const location = useLocation();
  const isDemo = new URLSearchParams(location.search).get('demo') === 'true';
  if (session || getRuntimeSession() || getRuntimeApiKey() || preferApiKey || isDemo) {
    return children;
  }
  return <Navigate to="/login" replace state={{ from: location.pathname }} />;
}

/** The legacy API-key overlay stays available off the auth pages only. */
function ConditionalApiKeyPrompt() {
  const location = useLocation();
  if (location.pathname.startsWith('/login') || location.pathname.startsWith('/signup')) {
    return null;
  }
  return <ApiKeyPrompt />;
}

function App() {
  return (
    <Router>
      <ConditionalApiKeyPrompt />
      <PatientBootstrap />
      <DemoQueryHandler />
      <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
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
