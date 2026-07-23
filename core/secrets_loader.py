"""Cloud Run secrets-file bootstrap (audit C-1 / Quick-Win 7).

Cloud Run mounts Secret Manager values as files (see the
``run.googleapis.com/secrets`` annotation in ``infra/cloud-run-api.yaml``)
and sets ``SECRETS_DIR=/secrets``. The application otherwise reads secrets
exclusively from environment variables, so without this bridge a literal
apply of the manifests would boot with no secrets at all (or tempt an
operator to "fix" it by pasting plaintext secrets into env vars).

At settings-load time, well-known filenames under ``SECRETS_DIR`` are mapped
into the environment **without overriding variables that are already set**
(real env always wins, so local dev and tests are unaffected).

Security properties:

* Values are never logged — only the names of the env vars that were loaded.
* Existing environment variables take precedence over files (no surprise
  overrides from a stale mount).
* In production, an explicitly-configured ``SECRETS_DIR`` that does not
  exist is a hard error: that combination means the operator expected
  file-mounted secrets that will never arrive, and booting anyway would
  either crash later or silently fall back to a stale template value.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, MutableMapping, Optional

logger = logging.getLogger(__name__)

#: Maps secret filenames (as mounted by infra/cloud-run-*.yaml) to the
#: environment variable the application actually reads. Keep in sync with
#: the ``run.googleapis.com/secrets`` annotations and infra/env.tier2.example.
SECRET_FILE_ENV_MAP: Dict[str, str] = {
    "database-url": "DATABASE_URL",
    "secret-key": "SECRET_KEY",
    "storage-key": "BUDDI_STORAGE_KEY",
    "api-key": "API_KEY",
    "anthropic-key": "ANTHROPIC_API_KEY",
    "openai-key": "OPENAI_API_KEY",
    "redis-url": "REDIS_URL",
}


def load_secrets_dir(
    secrets_dir: Optional[str] = None,
    *,
    environ: Optional[MutableMapping[str, str]] = None,
) -> List[str]:
    """Map well-known secret files under ``secrets_dir`` into ``environ``.

    Returns the list of env var names populated from files. Never overrides
    a variable that is already set. Raises ``RuntimeError`` when
    ``ENVIRONMENT=production`` and the configured directory is missing —
    fail closed on a broken secrets mount.
    """

    env: MutableMapping[str, str] = os.environ if environ is None else environ
    raw_dir = (secrets_dir if secrets_dir is not None else env.get("SECRETS_DIR", "")).strip()
    if not raw_dir:
        return []

    root = Path(raw_dir)
    if not root.is_dir():
        if env.get("ENVIRONMENT", "production").strip().lower() == "production":
            raise RuntimeError(
                f"SECRETS_DIR={raw_dir!r} is set but the directory does not exist. "
                "Secret Manager mounts are missing — refusing to boot without "
                "production secrets. Fix the run.googleapis.com/secrets "
                "annotation or unset SECRETS_DIR."
            )
        logger.warning("SECRETS_DIR=%s is set but missing; skipping secrets-file load.", raw_dir)
        return []

    loaded: List[str] = []
    for filename, env_name in SECRET_FILE_ENV_MAP.items():
        if env.get(env_name):
            continue  # real environment wins; never override
        path = root / filename
        try:
            value = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.error("Failed reading secret file %s: %s", path, exc)
            continue
        if not value:
            logger.warning("Secret file %s is empty; leaving %s unset.", path, env_name)
            continue
        env[env_name] = value
        loaded.append(env_name)

    if loaded:
        # Names only — secret values must never touch the log stream.
        logger.info(
            "Loaded %d secret(s) from %s: %s",
            len(loaded),
            raw_dir,
            ", ".join(sorted(loaded)),
        )
    return loaded


__all__ = ["SECRET_FILE_ENV_MAP", "load_secrets_dir"]
