"""Tests for the signed daily Merkle root — the compliance moat.

The manual's headline judgment #1 is that "the moat is the audit chain, not
the LLM" and §2.2 week 1 makes the signed daily Merkle root the single
highest-leverage compliance deliverable. This suite is the regression net
for that artifact. It exercises ``core/merkle.py`` end-to-end without a live
Postgres: a lightweight fake ``Session`` returns ``AuditEvent``-shaped rows so
we can drive ``build_daily_root`` and ``verify_signed_roots_against_db`` and,
critically, prove **tamper detection** — that rewriting a Postgres audit row
after the fact makes the recomputed root diverge from the signed root.

The fake session deliberately ignores the WHERE/ORDER clauses (we control the
returned rows directly); ``_events_for_day`` only reads row attributes, so the
projection logic and Merkle math are exercised faithfully.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from core import merkle


# ---------------------------------------------------------------------------
# Fake DB session (no Postgres required)
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):  # noqa: D401 - chainable no-op
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy Session over ``audit_events``."""

    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


def _row(event_id, event_type, payload, *, prev, crypto, hour=12, tenant_id=None):
    return SimpleNamespace(
        event_id=event_id,
        tenant_id=tenant_id,
        event_type=event_type,
        timestamp=datetime(2026, 6, 1, hour, 0, 0, tzinfo=timezone.utc),
        previous_hash=prev,
        cryptographic_hash=crypto,
        payload=payload,
    )


def _sample_rows():
    return [
        _row(1, "shadow_mode_rcm_completed", {"recovered_revenue": 11000.0}, prev="GENESIS", crypto="a" * 64, hour=8),
        _row(2, "hcc_suggestion_abstained", {"abstained_count": 1}, prev="a" * 64, crypto="b" * 64, hour=9),
        _row(3, "human_approval_granted", {"suggestion": "E11.22"}, prev="b" * 64, crypto="c" * 64, hour=10),
    ]


DAY = date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fresh_signer():
    """Drop the cached signer before and after each test (env may change)."""
    merkle.reset_signer_cache()
    yield
    merkle.reset_signer_cache()


# ---------------------------------------------------------------------------
# Leaf / tree primitives
# ---------------------------------------------------------------------------


def test_leaf_hash_is_deterministic_and_payload_sensitive():
    event = {
        "event_id": 1,
        "event_type": "shadow_mode_rcm_completed",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "previous_hash": "GENESIS",
        "cryptographic_hash": "a" * 64,
        "payload": {"recovered_revenue": 11000.0},
    }
    h1 = merkle.leaf_hash(event)
    h2 = merkle.leaf_hash(dict(event))
    assert h1 == h2  # deterministic
    assert len(h1) == 64

    tampered = dict(event, payload={"recovered_revenue": 99999.0})
    assert merkle.leaf_hash(tampered) != h1  # payload change flips the leaf


def test_leaf_hash_ignores_display_only_fields():
    base = {
        "event_id": 1,
        "event_type": "x",
        "timestamp": "t",
        "previous_hash": "p",
        "cryptographic_hash": "c",
        "payload": {"k": "v"},
    }
    # Fields outside the integrity projection must not change the leaf.
    with_extra = dict(base, actor_id="alice", request_id="req-123")
    assert merkle.leaf_hash(with_extra) == merkle.leaf_hash(base)


def test_compute_merkle_root_empty_single_and_order_sensitive():
    assert merkle.compute_merkle_root([]) == merkle.EMPTY_TREE_ROOT

    leaf = "d" * 64
    assert merkle.compute_merkle_root([leaf]) == leaf  # single leaf is its own root

    a, b, c = "a" * 64, "b" * 64, "c" * 64
    root_abc = merkle.compute_merkle_root([a, b, c])
    assert len(root_abc) == 64
    assert merkle.compute_merkle_root([a, b, c]) == root_abc  # stable
    assert merkle.compute_merkle_root([c, b, a]) != root_abc  # order matters


def test_compute_merkle_root_rejects_malformed_leaf():
    with pytest.raises(ValueError):
        merkle.compute_merkle_root(["not-a-valid-hash"])


# ---------------------------------------------------------------------------
# Signers
# ---------------------------------------------------------------------------


def test_hmac_dev_signer_roundtrip_and_rejects_tamper(monkeypatch):
    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    monkeypatch.setenv("BUDDI_STORAGE_KEY", "unit-test-storage-key")
    merkle.reset_signer_cache()

    signer = merkle.get_signer()
    assert signer.algorithm == "hmac-sha256-dev"

    root = "e" * 64
    envelope = signer.sign(root, "2026-06-01", 3)
    assert signer.verify(envelope, "2026-06-01", root, 3) is True
    # Any change to the signed triple must fail verification.
    assert signer.verify(envelope, "2026-06-01", "f" * 64, 3) is False
    assert signer.verify(envelope, "2026-06-01", root, 4) is False


def test_ed25519_signer_roundtrip(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path / "audit_root_signing.pem"
    key_path.write_bytes(pem)

    monkeypatch.setenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", str(key_path))
    merkle.reset_signer_cache()

    signer = merkle.get_signer()
    assert signer.algorithm == "ed25519"
    assert signer.public_key_pem and "BEGIN PUBLIC KEY" in signer.public_key_pem

    root = "1" * 64
    envelope = signer.sign(root, "2026-06-01", 2)
    assert signer.verify(envelope, "2026-06-01", root, 2) is True
    assert signer.verify(envelope, "2026-06-01", "2" * 64, 2) is False


def test_production_requires_configured_signer(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("BUDDI_AUDIT_KMS_PROVIDER", raising=False)
    monkeypatch.delenv("BUDDI_AUDIT_KMS_KEY", raising=False)
    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    merkle.reset_signer_cache()

    with pytest.raises(RuntimeError, match="Production audit root signing requires"):
        merkle.get_signer()


# ---------------------------------------------------------------------------
# Daily-root build / export / verify against the DB
# ---------------------------------------------------------------------------


def test_build_export_and_verify_clean_day(tmp_path, monkeypatch):
    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    merkle.reset_signer_cache()

    db = _FakeSession(_sample_rows())
    daily = merkle.build_daily_root(db, DAY)
    assert daily.event_count == 3
    assert daily.merkle_root != merkle.EMPTY_TREE_ROOT
    assert daily.signature["algorithm"] == "hmac-sha256-dev"

    path = merkle.export_daily_root(daily, base_dir=tmp_path)
    assert path.exists()
    assert merkle.list_signed_root_days(base_dir=tmp_path) == ["2026-06-01"]

    # Round-trip the envelope.
    reloaded = merkle.load_signed_root("2026-06-01", base_dir=tmp_path)
    assert reloaded is not None
    assert reloaded.merkle_root == daily.merkle_root

    # Verify the signed root against the same (untampered) DB rows.
    report = merkle.verify_signed_roots_against_db(db, base_dir=tmp_path)
    assert report["verified"] is True
    assert report["checked_days"] == 1
    day_report = report["days"][0]
    assert day_report["signature_valid"] is True
    assert day_report["root_matches_db"] is True


def test_tamper_detection_breaks_verification(tmp_path, monkeypatch):
    """The crown-jewel test: a DBA who rewrites an audit row is caught.

    We sign the root over the original rows, then verify against a DB whose
    rows have been mutated after the fact. The recomputed Merkle root must no
    longer match the signed root, so the day fails verification even though
    the signature itself is still valid over the *original* signed triple.
    """
    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    merkle.reset_signer_cache()

    original = _FakeSession(_sample_rows())
    daily = merkle.build_daily_root(original, DAY)
    merkle.export_daily_root(daily, base_dir=tmp_path)

    # An attacker with UPDATE privilege rewrites the recovered_revenue on the
    # first event (e.g. to inflate a recovery metric) without touching the
    # signed root file.
    tampered_rows = _sample_rows()
    tampered_rows[0].payload = {"recovered_revenue": 500000.0}
    tampered = _FakeSession(tampered_rows)

    report = merkle.verify_signed_roots_against_db(tampered, base_dir=tmp_path)
    assert report["verified"] is False
    day_report = report["days"][0]
    assert day_report["root_matches_db"] is False  # recomputed root diverged
    assert day_report["signature_valid"] is True  # signature over original triple still valid
    assert day_report["persisted_root"] != day_report["recomputed_root"]


def test_empty_day_is_still_signable(tmp_path, monkeypatch):
    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    merkle.reset_signer_cache()

    db = _FakeSession([])
    daily = merkle.build_daily_root(db, DAY)
    assert daily.event_count == 0
    assert daily.merkle_root == merkle.EMPTY_TREE_ROOT

    merkle.export_daily_root(daily, base_dir=tmp_path)
    report = merkle.verify_signed_roots_against_db(db, base_dir=tmp_path)
    assert report["verified"] is True


def test_tenant_root_uses_tenant_path_and_signature_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    merkle.reset_signer_cache()

    tenant_id = str(uuid.uuid4())
    rows = _sample_rows()
    for row in rows:
        row.tenant_id = tenant_id
    db = _FakeSession(rows)

    daily = merkle.build_daily_root(db, DAY, tenant_id=tenant_id)
    assert daily.tenant_id == tenant_id
    assert daily.signature["tenant_id"] == tenant_id

    path = merkle.export_daily_root(daily, base_dir=tmp_path)
    assert f"tenants/{tenant_id}/2026/06" in path.as_posix()
    assert merkle.list_signed_root_days(base_dir=tmp_path) == []
    assert merkle.list_signed_root_days(base_dir=tmp_path, tenant_id=tenant_id) == [
        "2026-06-01"
    ]

    report = merkle.verify_signed_roots_against_db(
        db,
        base_dir=tmp_path,
        tenant_id=tenant_id,
    )
    assert report["verified"] is True
    assert report["days"][0]["tenant_id"] == tenant_id


# ---------------------------------------------------------------------------
# KMS-backed signing (GCP / AWS) — verified OFFLINE against the embedded
# public key, so no live KMS is required for the verification path.
# ---------------------------------------------------------------------------


def _ec_p256_key():
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.generate_private_key(ec.SECP256R1())


class _FakeAwsKms:
    """Mimics the boto3 KMS surface (``get_public_key`` / ``sign``) with a
    real local EC P-256 key, so the production code path runs end-to-end."""

    def __init__(self, private_key):
        self._priv = private_key
        self._pub = private_key.public_key()

    def get_public_key(self, KeyId):  # noqa: N803 - boto3 kwarg casing
        from cryptography.hazmat.primitives import serialization

        der = self._pub.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return {"PublicKey": der, "KeySpec": "ECC_NIST_P256", "SigningAlgorithms": ["ECDSA_SHA_256"]}

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):  # noqa: N803
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec

        assert MessageType == "RAW"
        assert SigningAlgorithm == "ECDSA_SHA_256"
        return {"Signature": self._priv.sign(Message, ec.ECDSA(hashes.SHA256()))}


class _FakeGcpKms:
    """Mimics the GCP KMS surface (``get_public_key`` / ``asymmetric_sign``)."""

    def __init__(self, private_key):
        self._priv = private_key
        self._pub = private_key.public_key()

    def get_public_key(self, name=None):
        from cryptography.hazmat.primitives import serialization

        pem = self._pub.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        return SimpleNamespace(pem=pem, algorithm=SimpleNamespace(name="EC_SIGN_P256_SHA256"))

    def asymmetric_sign(self, name=None, digest: dict[str, bytes] | None = None):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

        # GCP signs the digest we computed; sign it as a prehash so the result
        # verifies as ECDSA-SHA256 over the original message.
        assert digest is not None
        signature = self._priv.sign(digest["sha256"], ec.ECDSA(Prehashed(hashes.SHA256())))
        return SimpleNamespace(signature=signature)


def test_verify_envelope_offline_for_ecdsa_p256():
    """The auditor path: verify a KMS-style ECDSA signature using only the
    public key carried in the envelope — no KMS, no shared secret."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = _ec_p256_key()
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    root, day, count = "a" * 64, "2026-06-01", 3
    message = merkle.MerkleSigner._canonical_message(day, root, count)
    signature = key.sign(message, ec.ECDSA(hashes.SHA256()))
    import base64

    envelope = {
        "algorithm": "ecdsa-p256-sha256",
        "signature_b64": base64.b64encode(signature).decode("ascii"),
        "public_key_pem": pub_pem,
    }
    assert merkle.verify_envelope(envelope, day, root, count) is True
    # Any change to the signed triple, or to the signature, fails closed.
    assert merkle.verify_envelope(envelope, day, "b" * 64, count) is False
    assert merkle.verify_envelope(envelope, day, root, count + 1) is False
    assert merkle.verify_envelope({**envelope, "signature_b64": "AAAA"}, day, root, count) is False


def test_aws_kms_signer_roundtrip(monkeypatch):
    key = _ec_p256_key()
    monkeypatch.setattr(merkle, "_aws_kms_client", lambda: _FakeAwsKms(key))

    signer = merkle.MerkleSigner._aws_kms_signer("arn:aws:kms:us-east-1:123:key/abc")
    assert signer.algorithm == "ecdsa-p256-sha256"
    assert signer.kms_provider == "aws"
    assert signer.public_key_pem and "BEGIN PUBLIC KEY" in signer.public_key_pem

    root = "c" * 64
    envelope = signer.sign(root, "2026-06-01", 5)
    assert envelope["kms_provider"] == "aws"
    assert signer.verify(envelope, "2026-06-01", root, 5) is True
    assert signer.verify(envelope, "2026-06-01", "d" * 64, 5) is False


def test_gcp_kms_signer_roundtrip(monkeypatch):
    key = _ec_p256_key()
    monkeypatch.setattr(merkle, "_gcp_kms_client", lambda: _FakeGcpKms(key))

    signer = merkle.MerkleSigner._gcp_kms_signer(
        "projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1"
    )
    assert signer.algorithm == "ecdsa-p256-sha256"
    assert signer.kms_provider == "gcp"

    root = "e" * 64
    envelope = signer.sign(root, "2026-06-01", 2)
    assert signer.verify(envelope, "2026-06-01", root, 2) is True
    assert signer.verify(envelope, "2026-06-01", root, 3) is False


def test_kms_signed_root_builds_exports_and_verifies(tmp_path, monkeypatch):
    """End-to-end with an AWS-KMS-resolved signer: build → export → verify,
    plus tamper detection. Verification re-derives the root from the DB and
    checks the ECDSA signature offline against the envelope's public key."""
    key = _ec_p256_key()
    monkeypatch.setattr(merkle, "_aws_kms_client", lambda: _FakeAwsKms(key))
    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    monkeypatch.setenv("BUDDI_AUDIT_KMS_PROVIDER", "aws")
    monkeypatch.setenv("BUDDI_AUDIT_KMS_KEY", "arn:aws:kms:us-east-1:123:key/abc")
    merkle.reset_signer_cache()

    db = _FakeSession(_sample_rows())
    daily = merkle.build_daily_root(db, DAY)
    assert daily.signature["algorithm"] == "ecdsa-p256-sha256"
    assert daily.signature["kms_provider"] == "aws"
    assert daily.signature["public_key_pem"]
    merkle.export_daily_root(daily, base_dir=tmp_path)

    report = merkle.verify_signed_roots_against_db(db, base_dir=tmp_path)
    assert report["verified"] is True
    assert report["days"][0]["signature_valid"] is True
    assert report["days"][0]["algorithm"] == "ecdsa-p256-sha256"

    tampered_rows = _sample_rows()
    tampered_rows[0].payload = {"recovered_revenue": 9_000_000.0}
    tamper_report = merkle.verify_signed_roots_against_db(
        _FakeSession(tampered_rows), base_dir=tmp_path
    )
    assert tamper_report["verified"] is False
    assert tamper_report["days"][0]["root_matches_db"] is False
    assert tamper_report["days"][0]["signature_valid"] is True  # still valid over original triple


# ---------------------------------------------------------------------------
# Object Lock (WORM) export mirror
# ---------------------------------------------------------------------------


class _FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"ETag": "fake"}


def test_export_mirrors_to_s3_object_lock(tmp_path, monkeypatch):
    import json as _json

    monkeypatch.delenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", raising=False)
    merkle.reset_signer_cache()

    fake = _FakeS3()
    monkeypatch.setattr(merkle, "_s3_client", lambda: fake)
    monkeypatch.setenv("BUDDI_AUDIT_ROOTS_BUCKET", "s3://buddi-audit-roots/sealed")
    monkeypatch.setenv("BUDDI_AUDIT_OBJECT_LOCK_MODE", "COMPLIANCE")
    monkeypatch.setenv("BUDDI_AUDIT_OBJECT_LOCK_DAYS", "2555")

    db = _FakeSession(_sample_rows())
    daily = merkle.build_daily_root(db, DAY)
    path = merkle.export_daily_root(daily, base_dir=tmp_path)

    # Local canonical copy still written.
    assert path.exists()
    # ...and mirrored to the WORM bucket with an Object Lock retention header.
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["Bucket"] == "buddi-audit-roots"
    assert call["Key"] == "sealed/2026/06/2026-06-01.root.json"
    assert call["ObjectLockMode"] == "COMPLIANCE"
    assert call["ObjectLockRetainUntilDate"] > datetime.now(timezone.utc)
    body = _json.loads(call["Body"].decode("utf-8"))
    assert body["merkle_root"] == daily.merkle_root
    assert daily.object_lock_uri == "s3://buddi-audit-roots/sealed/2026/06/2026-06-01.root.json"


def test_export_skips_object_lock_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.delenv("BUDDI_AUDIT_ROOTS_BUCKET", raising=False)
    merkle.reset_signer_cache()

    db = _FakeSession(_sample_rows())
    daily = merkle.build_daily_root(db, DAY)
    merkle.export_daily_root(daily, base_dir=tmp_path)
    assert daily.object_lock_uri is None


def test_export_reraises_on_object_lock_failure(tmp_path, monkeypatch):
    """A failed immutable-archive write must surface, not be swallowed."""

    def _boom():
        raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(merkle, "_s3_client", _boom)
    monkeypatch.setenv("BUDDI_AUDIT_ROOTS_BUCKET", "s3://buddi-audit-roots")
    merkle.reset_signer_cache()

    db = _FakeSession(_sample_rows())
    daily = merkle.build_daily_root(db, DAY)
    with pytest.raises(RuntimeError, match="bucket unreachable"):
        merkle.export_daily_root(daily, base_dir=tmp_path)
