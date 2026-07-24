"""
Buddi System Configuration v4 — Production-hardened (SEC-03, SEC-05).

Uses pydantic-settings so that every security-critical environment variable is
validated at startup. Missing or obviously-insecure values raise a clear error
before the app ever binds to a port, which is the HIPAA-safe posture.
"""

from __future__ import annotations

import os
import sys
import warnings
from typing import List, Optional

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.secrets_loader import load_secrets_dir


class Settings(BaseSettings):
    """Single source of truth for runtime configuration.

    ``SECRET_KEY`` and ``BUDDI_STORAGE_KEY`` are both marked mandatory — the
    application intentionally refuses to start without them so that PHI can
    never be signed or encrypted with a publicly known default.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Identity ---
    ASSISTANT_NAME: str = "Buddi Clinical Agent"
    VERSION: str = "4.0.0"

    # --- Security (mandatory) ---
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="HMAC signing key for JWT/API tokens. No default.",
    )
    BUDDI_STORAGE_KEY: str = Field(
        ...,
        min_length=16,
        description="Master passphrase for at-rest PHI encryption. No default.",
    )
    API_KEY: Optional[str] = Field(
        default=None,
        description="Static API key for server-to-server access. If unset, "
        "bearer-token mode is used.",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # --- Portal user auth (invite-only email+password+hCaptcha login) ---
    # Dedicated JWT signing secret for portal session tokens. Optional: when
    # unset, a domain-separated key is derived from SECRET_KEY (see
    # core/user_auth._signing_key) so existing deployments keep working; set
    # it explicitly to rotate portal sessions independently of anything else
    # signed with SECRET_KEY.
    BUDDI_JWT_SECRET: Optional[str] = Field(
        default=None,
        description="HS256 signing secret for portal session JWTs.",
    )
    BUDDI_JWT_ACCESS_MINUTES: int = 15
    BUDDI_JWT_REFRESH_DAYS: int = 14
    # hCaptcha secret for the siteverify call on login/signup. Required in
    # production — the verifier fails closed without it. In
    # development/test, BUDDI_CAPTCHA_DISABLED=1 skips verification (that
    # flag is ignored when ENVIRONMENT=production, mirroring the phi_guard
    # break-glass discipline).
    HCAPTCHA_SECRET_KEY: str = ""
    HCAPTCHA_SITEKEY: str = ""
    BUDDI_INVITE_EXPIRY_HOURS: int = 48

    # --- CORS (SEC-01) ---
    CORS_ORIGINS: str = ""

    # --- LLM ---
    # Manual §2.2 week 2: Anthropic is the primary provider; OpenAI is the
    # embeddings-only fallback. core/llm_manager.py reads these.
    LLM_PROVIDER: str = "anthropic"
    LLM_API_URL: str = "https://api.openai.com/v1/chat/completions"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "claude-opus-4-8"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-4-8"
    OPENAI_API_KEY: str = ""
    OPENAI_EMBED_MODEL: str = "text-embedding-3-large"

    # Tier-based model routing — separates the high-stakes reasoning /
    # safety-arbitration path (Opus) from the high-volume HCC/ICD coding
    # suggestion path (Sonnet). core/llm_manager.py reads these.
    #   * reasoning tier — confidence-floor adjudication, prior-auth drafts,
    #     and anything that directly faces a payer. Defaults to Opus 4.8.
    #   * coding tier — first-pass HCC shadow-audit suggestions and free-text
    #     rationale narration. Defaults to Sonnet 4.6 (no extended thinking).
    ANTHROPIC_ROUTING_MODEL: str = "claude-opus-4-8"
    ANTHROPIC_CODING_MODEL: str = "claude-sonnet-4-6"

    # --- Stripe billing (PROMPT_04 / strategy-doc §2.1 gap #10) ---
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID_MONTHLY: str = ""
    STRIPE_PRICE_ID_GAIN_SHARE: str = ""

    # --- Storage / Memory ---
    MEMORY_ENABLED: bool = True
    MAX_MEMORY_HISTORY: int = 10
    STORAGE_DIR: str = "data"

    # --- Infrastructure ---
    BACKEND_PORT: int = 8001
    FRONTEND_PORT: int = 5173
    # SEC-04: DATABASE_URL is validated below. The default here is only used
    # in test mode; production startup requires an explicit env var pointing
    # at a database that is NOT the insecure ``postgres:postgres`` default.
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/buddi"


    # --- Safety & Audit ---
    ENABLE_AUDIT_LOG: bool = True
    AUDIT_LOG_FILE: str = "audit_log.json"
    ENABLE_SAFETY_LAYER: bool = True
    REQUIRE_HUMAN_APPROVAL: bool = True

    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_insecure_secret(cls, v: str) -> str:
        bad = {"change-me", "super-secret-key-for-jwt-change-in-prod", "dev", "secret"}
        if v.strip().lower() in bad:
            raise ValueError(
                "SECRET_KEY is set to an insecure default. Generate one with "
                "`python -c \"import secrets; print(secrets.token_hex(32))\"`."
            )
        return v

    @field_validator("BUDDI_STORAGE_KEY")
    @classmethod
    def _reject_insecure_storage_key(cls, v: str) -> str:
        if v.strip().lower() in {"clinical-dev-key-not-for-prod", "change-me", "dev"}:
            raise ValueError("BUDDI_STORAGE_KEY must not be the dev default.")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def _reject_insecure_database_url(cls, v: str) -> str:
        """SEC-04: refuse the ``postgres:postgres`` fallback outside test mode.

        The ``BUDDI_TEST_MODE=1`` escape hatch lets CI and local tests keep
        using the throwaway compose database. Any other environment must set
        ``DATABASE_URL`` explicitly to a dedicated credential — a database
        exposed with ``postgres:postgres`` is effectively public.
        """
        if os.getenv("BUDDI_TEST_MODE") == "1":
            return v
        lowered = v.strip().lower()
        if not lowered:
            raise ValueError(
                "DATABASE_URL must be set explicitly. Set it to a connection "
                "string pointing at a dedicated Postgres credential."
            )
        if "postgres:postgres@" in lowered:
            raise ValueError(
                "DATABASE_URL is using the insecure `postgres:postgres` "
                "default. Provision a dedicated DB user / password and set "
                "DATABASE_URL to that connection string before starting the "
                "service."
            )
        return v


    @property
    def cors_origin_list(self) -> List[str]:
        """Parsed, de-duplicated list of allowed CORS origins."""
        raw = os.getenv("CORS_ORIGINS", self.CORS_ORIGINS)
        return [o.strip() for o in raw.split(",") if o.strip()]


def _assert_test_mode_allowed() -> None:
    """C-3: refuse test mode on any deployed, reachable environment.

    ``BUDDI_TEST_MODE=1`` injects well-known secrets and (outside production)
    enables a plaintext static API-key fallback. That is safe for local dev
    and CI, but catastrophic on a deployed container. Hard-fail when running
    on Cloud Run (``K_SERVICE`` is always present there) or when
    ``ENVIRONMENT`` is explicitly ``production`` / ``staging``. An unset
    ``ENVIRONMENT`` (local scripts, CI jobs) is tolerated but still triggers
    the startup warning in ``_load_settings``.
    """

    if os.getenv("BUDDI_TEST_MODE") != "1":
        return
    if os.getenv("K_SERVICE"):
        raise RuntimeError(
            "BUDDI_TEST_MODE=1 is set on Cloud Run (K_SERVICE is present). "
            "Test mode injects well-known secrets and enables a static "
            "API-key fallback. Remove BUDDI_TEST_MODE from the service "
            "manifest — production must load secrets via SECRETS_DIR."
        )
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if environment in {"production", "staging"}:
        raise RuntimeError(
            f"BUDDI_TEST_MODE=1 is set with ENVIRONMENT={environment!r}. "
            "Test mode is only permitted for local development and CI "
            "(ENVIRONMENT must be 'test' or 'development')."
        )


def _load_settings() -> Settings:
    """Load settings with a test-mode escape hatch so unit tests don't need
    real production secrets, while production startup still fails loudly if
    ``SECRET_KEY`` / ``BUDDI_STORAGE_KEY`` are missing."""
    # C-1: map Cloud Run file-mounted secrets into the environment *before*
    # validation, so the service boots from Secret Manager mounts instead of
    # plaintext env vars (see core/secrets_loader.py).
    load_secrets_dir()
    _assert_test_mode_allowed()
    if os.getenv("BUDDI_TEST_MODE") == "1" and not os.getenv("CI") and "pytest" not in sys.modules:
        warnings.warn(
            "BUDDI_TEST_MODE=1 is set outside CI — ensure this is not production.",
            stacklevel=2,
        )  # Security: surface accidental test-mode auth bypasses during startup.
    if os.getenv("BUDDI_TEST_MODE") == "1" and not (
        os.getenv("CI") and "pytest" not in sys.modules
    ):
        # C-3: never inject well-known secrets into a CI process that is not
        # actually running pytest (e.g. a smoke container built by CI). Such
        # processes must receive real secrets via env / SECRETS_DIR — and
        # Settings() below fails loudly when they don't.
        os.environ.setdefault(
            "SECRET_KEY",
            "test-only-secret-key-not-for-production-use-0123456789abcdef",
        )
        os.environ.setdefault("BUDDI_STORAGE_KEY", "test-only-storage-key-not-for-prod")
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as e:
        problem_fields = sorted(
            {
                str(error.get("loc", ["unknown"])[0])
                for error in e.errors()
                if error.get("loc")
            }
        )
        missing = ", ".join(problem_fields) if problem_fields else "unknown"
        print(
            "Buddi configuration error: Missing or invalid required env vars: "
            f"{missing} — copy .env.example to .env and fill in the values.",
            file=sys.stderr,
        )
        raise


settings = _load_settings()


# --- Back-compat shim ---------------------------------------------------------
# A handful of legacy modules still import ``Config`` as a class-attribute
# namespace. Expose the settings instance as a drop-in so those imports keep
# working without leaking the pydantic-settings surface.
class _ConfigProxy:
    def __getattr__(self, item: str):
        return getattr(settings, item)


Config = _ConfigProxy()
