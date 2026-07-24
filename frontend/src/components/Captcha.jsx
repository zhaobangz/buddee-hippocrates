import React, { useEffect } from 'react';
import HCaptcha from '@hcaptcha/react-hcaptcha';

/**
 * hCaptcha wrapper for the portal auth pages.
 *
 * The site key is a build-time public identifier (`VITE_HCAPTCHA_SITEKEY`)
 * — the *secret* never leaves the backend. When no site key is configured
 * (local dev), we render a notice and immediately report a bypass token;
 * the backend only accepts that bypass outside production
 * (`BUDDI_CAPTCHA_DISABLED=1` + non-production ENVIRONMENT), so a
 * misconfigured production build still fails closed server-side.
 */
const SITEKEY = (import.meta.env && import.meta.env.VITE_HCAPTCHA_SITEKEY) || '';

export default function Captcha({ onVerify }) {
  useEffect(() => {
    if (!SITEKEY) onVerify('dev-bypass-no-sitekey');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!SITEKEY) {
    return (
      <p className="text-xs" style={{ color: 'var(--color-muted)' }}>
        Captcha not configured — accepted automatically in this development build.
      </p>
    );
  }
  return (
    <HCaptcha
      sitekey={SITEKEY}
      onVerify={(token) => onVerify(token)}
      onExpire={() => onVerify(null)}
      onError={() => onVerify(null)}
    />
  );
}
