"""hCaptcha verification for the portal login/signup flows.

The browser widget produces a short-lived token; this module verifies it
server-side against ``https://hcaptcha.com/siteverify`` before any
credential check runs. Security posture:

  * The outbound call goes through ``core.outbound_security.validate_outbound_url``
    (the SSRF guard) and carries a hard 5s timeout.
  * **Fail closed**: network errors, non-200 responses, malformed JSON, or a
    missing ``HCAPTCHA_SECRET_KEY`` all reject the login. A captcha outage
    must never become an authentication bypass.
  * ``BUDDI_CAPTCHA_DISABLED=1`` skips verification for local dev / CI only —
    it is ignored when ``ENVIRONMENT=production`` (or unset, which defaults
    to production), mirroring the break-glass discipline in ``core/phi_guard``.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from core.config import settings
from core.outbound_security import OutboundURLBlocked, validate_outbound_url

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://hcaptcha.com/siteverify"
CAPTCHA_TIMEOUT_SECONDS = 5.0


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT", "production").strip().lower() == "production"


def captcha_disabled() -> bool:
    """True only when verification is explicitly bypassed outside production."""

    if _is_production():
        return False
    return os.getenv("BUDDI_CAPTCHA_DISABLED", "").strip() == "1"


def verify_captcha(token: Optional[str], remote_ip: Optional[str] = None) -> bool:
    """Verify an hCaptcha response token. Returns True only on proven success."""

    if captcha_disabled():
        logger.debug("hCaptcha verification skipped (BUDDI_CAPTCHA_DISABLED, non-production)")
        return True
    if not token or not token.strip():
        logger.warning("hCaptcha verification failed: empty token")
        return False
    secret = settings.HCAPTCHA_SECRET_KEY
    if not secret:
        # Fail closed — a production deployment without the secret must not
        # accept logins rather than skip the bot check.
        logger.error("hCaptcha verification failed: HCAPTCHA_SECRET_KEY is not configured")
        return False
    try:
        url = validate_outbound_url(SITEVERIFY_URL)
    except OutboundURLBlocked:
        logger.error("hCaptcha siteverify URL blocked by outbound security policy")
        return False
    payload = {"secret": secret, "response": token.strip()}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        resp = httpx.post(url, data=payload, timeout=CAPTCHA_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("hCaptcha siteverify request failed: %s", exc)
        return False
    if resp.status_code != 200:
        logger.warning("hCaptcha siteverify returned HTTP %s", resp.status_code)
        return False
    try:
        body = resp.json()
    except ValueError:
        logger.warning("hCaptcha siteverify returned malformed JSON")
        return False
    success = body.get("success") is True
    if not success:
        logger.info("hCaptcha rejected token: %s", body.get("error-codes"))
    return success


__all__ = ["SITEVERIFY_URL", "captcha_disabled", "verify_captcha"]
