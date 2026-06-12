import React from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';

/**
 * Top-level React Error Boundary (FE-06).
 *
 * A thrown exception inside any page component used to crash the entire
 * Buddee Health shell (blank white screen). In a HIPAA-scope clinical UI that is a
 * usability *and* safety concern — the clinician loses context without a
 * clear signal. This boundary catches render-time exceptions, logs them to
 * the console for developer diagnostics, and renders a minimal fallback
 * UI with a "Reload" control so the rest of the shell remains usable.
 *
 * Note: React error boundaries only catch errors in the React render tree.
 * Async/event-handler errors still need their own try/catch; those are
 * handled by the Zustand action creators in `src/store/useStore.js`.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Intentionally `console.error` only — do NOT forward the stack to a
    // third-party sink from here, the stack frame could include PHI-adjacent
    // state. Observability hooks live server-side (core/tracing.py).
    console.error('[Buddee Health] render error caught by ErrorBoundary:', error, errorInfo);
  }

  handleReload = () => {
    // A full reload is safer than trying to reset component state — it
    // forces re-auth, refreshes cached bundles, and avoids a partially
    // hydrated store.
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-slate-950 text-slate-200">
        <div className="max-w-md w-full glass-panel p-6 rounded-2xl border-rose-500/20">
          <div className="flex items-start space-x-3">
            <div className="p-2 rounded-xl bg-rose-500/10 text-rose-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <h2 className="text-sm font-bold text-slate-100">
                Something went wrong rendering this view.
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                The error has been captured locally. No clinical action has
                been taken. You can safely reload the application.
              </p>
              <button
                onClick={this.handleReload}
                className="mt-4 inline-flex items-center px-3 py-1.5 rounded-lg bg-medical-500 hover:bg-medical-400 text-white text-xs font-bold transition-colors"
              >
                <RefreshCcw className="w-3 h-3 mr-2" />
                Reload
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
