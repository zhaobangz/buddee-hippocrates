"""Clinical Storage Utility — Production Hardening (SEC-05).

Provides encrypted I/O for sensitive patient data.

Security properties:
  * The master passphrase (``BUDDI_STORAGE_KEY``) has *no* default. If it is
    not set, construction raises ``ValueError`` so the process fails to start
    rather than silently encrypting PHI with a publicly known key.
  * Each record is encrypted with a fresh ``os.urandom(16)`` salt. The salt is
    stored as a prefix alongside the ciphertext, so every file is independently
    protected against pre-computed / rainbow-table attacks.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SALT_LEN = 16  # 128-bit salt, per NIST SP 800-132
PBKDF2_ITERATIONS = 200_000
logger = logging.getLogger(__name__)


class SecureStorage:
    """Envelope-encrypt JSON/text blobs with a per-record PBKDF2 salt."""

    def __init__(self, encryption_key: Optional[str] = None, allow_plaintext_fallback: bool = False):
        secret = encryption_key or os.getenv("BUDDI_STORAGE_KEY")
        if not secret:
            raise ValueError(
                "BUDDI_STORAGE_KEY is required for at-rest PHI encryption. "
                "Refusing to start without a configured key."
            )
        if secret.strip().lower() in {
            "clinical-dev-key-not-for-prod",
            "change-me",
            "dev",
        }:
            raise ValueError("BUDDI_STORAGE_KEY must not be a development default.")
        self._secret: bytes = secret.encode("utf-8")
        self._allow_plaintext_fallback = allow_plaintext_fallback

    # ------------------------------------------------------------------
    # Key derivation
    # ------------------------------------------------------------------
    def _derive_fernet(self, salt: bytes) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        derived = base64.urlsafe_b64encode(kdf.derive(self._secret))
        return Fernet(derived)

    def _encrypt(self, plaintext: bytes) -> bytes:
        salt = os.urandom(SALT_LEN)
        token = self._derive_fernet(salt).encrypt(plaintext)
        # Store [salt || ciphertext]. Fernet tokens are url-safe base64, so we
        # keep the salt as raw bytes and concatenate — readers split at offset
        # ``SALT_LEN``.
        return salt + token

    def _decrypt(self, blob: bytes) -> bytes:
        if len(blob) <= SALT_LEN:
            raise ValueError("Ciphertext too short — missing salt prefix.")
        salt, token = blob[:SALT_LEN], blob[SALT_LEN:]
        return self._derive_fernet(salt).decrypt(token)

    # ------------------------------------------------------------------
    # In-memory blobs (for DB BYTEA columns, e.g. ehr_integrations tokens)
    # ------------------------------------------------------------------
    def encrypt_blob(self, text: str) -> bytes:
        """Encrypt a string to a salted Fernet blob suitable for a BYTEA column."""

        return self._encrypt(text.encode("utf-8"))

    def decrypt_blob(self, blob: bytes) -> str:
        """Decrypt a blob produced by :meth:`encrypt_blob`."""

        return self._decrypt(bytes(blob)).decode("utf-8")

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------
    def save_json(self, file_path: str, data: Any) -> bool:
        try:
            json_data = json.dumps(data).encode("utf-8")
            with open(file_path, "wb") as f:
                f.write(self._encrypt(json_data))
            return True
        except (OSError, json.JSONDecodeError, TypeError) as e:
            logger.error("SecureStorage save_json failed for %s: %s", file_path, e)
            return False

    def load_json(self, file_path: str) -> Optional[Any]:
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "rb") as f:
                blob = f.read()
            # Graceful handling of legacy plain-JSON files left over from
            # pre-encryption runs.
            stripped = blob.strip()
            if self._allow_plaintext_fallback and (stripped.startswith(b"{") or stripped.startswith(b"[")):
                logger.warning(
                    "Plaintext SecureStorage fallback used for %s; re-encrypt this legacy file.",
                    file_path,
                )  # Security: operators must know when unencrypted legacy data is read.
                try:
                    return json.loads(blob.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    if b"\n" in stripped:
                        return [
                            json.loads(line)
                            for line in blob.decode("utf-8").split("\n")
                            if line.strip()
                        ]
            decrypted = self._decrypt(blob)
            return json.loads(decrypted.decode("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            logger.error("SecureStorage load_json failed for %s: %s", file_path, e)
            return None

    # ------------------------------------------------------------------
    # Text
    # ------------------------------------------------------------------
    def save_text(self, file_path: str, text: str) -> bool:
        try:
            with open(file_path, "wb") as f:
                f.write(self._encrypt(text.encode("utf-8")))
            return True
        except OSError as e:
            logger.error("SecureStorage save_text failed for %s: %s", file_path, e)
            return False

    def load_text(self, file_path: str) -> Optional[str]:
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "rb") as f:
                return self._decrypt(f.read()).decode("utf-8")
        except (OSError, ValueError) as e:
            logger.error("SecureStorage load_text failed for %s: %s", file_path, e)
            return None

    # ------------------------------------------------------------------
    # List append
    # ------------------------------------------------------------------
    def append_json(self, file_path: str, item: Any) -> bool:
        data = self.load_json(file_path) or []
        if not isinstance(data, list):
            data = [data]
        data.append(item)
        return self.save_json(file_path, data)

    def delete_text_file(self, file_path: str) -> bool:
        try:
            os.remove(file_path)
            return True
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.error("SecureStorage delete failed for %s: %s", file_path, e)
            return False
