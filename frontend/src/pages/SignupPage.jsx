import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import Captcha from '../components/Captcha';
import useStore from '../store/useStore';

/**
 * Invite-only account creation. The invite token arrives in the link the
 * admin shares (`/signup?token=...`) and can also be pasted manually.
 * Signup requires the same hCaptcha gate as login.
 */
export default function SignupPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const signup = useStore((state) => state.signup);
  const [inviteToken, setInviteToken] = useState(searchParams.get('token') || '');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [captchaToken, setCaptchaToken] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const canSubmit =
    inviteToken.trim() && email.trim() && password.length >= 12 && captchaToken && !busy;

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await signup({
        inviteToken: inviteToken.trim(),
        email: email.trim(),
        password,
        fullName: fullName.trim(),
        captchaToken,
      });
      navigate('/', { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail || 'Could not create your account — check the invite and try again.');
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
              Create your account
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
              Buddee accounts are invite-only — ask your admin for a link
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
              <label className="label" htmlFor="signup-invite">
                Invite token
              </label>
              <input
                id="signup-invite"
                type="text"
                className="input"
                value={inviteToken}
                onChange={(e) => setInviteToken(e.target.value)}
                placeholder="Paste your invite token"
                required
              />
            </div>

            <div>
              <label className="label" htmlFor="signup-name">
                Full name
              </label>
              <input
                id="signup-name"
                type="text"
                autoComplete="name"
                className="input"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Dr. Jordan Rivera"
              />
            </div>


            <div>
              <label className="label" htmlFor="signup-email">
                Email
              </label>
              <input
                id="signup-email"
                type="email"
                autoComplete="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@practice.com"
                required
              />
            </div>

            <div>
              <label className="label" htmlFor="signup-password">
                Password
              </label>
              <div className="relative">
                <input
                  id="signup-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  className="input pr-10"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 12 characters"
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
              <p className="text-xs mt-1.5" style={{ color: 'var(--color-muted)' }}>
                12+ characters with at least one letter and one digit.
              </p>
            </div>

            <Captcha onVerify={setCaptchaToken} />

            <button type="submit" className="btn-primary w-full" disabled={!canSubmit}>
              {busy ? 'Creating account…' : 'Create account'}
            </button>

            <div className="text-center text-xs">
              <Link to="/login" className="hover:underline" style={{ color: 'var(--color-primary)' }}>
                Already have an account? Sign in
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
