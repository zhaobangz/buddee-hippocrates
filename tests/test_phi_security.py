"""Focused PHI-processing and encrypted-field security tests."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from core import phi_guard
from core.secure_fields import (
    TEXT_PREFIX,
    decrypt_json_value,
    decrypt_text_value,
    encrypt_json_value,
    encrypt_text_value,
    is_encrypted_json_value,
)


TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_encrypted_json_envelope_roundtrip():
    payload = {"note": "patient has diabetes", "billed_codes": ["E11.9"]}
    encrypted = encrypt_json_value(payload)

    assert encrypted != payload
    assert is_encrypted_json_value(encrypted)
    assert "patient has diabetes" not in str(encrypted)
    assert decrypt_json_value(encrypted) == payload
    assert decrypt_json_value(payload) == payload


def test_encrypted_text_roundtrip():
    raw = "clinical note text"
    encrypted = encrypt_text_value(raw)

    assert encrypted is not None
    assert encrypted.startswith(TEXT_PREFIX)
    assert raw not in encrypted
    assert decrypt_text_value(encrypted) == raw
    assert decrypt_text_value(raw) == raw


def test_phi_gate_blocks_when_global_baa_missing(monkeypatch):
    monkeypatch.delenv("BUDDI_BAA_CONFIRMED", raising=False)
    with pytest.raises(phi_guard.PHIProcessingNotAllowed, match="Global provider BAA"):
        phi_guard.assert_phi_processing_allowed(MagicMock(), TENANT)


def test_phi_gate_allows_synthetic_without_baa(monkeypatch):
    monkeypatch.delenv("BUDDI_BAA_CONFIRMED", raising=False)
    phi_guard.assert_phi_processing_allowed(MagicMock(), TENANT, synthetic=True)


def test_phi_gate_requires_tenant_baa(monkeypatch):
    monkeypatch.setenv("BUDDI_BAA_CONFIRMED", "1")
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = False

    with pytest.raises(phi_guard.PHIProcessingNotAllowed, match="Tenant BAA"):
        phi_guard.assert_phi_processing_allowed(db, TENANT)
