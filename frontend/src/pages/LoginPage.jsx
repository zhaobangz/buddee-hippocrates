import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import Captcha from '../components/Captcha';
import useStore from '../store/useStore';

/**
 * Portal sign-in (human lane): email + password + hCaptcha → session JWT.
 * Machine-lane users can still fall through to the API-key prompt via the
 * "Use an API key instead" link.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const login = useStore((state) => state.login);
  const setPreferApiKey = useStore((state) => state.setPreferApiKey);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [captchaToken, setCaptchaToken] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const canSubmit = email.trim() && password && captchaToken && !busy;

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await login({ email: email.trim(), password, captchaToken });
      navigate('/', { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail || 'Sign-in failed — check your credentials and try again.');
      setBusy(false);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ backgroundColor: 'var(--color-bg)' }}
    >
      <div className="w-full max-w-sm mx-6">
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
              Sign in to your operator portal
            </p>
          </div>
        </div>

        <div className="card">
          <form className="card-body space-y-4" onSubmit={handleSubmit}>
            {error && (
              <div
                className="text-sm p-3 rounded-control"
                style={{ backgroundColor: 'var(--color-caution-bg, #FEF3E2)', color: '#B45309' }}
                role="alert"
              >
                {error}
              </div>
            )}

            <div>
              <label className="label" htmlFor="login-email">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                autoComplete="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@practice.com"
                autoFocus
                required
              />
            </div>

            <div>
              <label className="label" htmlFor="login-password">
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  className="input pr-10"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Your password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--color-muted)' }}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <Captcha onVerify={setCaptchaToken} />

            <button type="submit" className="btn-primary w-full" disabled={!canSubmit}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>

            <div className="flex items-center justify-between text-xs">
              <Link
                to="/signup"
                className="hover:underline"
                style={{ color: 'var(--color-primary)' }}
              >
                Have an invite? Create account
              </Link>
              <a
                href="#api-key"
                className="hover:underline"
                style={{ color: 'var(--color-muted)' }}
                onClick={(e) => {
                  e.preventDefault();
                  setPreferApiKey(true);
                  navigate('/');
                }}
              >
                Use an API key instead
              </a>
            </div>
          </form>
        </div>

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
