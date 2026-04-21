"""
Buddi System Configuration v4 — Production-hardened (SEC-03, SEC-05).

Uses pydantic-settings so that every security-critical environment variable is
validated at startup. Missing or obviously-insecure values raise a clear error
before the app ever binds to a port, which is the HIPAA-safe posture.
"""

from __future__ import annotations

import os
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- CORS (SEC-01) ---
    CORS_ORIGINS: str = ""

    # --- LLM ---
    LLM_PROVIDER: str = "openai"
    LLM_API_URL: str = "https://api.openai.com/v1/chat/completions"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4-turbo"

    # --- Storage / Memory ---
    MEMORY_ENABLED: bool = True
    MAX_MEMORY_HISTORY: int = 10
    STORAGE_DIR: str = "data"

    # --- Infrastructure ---
    BACKEND_PORT: int = 8001
    FRONTEND_PORT: int = 5173
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

    @property
    def cors_origin_list(self) -> List[str]:
        """Parsed, de-duplicated list of allowed CORS origins."""
        raw = os.getenv("CORS_ORIGINS", self.CORS_ORIGINS)
        return [o.strip() for o in raw.split(",") if o.strip()]


def _load_settings() -> Settings:
    """Load settings with a test-mode escape hatch so unit tests don't need
    real production secrets, while production startup still fails loudly if
    ``SECRET_KEY`` / ``BUDDI_STORAGE_KEY`` are missing."""
    if os.getenv("BUDDI_TEST_MODE") == "1":
        os.environ.setdefault(
            "SECRET_KEY",
            "test-only-secret-key-not-for-production-use-0123456789abcdef",
        )
        os.environ.setdefault("BUDDI_STORAGE_KEY", "test-only-storage-key-not-for-prod")
    return Settings()  # type: ignore[call-arg]


settings = _load_settings()


# --- Back-compat shim ---------------------------------------------------------
# A handful of legacy modules still import ``Config`` as a class-attribute
# namespace. Expose the settings instance as a drop-in so those imports keep
# working without leaking the pydantic-settings surface.
class _ConfigProxy:
    def __getattr__(self, item: str):
        return getattr(settings, item)


Config = _ConfigProxy()
