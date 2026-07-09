import React from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';

/**
 * Top-level React Error Boundary (FE-06).
 *
 * A thrown exception inside any page component used to crash the entire
 * Buddee Health shell (blank white screen). In a HIPAA-scope clinical UI
 * that is a usability *and* safety concern — the clinician loses context
 * without a clear signal. This boundary catches render-time exceptions,
 * logs them to the console for developer diagnostics, and renders a minimal
 * fallback UI with a "Reload" control so the rest of the shell remains
 * usable.
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
    console.error('[Buddee Health] render error caught by ErrorBoundary:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div
        className="min-h-screen flex items-center justify-center p-6"
        style={{ backgroundColor: 'var(--color-bg)' }}
      >
        <div
          className="max-w-md w-full card p-6"
          style={{ borderLeft: '3px solid #BE123C' }}
        >
          <div className="flex items-start gap-3">
            <div
              className="p-2 rounded-control"
              style={{
                backgroundColor: 'var(--color-risk-bg, #FDECEF)',
              }}
            >
              <AlertTriangle size={20} style={{ color: '#BE123C' }} />
            </div>
            <div className="flex-1">
              <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
                Something went wrong rendering this view.
              </h2>
              <p className="text-sm mt-1" style={{ color: 'var(--color-secondary)' }}>
                The error has been captured locally. No clinical action has
                been taken. You can safely reload the application.
              </p>
              <button
                onClick={this.handleReload}
                className="btn-primary btn-sm mt-4"
              >
                <RefreshCcw size={16} />
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
