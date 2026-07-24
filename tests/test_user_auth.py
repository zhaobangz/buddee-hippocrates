"""Tests for portal user auth (invite-only email+password+hCaptcha).

Covers the pure primitives (password policy, JWT, captcha verifier) and the
full DB-backed flow against the test Postgres (provision → invite → signup →
login → me → refresh → logout), including lockout, invite abuse, and
refresh-token reuse detection. DB-backed tests skip gracefully when the
test Postgres is unreachable, mirroring the ``tenant_api_key`` fixture in
conftest.py.
"""

from __future__ import annotations

import uuid

import pytest

from core.user_auth import (
    issue_access_token,
    normalize_email,
    refresh_token_digest,
    validate_password,
    verify_access_token,
)


class TestPasswordPolicy:
    @pytest.mark.parametrize(
        "password",
        [
            "Tr7ubador!nine42",
            "a1" + "x" * 30,  # long is fine
            "CorrectHorse9BatteryStaple",
        ],
    )
    def test_accepts_strong_passwords(self, password):
        assert validate_password(password) is None

    @pytest.mark.parametrize(
        "password,fragment",
        [
            ("", "required"),
            ("short1", "at least"),
            ("password1234", "too common"),
            ("aaaaaaaaaaaa", "repeated"),
            ("onlylettersxx", "letter and one digit"),
            ("1234567890123", "letter and one digit"),
        ],
    )
    def test_rejects_weak_passwords(self, password, fragment):
        error = validate_password(password)
        assert error is not None
        assert fragment in error

    def test_normalize_email(self):
        assert normalize_email("  Alice@Example.COM \n") == "alice@example.com"


class TestAccessTokens:
    def _issue(self, role="clinician"):
        return issue_access_token(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            role=role,
            session_id=uuid.uuid4(),
        )[0]

    def test_roundtrip(self):
        uid, tid = uuid.uuid4(), uuid.uuid4()
        token, expires_in = issue_access_token(
            user_id=uid, tenant_id=tid, role="admin", session_id=uuid.uuid4()
        )
        assert expires_in > 0
        claims = verify_access_token(token)
        assert claims is not None
        assert claims["sub"] == str(uid)
        assert claims["tenant_id"] == str(tid)
        assert claims["role"] == "admin"
        assert claims["scopes"] == ["clinician", "ingest", "admin"]

    def test_tampered_signature_rejected(self):
        token = self._issue()
        assert verify_access_token(token[:-2] + "zz") is None

    def test_alg_none_rejected(self):
        import jwt as pyjwt

        forged = pyjwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "role": "admin",
                "iss": "buddi-portal",
                "aud": "buddi-portal-web",
                "exp": 9999999999,
                "iat": 1,
            },
            key="",
            algorithm="none",
        )
        assert verify_access_token(forged) is None

    def test_wrong_key_rejected(self):
        import jwt as pyjwt

        forged = pyjwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "role": "admin",
                "iss": "buddi-portal",
                "aud": "buddi-portal-web",
                "exp": 9999999999,
                "iat": 1,
            },
            key="attacker-controlled-key",
            algorithm="HS256",
        )
        assert verify_access_token(forged) is None

    def test_expired_rejected(self):
        import jwt as pyjwt

        from core.user_auth import _signing_key

        expired = pyjwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "role": "clinician",
                "iss": "buddi-portal",
                "aud": "buddi-portal-web",
                "exp": 1000,
                "iat": 900,
            },
            key=_signing_key(),
            algorithm="HS256",
        )
        assert verify_access_token(expired) is None

    def test_unknown_role_rejected(self):
        import jwt as pyjwt

        from core.user_auth import _signing_key

        token = pyjwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "role": "superadmin",  # not in KNOWN_ROLES
                "iss": "buddi-portal",
                "aud": "buddi-portal-web",
                "exp": 9999999999,
                "iat": 1,
            },
            key=_signing_key(),
            algorithm="HS256",
        )
        assert verify_access_token(token) is None

    def test_refresh_digest_properties(self):
        assert refresh_token_digest("a") != refresh_token_digest("b")
        assert refresh_token_digest("a") == refresh_token_digest("a")
        assert len(refresh_token_digest("a")) == 64


# ---------------------------------------------------------------------------
# hCaptcha verifier (network mocked)
# ---------------------------------------------------------------------------


class TestCaptchaVerifier:
    def test_disabled_flag_honoured_outside_production(self, monkeypatch):
        from core.captcha import verify_captcha

        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("BUDDI_CAPTCHA_DISABLED", "1")
        assert verify_captcha(None) is True

    def test_disabled_flag_dead_in_production(self, monkeypatch):
        from core.captcha import verify_captcha

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("BUDDI_CAPTCHA_DISABLED", "1")
        monkeypatch.setattr("core.config.settings.HCAPTCHA_SECRET_KEY", "secret")
        assert verify_captcha(None) is False  # empty token still rejected

    def test_missing_secret_fails_closed(self, monkeypatch):
        from core.captcha import verify_captcha

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("BUDDI_CAPTCHA_DISABLED", raising=False)
        monkeypatch.setattr("core.config.settings.HCAPTCHA_SECRET_KEY", "")
        assert verify_captcha("some-token") is False

    def test_http_error_fails_closed(self, monkeypatch):
        import httpx

        from core.captcha import verify_captcha

        monkeypatch.setattr("core.config.settings.HCAPTCHA_SECRET_KEY", "secret")

        def _boom(*args, **kwargs):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "post", _boom)
        assert verify_captcha("some-token") is False

    def test_success_and_rejection_paths(self, monkeypatch):
        import httpx

        from core.captcha import verify_captcha

        monkeypatch.setattr("core.config.settings.HCAPTCHA_SECRET_KEY", "secret")

        class _Resp:
            def __init__(self, body):
                self.status_code = 200
                self._body = body

            def json(self):
                return self._body

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp({"success": True}))
        assert verify_captcha("good-token") is True
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: _Resp({"success": False, "error-codes": ["expired"]})
        )
        assert verify_captcha("stale-token") is False


# ---------------------------------------------------------------------------
# DB-backed flow tests (skip without the test Postgres)
# ---------------------------------------------------------------------------


@pytest.fixture
def portal_tenant(monkeypatch):
    """Provision a tenant + admin user directly, bypass captcha for routes.

    Yields dict(tenant_id, admin_email, admin_password, invite_token=None).
    Skips when the test Postgres is unreachable or lacks the new tables.
    """

    monkeypatch.setattr("backend.auth_users.verify_captcha", lambda *a, **k: True)
    from backend.auth import hash_password
    from core import models
    from core.database import SessionLocal

    suffix = uuid.uuid4().hex[:8]
    email = f"admin-{suffix}@example.com"
    password = "Sup3r!longpassphrase"
    db = SessionLocal()
    try:
        tenant = models.Tenant(name=f"portal-test-{suffix}")
        db.add(tenant)
        db.flush()
        admin = models.User(
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            full_name="Portal Admin",
            role="admin",
        )
        db.add(admin)
        db.commit()
        ctx = {
            "tenant_id": tenant.id,
            "admin_id": admin.id,
            "admin_email": email,
            "admin_password": password,
        }
    except Exception as exc:
        db.rollback()
        pytest.skip(f"test Postgres unavailable for portal flow tests: {exc}")
    finally:
        db.close()

    yield ctx

    # Teardown: remove everything created above (children first).
    db = SessionLocal()
    try:
        db.query(models.AuthRefreshToken).filter(
            models.AuthRefreshToken.tenant_id == ctx["tenant_id"]
        ).delete(synchronize_session=False)
        db.query(models.TenantInvite).filter(
            models.TenantInvite.tenant_id == ctx["tenant_id"]
        ).delete(synchronize_session=False)
        db.query(models.User).filter(models.User.tenant_id == ctx["tenant_id"]).delete(
            synchronize_session=False
        )
        db.query(models.Tenant).filter(models.Tenant.id == ctx["tenant_id"]).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


class TestPortalFlow:
    STRONG = "N3w!password-horizon"

    def _login(self, client, email, password):
        return client.post(
            "/api/auth/login",
            json={"email": email, "password": password, "captcha_token": "bypass"},
        )

    def _signup(self, client, invite_token, email, password=None):
        return client.post(
            "/api/auth/signup",
            json={
                "invite_token": invite_token,
                "email": email,
                "password": password or self.STRONG,
                "full_name": "New Clinician",
                "captcha_token": "bypass",
            },
        )

    def _invite(self, client, admin_token, email=None, role="clinician"):
        resp = client.post(
            "/api/auth/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": email, "role": role},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["invite_token"]

    def test_login_me_roundtrip(self, client, portal_tenant):
        resp = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["user"]["role"] == "admin"
        assert body["expires_in"] > 0
        me = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert me.status_code == 200
        assert me.json()["email"] == portal_tenant["admin_email"]

    def test_login_wrong_password_uniform_401(self, client, portal_tenant):
        resp = self._login(client, portal_tenant["admin_email"], "Wr0ng-password-999")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password."

    def test_login_unknown_email_uniform_401(self, client, portal_tenant):
        resp = self._login(client, f"ghost-{uuid.uuid4().hex[:6]}@example.com", "Anyth1ng!long")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password."

    def test_lockout_after_five_failures(self, client, portal_tenant):
        for _ in range(5):
            resp = self._login(client, portal_tenant["admin_email"], "Wr0ng-password-999")
            assert resp.status_code == 401
        # Sixth attempt — even with the CORRECT password — is locked out.
        resp = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        assert resp.status_code == 429

    def test_invite_signup_login_flow(self, client, portal_tenant):
        admin = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        admin_token = admin.json()["access_token"]
        new_email = f"clinician-{uuid.uuid4().hex[:6]}@example.com"
        invite = self._invite(client, admin_token, email=new_email)

        created = self._signup(client, invite, new_email)
        assert created.status_code == 201, created.text
        session = created.json()
        assert session["user"]["role"] == "clinician"
        assert session["user"]["email"] == new_email

        # The new account can log in on its own.
        login = self._login(client, new_email, self.STRONG)
        assert login.status_code == 200

    def test_invite_single_use(self, client, portal_tenant):
        admin = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        invite = self._invite(client, admin.json()["access_token"])
        email_a = f"a-{uuid.uuid4().hex[:6]}@example.com"
        assert self._signup(client, invite, email_a).status_code == 201
        email_b = f"b-{uuid.uuid4().hex[:6]}@example.com"
        assert self._signup(client, invite, email_b).status_code == 400

    def test_invite_email_binding_enforced(self, client, portal_tenant):
        admin = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        bound = f"bound-{uuid.uuid4().hex[:6]}@example.com"
        invite = self._invite(client, admin.json()["access_token"], email=bound)
        other = f"other-{uuid.uuid4().hex[:6]}@example.com"
        assert self._signup(client, invite, other).status_code == 400

    def test_signup_weak_password_rejected(self, client, portal_tenant):
        admin = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        invite = self._invite(client, admin.json()["access_token"])
        resp = self._signup(client, invite, f"c-{uuid.uuid4().hex[:6]}@example.com", "short")
        assert resp.status_code == 422

    def test_clinician_cannot_create_invites(self, client, portal_tenant):
        admin = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        invite = self._invite(client, admin.json()["access_token"])
        email = f"d-{uuid.uuid4().hex[:6]}@example.com"
        session = self._signup(client, invite, email).json()
        resp = client.post(
            "/api/auth/invites",
            headers={"Authorization": f"Bearer {session['access_token']}"},
            json={"role": "clinician"},
        )
        assert resp.status_code == 403

    def test_refresh_rotation_and_reuse_detection(self, client, portal_tenant):
        login = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        refresh_token = login.json()["refresh_token"]

        rotated = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert rotated.status_code == 200, rotated.text
        new_refresh = rotated.json()["refresh_token"]
        assert new_refresh != refresh_token

        # Reusing the OLD token = theft: whole family revoked.
        reuse = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert reuse.status_code == 401
        # The rotated token is now dead too.
        dead = client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
        assert dead.status_code == 401

    def test_logout_revokes_refresh(self, client, portal_tenant):
        login = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        refresh_token = login.json()["refresh_token"]
        assert (
            client.post("/api/auth/logout", json={"refresh_token": refresh_token}).status_code
            == 204
        )
        assert (
            client.post("/api/auth/refresh", json={"refresh_token": refresh_token}).status_code
            == 401
        )

    def test_tampered_jwt_rejected_on_portal_route(self, client, portal_tenant):
        login = self._login(client, portal_tenant["admin_email"], portal_tenant["admin_password"])
        token = login.json()["access_token"]
        forged = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert resp.status_code == 401

    def test_api_key_lane_still_works(self, client, auth_headers):
        """Machine lane regression: the API-key path is untouched."""

        resp = client.get("/api/dashboard/metrics", headers=auth_headers)
        assert resp.status_code != 401

    def test_captcha_gate_blocks_before_db(self, client, monkeypatch):
        """When captcha fails, login is rejected before any credential work."""

        monkeypatch.setattr("backend.auth_users.verify_captcha", lambda *a, **k: False)
        resp = client.post(
            "/api/auth/login",
            json={"email": "a@b.com", "password": "Anyth1ng!long", "captcha_token": "bad"},
        )
        assert resp.status_code == 400
