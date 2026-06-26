"""Encrypted compatibility envelopes for PHI-bearing DB fields.

The schema still uses JSONB/Text columns for jobs and LLM artifacts, so this
module encrypts values inside those existing columns and keeps legacy plaintext
rows readable. New writes should pass through these helpers before persistence;
read paths should decode with the matching helper instead of touching ORM
attributes directly.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from core.storage import SecureStorage

JSON_MARKER = "securestorage-json:v1"
TEXT_PREFIX = "enc:securestorage-text:v1:"


def _storage() -> SecureStorage:
    return SecureStorage()


def encrypt_json_value(value: Any) -> Any:
    """Return an encrypted JSON-compatible envelope for ``value``."""

    if value is None or is_encrypted_json_value(value):
        return value
    plaintext = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    ciphertext = _storage().encrypt_blob(plaintext)
    return {
        "_buddi_encrypted": JSON_MARKER,
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def is_encrypted_json_value(value: Any) -> bool:
    return isinstance(value, dict) and value.get("_buddi_encrypted") == JSON_MARKER


def decrypt_json_value(value: Any) -> Any:
    """Decode an encrypted JSON envelope, or return legacy plaintext unchanged."""

    if not is_encrypted_json_value(value):
        return value
    ciphertext = base64.b64decode(str(value.get("ciphertext") or ""))
    plaintext = _storage().decrypt_blob(ciphertext)
    return json.loads(plaintext)


def encrypt_text_value(value: str | None) -> str | None:
    """Return encrypted text suitable for a Text column."""

    if value is None or value.startswith(TEXT_PREFIX):
        return value
    ciphertext = _storage().encrypt_blob(value)
    return TEXT_PREFIX + base64.b64encode(ciphertext).decode("ascii")


def decrypt_text_value(value: str | None) -> str | None:
    """Decode encrypted text, or return legacy plaintext unchanged."""

    if value is None or not value.startswith(TEXT_PREFIX):
        return value
    ciphertext = base64.b64decode(value[len(TEXT_PREFIX):])
    return _storage().decrypt_blob(ciphertext)


__all__ = [
    "JSON_MARKER",
    "TEXT_PREFIX",
    "decrypt_json_value",
    "decrypt_text_value",
    "encrypt_json_value",
    "encrypt_text_value",
    "is_encrypted_json_value",
]
