"""Cryptographically signed daily Merkle root over the audit chain.

This module is the spine of the CMS / OIG-audit-grade artifact described in
``Buddi_Strategic_Founders_Operating_Manual.pdf §2.2 week 1`` and
``BUILD_PLAN.md`` §1 strategic bet #5:

    Hash-chained, write-once audit log: dedicated ``audit_events`` table
    where every row's hash = sha256(prev_hash || canonical_json(payload)),
    signed daily with an HSM-backed KMS key.

The row-level hash chain already lives on ``audit_events`` (see
``core.models.AuditEvent``). On its own it is only as trustworthy as the
DB role privilege — a DBA with UPDATE can rewrite history. The signed
Merkle root closes that gap: every 24h we

    1. Read the day's audit rows.
    2. Project each row into a canonical leaf (``leaf_hash``).
    3. Build a Merkle tree (``compute_merkle_root``).
    4. Sign the root with a signing key (``MerkleSigner``).
    5. Export the {day, root, signature, leaf_count, leaf_hashes} envelope
       to a path under ``BUDDI_AUDIT_ROOTS_DIR`` (defaults to
       ``storage/audit_roots/``). In production that directory should be
       a GCS / S3 bucket with Object Lock so the signed roots are
       *append-only* even if the DB is fully compromised.

Signing key resolution (``MerkleSigner.from_env()``), highest priority first:

    1. **Cloud KMS** — ``BUDDI_AUDIT_KMS_PROVIDER`` (``gcp`` | ``aws``) +
       ``BUDDI_AUDIT_KMS_KEY`` (the GCP CryptoKeyVersion resource name or the
       AWS KMS key id / ARN). This is the production posture the manual
       recommends: the private key never leaves the HSM. Crucially, the
       *public* half is fetched once at startup and embedded in every signed
       envelope, so verification is **offline** — an OIG auditor (or our own
       verifier) checks the signature against the published public key with
       no call back to KMS and no contact with Buddi.
    2. ``BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH`` — path to a PEM-encoded Ed25519
       private key (a self-managed alternative to KMS; the public half is
       still what an auditor verifies against).
    3. Fallback: a deterministic HMAC-SHA256 signature derived from
       ``BUDDI_STORAGE_KEY``. This keeps local dev / CI working without a
       KMS but is **not** an acceptable production posture and is flagged
       as such in the signature envelope (``algorithm=hmac-sha256-dev``).

Object Lock export (``export_daily_root`` → ``BUDDI_AUDIT_ROOTS_BUCKET``):
the signed envelope is always written to the local ``BUDDI_AUDIT_ROOTS_DIR``
(the canonical read path for verification), and *additionally* mirrored to a
WORM object-storage bucket (``s3://…`` or ``gs://…``) with Object Lock
retention when one is configured. That mirror is the append-only archive a
verifier trusts even if the host and the Postgres DB are fully compromised.

See ``docs/COMPLIANCE/phi_flow.md`` for the production wiring plan.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Stable "empty tree" sentinel. Required so we can sign even a zero-event
#: day without branching the schema. The string is the SHA-256 of the literal
#: ``"buddi-audit-empty-tree"`` so it cannot collide with any real leaf hash.
EMPTY_TREE_ROOT: str = hashlib.sha256(b"buddi-audit-empty-tree").hexdigest()

#: Filesystem location for signed daily roots (overridable for tests).
DEFAULT_AUDIT_ROOTS_DIR: str = "storage/audit_roots"

#: Filename suffix on the per-day JSON envelope.
_ROOT_FILE_SUFFIX = ".root.json"


def _roots_dir() -> Path:
    """Resolve the signed-roots export directory (env-overridable)."""

    return Path(os.getenv("BUDDI_AUDIT_ROOTS_DIR", DEFAULT_AUDIT_ROOTS_DIR))


# ---------------------------------------------------------------------------
# Leaf / tree primitives
# ---------------------------------------------------------------------------


def _canonical_json(payload: Any) -> str:
    """Stable JSON serialisation — same rules as ``backend/api.py``."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def leaf_hash(event: Dict[str, Any]) -> str:
    """Project an audit event into its canonical Merkle leaf.

    Both the DB-backed ``audit_events`` row and the legacy file-based
    ``audit_log.json`` event must produce the same digest when they
    represent the same logical event — this is what lets us verify the
    signed root against the live DB at any later point.

    Only the fields that materially affect chain integrity are folded in:
    ``event_id``, ``event_type``, ``timestamp``, ``previous_hash``,
    ``cryptographic_hash``, and ``payload``. Display-only or audit-meta
    fields are excluded so cosmetic backfills cannot break verification.
    """

    canonical = _canonical_json(
        {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "tenant_id": event.get("tenant_id"),
            "timestamp": event.get("timestamp"),
            "previous_hash": event.get("previous_hash"),
            "cryptographic_hash": event.get("cryptographic_hash"),
            "payload": event.get("payload") or {},
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_merkle_root(leaves: Sequence[str]) -> str:
    """Compute the SHA-256 Merkle root over an ordered list of hex leaves.

    Uses Bitcoin-style duplicate-last-leaf to keep the tree binary at odd
    levels. Returns ``EMPTY_TREE_ROOT`` for an empty input so callers can
    always sign *something*.
    """

    if not leaves:
        return EMPTY_TREE_ROOT
    level: List[str] = [_normalize_hex(h) for h in leaves]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level: List[str] = []
        for i in range(0, len(level), 2):
            joined = bytes.fromhex(level[i]) + bytes.fromhex(level[i + 1])
            next_level.append(hashlib.sha256(joined).hexdigest())
        level = next_level
    return level[0]


def _normalize_hex(value: str) -> str:
    """Reject obviously malformed leaf hashes; truncated chains should *fail closed*."""

    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"Invalid SHA-256 hex digest for Merkle leaf: {value!r}")
    int(value, 16)  # raises ValueError on non-hex
    return value.lower()


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def _verify_with_public_key(
    algorithm: str, public_key_pem: Optional[str], message: bytes, signature: bytes
) -> bool:
    """Verify an asymmetric signature against a published public key (offline).

    This is the auditor path: given only the algorithm, the PEM-encoded
    public key (which travels inside every signed envelope), the canonical
    message and the signature bytes, decide whether the signature is valid —
    with **no** call back to KMS and no Buddi-side secret. Returns False on
    any malformed input or signature mismatch (fail closed).
    """

    if not public_key_pem:
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
    except Exception:  # pragma: no cover — cryptography is pinned in requirements.txt
        logger.error("cryptography package is required to verify signed roots")
        return False

    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        # ``load_pem_public_key`` returns a union of key types, only some of
        # which expose ``verify``. Narrowing with ``isinstance`` per algorithm
        # both satisfies the type checker and fails closed when the PEM key
        # type does not match the algorithm declared in the envelope — an
        # auditor must never accept, say, an RSA signature "verified" against
        # an EC key.
        if algorithm == "ed25519":
            if not isinstance(public_key, ed25519.Ed25519PublicKey):
                return False
            public_key.verify(signature, message)
        elif algorithm == "ecdsa-p256-sha256":
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                return False
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        elif algorithm == "ecdsa-p384-sha384":
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                return False
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA384()))
        elif algorithm == "rsa-pkcs1-sha256":
            if not isinstance(public_key, rsa.RSAPublicKey):
                return False
            public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
        elif algorithm == "rsa-pss-sha256":
            if not isinstance(public_key, rsa.RSAPublicKey):
                return False
            public_key.verify(
                signature,
                message,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
        else:
            return False
        return True
    except InvalidSignature:
        return False
    except Exception as e:  # malformed key / signature — fail closed
        logger.warning("Public-key verification raised %s; treating as invalid", e)
        return False


#: GCP Cloud KMS ``CryptoKeyVersionAlgorithm`` name → (envelope algorithm,
#: digest field expected by ``asymmetric_sign``). Only the algorithms a
#: healthcare deployment would realistically pick are supported; anything
#: else raises so we never silently sign with an unverifiable scheme.
_GCP_KMS_ALGORITHMS: Dict[str, tuple] = {
    "EC_SIGN_P256_SHA256": ("ecdsa-p256-sha256", "sha256"),
    "EC_SIGN_P384_SHA384": ("ecdsa-p384-sha384", "sha384"),
    "RSA_SIGN_PKCS1_2048_SHA256": ("rsa-pkcs1-sha256", "sha256"),
    "RSA_SIGN_PKCS1_3072_SHA256": ("rsa-pkcs1-sha256", "sha256"),
    "RSA_SIGN_PKCS1_4096_SHA256": ("rsa-pkcs1-sha256", "sha256"),
    "RSA_SIGN_PSS_2048_SHA256": ("rsa-pss-sha256", "sha256"),
    "RSA_SIGN_PSS_3072_SHA256": ("rsa-pss-sha256", "sha256"),
    "RSA_SIGN_PSS_4096_SHA256": ("rsa-pss-sha256", "sha256"),
}

#: AWS KMS ``KeySpec`` → (envelope algorithm, AWS ``SigningAlgorithm``).
_AWS_KMS_ALGORITHMS: Dict[str, tuple] = {
    "ECC_NIST_P256": ("ecdsa-p256-sha256", "ECDSA_SHA_256"),
    "ECC_NIST_P384": ("ecdsa-p384-sha384", "ECDSA_SHA_384"),
    "RSA_2048": ("rsa-pkcs1-sha256", "RSASSA_PKCS1_V1_5_SHA_256"),
    "RSA_3072": ("rsa-pkcs1-sha256", "RSASSA_PKCS1_V1_5_SHA_256"),
    "RSA_4096": ("rsa-pkcs1-sha256", "RSASSA_PKCS1_V1_5_SHA_256"),
}


def _gcp_kms_client():  # pragma: no cover — thin SDK seam (monkeypatched in tests)
    """Return a GCP Cloud KMS client. Lazy import so the SDK is optional."""

    from google.cloud import kms  # type: ignore[import-not-found]  # optional dep

    return kms.KeyManagementServiceClient()


def _aws_kms_client():  # pragma: no cover — thin SDK seam (monkeypatched in tests)
    """Return a boto3 KMS client. Lazy import so the SDK is optional."""

    import boto3  # type: ignore[import-not-found]  # optional dep

    return boto3.client("kms", region_name=os.getenv("AWS_REGION") or None)


class MerkleSigner:
    """Pluggable signer for the daily Merkle root.

    Production deployments should bind this to GCP KMS / AWS KMS by
    providing an Ed25519 private key whose public half is published in
    ``docs/COMPLIANCE/`` (so external auditors can verify without
    contacting Buddi). The local Ed25519 + HMAC fallbacks exist so dev
    and CI keep working without a KMS — but they emit an
    ``algorithm`` value that explicitly distinguishes them from the
    production posture (``ed25519`` vs. ``hmac-sha256-dev``).
    """

    def __init__(
        self,
        *,
        algorithm: str,
        key_id: str,
        signer,  # callable: bytes -> bytes
        verifier=None,  # callable: bytes (message), bytes (sig) -> bool
        public_key_pem: Optional[str] = None,
        kms_provider: Optional[str] = None,
    ):
        self.algorithm = algorithm
        self.key_id = key_id
        self._signer = signer
        self._verifier = verifier
        self.public_key_pem = public_key_pem
        self.kms_provider = kms_provider

    def sign(
        self,
        merkle_root: str,
        day: str,
        event_count: int,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a signature envelope for ``(day, merkle_root, event_count)``."""

        message = self._canonical_message(day, merkle_root, event_count, tenant_id)
        signature_bytes = self._signer(message)
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "kms_provider": self.kms_provider,
            "signature_b64": base64.b64encode(signature_bytes).decode("ascii"),
            "signed_at": datetime.now(timezone.utc).isoformat(),  # Security: audit signatures must be timestamped in UTC.
            "public_key_pem": self.public_key_pem,
            "tenant_id": tenant_id,
        }

    def verify(
        self,
        envelope: Dict[str, Any],
        day: str,
        merkle_root: str,
        event_count: int,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Best-effort signature verification.

        Returns True when the envelope's algorithm matches our signer and
        the signature checks out. Returns False on mismatch. Raises only
        for malformed envelopes.
        """

        if envelope.get("algorithm") != self.algorithm:
            # Mismatched algorithm — caller must rotate signer / re-export.
            return False
        sig_b64 = envelope.get("signature_b64")
        if not sig_b64:
            return False
        signature_bytes = base64.b64decode(sig_b64)
        message = self._canonical_message(day, merkle_root, event_count, tenant_id)
        if self._verifier is None:
            # HMAC path: re-sign + constant-time compare.
            expected = self._signer(message)
            return hmac.compare_digest(expected, signature_bytes)
        try:
            return bool(self._verifier(message, signature_bytes))
        except Exception:
            return False

    @staticmethod
    def _canonical_message(
        day: str,
        merkle_root: str,
        event_count: int,
        tenant_id: Optional[str] = None,
    ) -> bytes:
        payload: Dict[str, Any] = {
            "day": day,
            "merkle_root": merkle_root,
            "event_count": event_count,
        }
        if tenant_id:
            payload["tenant_id"] = tenant_id
        return _canonical_json(payload).encode("utf-8")

    # -- Factories ----------------------------------------------------------

    @classmethod
    def from_env(cls) -> "MerkleSigner":
        """Resolve the configured signer.

        Priority: Cloud KMS (GCP/AWS) → local Ed25519 PEM → HMAC dev fallback.
        A failure to initialise a *configured* higher-priority signer is
        logged loudly and falls through to the next option so the API never
        fails to start — the seal loop in ``backend/api.py`` records the
        algorithm actually used, and production monitoring alerts on any
        envelope whose ``algorithm`` is the dev HMAC fallback.
        """

        provider = os.getenv("BUDDI_AUDIT_KMS_PROVIDER", "").strip().lower()
        kms_key = os.getenv("BUDDI_AUDIT_KMS_KEY", "").strip()
        production = os.getenv("ENVIRONMENT", "production").strip().lower() == "production"
        require_configured_signer = (
            production or os.getenv("BUDDI_AUDIT_REQUIRE_CONFIGURED_SIGNER", "").strip() == "1"
        )
        if provider and kms_key:
            try:
                if provider in {"gcp", "gcp-kms", "google", "cloudkms"}:
                    return cls._gcp_kms_signer(kms_key)
                if provider in {"aws", "aws-kms"}:
                    return cls._aws_kms_signer(kms_key)
                raise ValueError(
                    f"Unknown BUDDI_AUDIT_KMS_PROVIDER={provider!r} (expected 'gcp' or 'aws')"
                )
            except Exception as e:
                logger.error(
                    "Failed to initialise %s KMS signer for key %s: %s; "
                    "falling back to local signing key",
                    provider,
                    kms_key,
                    e,
                )
                if require_configured_signer:
                    raise RuntimeError("Configured audit KMS signer failed to initialise") from e

        pem_path = os.getenv("BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH", "").strip()
        if pem_path:
            try:
                return cls._ed25519_from_pem_file(pem_path)
            except Exception as e:
                # Loud warning + fall through. Production deployments MUST
                # set the PEM path; if loading fails we'd rather crash the
                # caller than silently downgrade to HMAC. The seal loop in
                # backend/api.py catches the resulting RuntimeError and
                # logs the day as un-sealed.
                logger.error(
                    "Failed to load signing key from %s: %s; falling back to dev HMAC signer",
                    pem_path,
                    e,
                )
                if require_configured_signer:
                    raise RuntimeError("Configured audit root signing key failed to load") from e
        if require_configured_signer:
            raise RuntimeError(
                "Production audit root signing requires BUDDI_AUDIT_KMS_PROVIDER/"
                "BUDDI_AUDIT_KMS_KEY or BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH. "
                "Refusing to use the dev HMAC signer."
            )
        return cls._dev_hmac_signer()

    @classmethod
    def _ed25519_from_pem_file(cls, path: str) -> "MerkleSigner":
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
                Ed25519PublicKey,
            )
        except Exception as e:  # pragma: no cover — cryptography is pinned in requirements.txt
            raise RuntimeError(
                "cryptography package is required for Ed25519 signing"
            ) from e

        with open(path, "rb") as f:
            pem_bytes = f.read()
        key = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(
                f"Signing key at {path} is not an Ed25519 private key"
            )
        pub: Ed25519PublicKey = key.public_key()
        pub_pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        key_id = hashlib.sha256(pub_pem.encode("ascii")).hexdigest()[:16]

        def _sign(message: bytes) -> bytes:
            return key.sign(message)

        def _verify(message: bytes, signature: bytes) -> bool:
            try:
                pub.verify(signature, message)
                return True
            except Exception:
                return False

        return cls(
            algorithm="ed25519",
            key_id=key_id,
            signer=_sign,
            verifier=_verify,
            public_key_pem=pub_pem,
        )

    @classmethod
    def _gcp_kms_signer(cls, key_name: str) -> "MerkleSigner":
        """Build a signer backed by a GCP Cloud KMS asymmetric-sign key.

        ``key_name`` is a CryptoKeyVersion resource name
        (``projects/…/cryptoKeyVersions/N``). The private key never leaves
        the HSM; we fetch the public half once and verify against it offline.
        """

        client = _gcp_kms_client()
        pub = client.get_public_key(name=key_name)
        public_key_pem = pub.pem
        gcp_algo = getattr(pub.algorithm, "name", None) or str(pub.algorithm)
        if gcp_algo not in _GCP_KMS_ALGORITHMS:
            raise ValueError(
                f"Unsupported GCP KMS key algorithm {gcp_algo!r} for {key_name}; "
                f"supported: {sorted(_GCP_KMS_ALGORITHMS)}"
            )
        algorithm, digest_field = _GCP_KMS_ALGORITHMS[gcp_algo]
        digest_fn = {"sha256": hashlib.sha256, "sha384": hashlib.sha384}[digest_field]

        def _sign(message: bytes) -> bytes:
            digest = {digest_field: digest_fn(message).digest()}
            response = client.asymmetric_sign(name=key_name, digest=digest)
            return response.signature

        def _verify(message: bytes, signature: bytes) -> bool:
            return _verify_with_public_key(algorithm, public_key_pem, message, signature)

        return cls(
            algorithm=algorithm,
            key_id=key_name,
            signer=_sign,
            verifier=_verify,
            public_key_pem=public_key_pem,
            kms_provider="gcp",
        )

    @classmethod
    def _aws_kms_signer(cls, key_id: str) -> "MerkleSigner":
        """Build a signer backed by an AWS KMS asymmetric (SIGN_VERIFY) key.

        ``key_id`` is a KMS key id, alias, or ARN. The canonical message is
        small (well under the 4 KiB ``MessageType=RAW`` limit), so KMS hashes
        it server-side; we verify offline against the fetched public key.
        """

        from cryptography.hazmat.primitives import serialization

        client = _aws_kms_client()
        info = client.get_public_key(KeyId=key_id)
        key_spec = info.get("KeySpec") or info.get("CustomerMasterKeySpec")
        if key_spec not in _AWS_KMS_ALGORITHMS:
            raise ValueError(
                f"Unsupported AWS KMS KeySpec {key_spec!r} for {key_id}; "
                f"supported: {sorted(_AWS_KMS_ALGORITHMS)}"
            )
        algorithm, signing_algorithm = _AWS_KMS_ALGORITHMS[key_spec]
        # AWS returns the public key DER-encoded (SubjectPublicKeyInfo).
        public_key = serialization.load_der_public_key(info["PublicKey"])
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

        def _sign(message: bytes) -> bytes:
            response = client.sign(
                KeyId=key_id,
                Message=message,
                MessageType="RAW",
                SigningAlgorithm=signing_algorithm,
            )
            return response["Signature"]

        def _verify(message: bytes, signature: bytes) -> bool:
            return _verify_with_public_key(algorithm, public_key_pem, message, signature)

        return cls(
            algorithm=algorithm,
            key_id=key_id,
            signer=_sign,
            verifier=_verify,
            public_key_pem=public_key_pem,
            kms_provider="aws",
        )

    @classmethod
    def _dev_hmac_signer(cls) -> "MerkleSigner":
        # Use BUDDI_STORAGE_KEY so we don't introduce yet another env var
        # for the dev fallback. The algorithm string is explicit so
        # nobody mistakes this for production-grade signing.
        secret = os.getenv("BUDDI_STORAGE_KEY", "buddi-dev-storage-key")
        key_bytes = secret.encode("utf-8")
        key_id = hashlib.sha256(b"dev-hmac::" + key_bytes).hexdigest()[:16]

        def _sign(message: bytes) -> bytes:
            return hmac.new(key_bytes, message, hashlib.sha256).digest()

        return cls(
            algorithm="hmac-sha256-dev",
            key_id=key_id,
            signer=_sign,
            verifier=None,
            public_key_pem=None,
        )


# Cache the signer so we don't re-read the PEM on every seal.
_signer_singleton: Optional[MerkleSigner] = None


def get_signer() -> MerkleSigner:
    global _signer_singleton
    if _signer_singleton is None:
        _signer_singleton = MerkleSigner.from_env()
    return _signer_singleton


def reset_signer_cache() -> None:
    """Drop the cached signer (used by tests that rotate env vars)."""

    global _signer_singleton
    _signer_singleton = None


def verify_envelope(
    envelope: Dict[str, Any],
    day: str,
    merkle_root: str,
    event_count: int,
    tenant_id: Optional[str] = None,
) -> bool:
    """Verify a signature envelope independently of the *currently* configured signer.

    Verification is driven by the envelope itself, not by ``get_signer()``,
    so a multi-year audit trail survives key rotation: a day signed last year
    with an Ed25519 key (or a since-retired KMS key) still verifies against
    the public key embedded in its own envelope, even after we've rotated to
    a new key. Asymmetric signatures (Ed25519 / ECDSA / RSA, including all
    KMS-backed ones) verify **offline** against ``public_key_pem``; only the
    symmetric dev HMAC needs the shared secret from the active signer.
    """

    algorithm = envelope.get("algorithm")
    sig_b64 = envelope.get("signature_b64")
    if not algorithm or not sig_b64:
        return False
    tenant = tenant_id or envelope.get("tenant_id")
    message = MerkleSigner._canonical_message(day, merkle_root, event_count, tenant)
    try:
        signature = base64.b64decode(sig_b64)
    except Exception:
        return False

    if algorithm == "hmac-sha256-dev":
        # Symmetric: re-derivation needs the shared secret, which only the
        # active HMAC signer holds (it never travels in the envelope).
        signer = get_signer()
        if signer.algorithm != "hmac-sha256-dev":
            return False
        return signer.verify(envelope, day, merkle_root, event_count, tenant)

    return _verify_with_public_key(algorithm, envelope.get("public_key_pem"), message, signature)


# ---------------------------------------------------------------------------
# Daily-root build / export / verify
# ---------------------------------------------------------------------------


@dataclass
class DailyRoot:
    """In-memory representation of one day's signed Merkle envelope."""

    day: str
    merkle_root: str
    event_count: int
    event_hashes: List[str]
    signature: Dict[str, Any] = field(default_factory=dict)
    tenant_id: Optional[str] = None
    #: Set by ``export_daily_root`` when the envelope is mirrored to an Object
    #: Lock bucket. Deliberately excluded from ``to_envelope`` so it never
    #: changes the signed/persisted payload — it is run metadata, not content.
    object_lock_uri: Optional[str] = None

    def to_envelope(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            **({"tenant_id": self.tenant_id} if self.tenant_id else {}),
            "merkle_root": self.merkle_root,
            "event_count": self.event_count,
            "event_hashes": list(self.event_hashes),
            "signature": dict(self.signature),
        }

    @classmethod
    def from_envelope(cls, envelope: Dict[str, Any]) -> "DailyRoot":
        return cls(
            day=str(envelope["day"]),
            merkle_root=str(envelope["merkle_root"]),
            event_count=int(envelope.get("event_count", 0)),
            event_hashes=[str(h) for h in envelope.get("event_hashes", [])],
            signature=dict(envelope.get("signature") or {}),
            tenant_id=str(envelope["tenant_id"]) if envelope.get("tenant_id") else None,
        )


def _events_for_day(
    db: Session,
    day: date,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read every audit event whose timestamp falls inside ``day`` UTC."""

    # Lazy import to avoid SQLAlchemy load on bare ``import core.merkle``.
    from core.models import AuditEvent

    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = datetime.fromordinal(start.toordinal() + 1).replace(tzinfo=timezone.utc)
    query = (
        db.query(AuditEvent)
        .filter(AuditEvent.timestamp >= start)
        .filter(AuditEvent.timestamp < end)
    )
    if tenant_id:
        query = query.filter(AuditEvent.tenant_id == tenant_id)
    rows = query.order_by(AuditEvent.event_id.asc()).all()
    projected: List[Dict[str, Any]] = []
    for row in rows:
        projected.append(
            {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "tenant_id": str(row.tenant_id) if getattr(row, "tenant_id", None) else None,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "previous_hash": row.previous_hash,
                "cryptographic_hash": row.cryptographic_hash,
                "payload": row.payload or {},
            }
        )
    return projected


def build_daily_root(
    db: Session,
    day: date,
    tenant_id: Optional[str] = None,
) -> DailyRoot:
    """Compute and *sign* the Merkle root for ``day`` (UTC)."""

    tenant_str = str(tenant_id) if tenant_id else None
    events = _events_for_day(db, day, tenant_id=tenant_str)
    leaves = [leaf_hash(e) for e in events]
    root = compute_merkle_root(leaves)
    signer = get_signer()
    iso_day = day.isoformat()
    signature = signer.sign(root, iso_day, len(events), tenant_id=tenant_str)
    return DailyRoot(
        day=iso_day,
        merkle_root=root,
        event_count=len(events),
        event_hashes=[
            e.get("cryptographic_hash") or h for e, h in zip(events, leaves)
        ],
        signature=signature,
        tenant_id=tenant_str,
    )


def export_daily_root(daily: DailyRoot, base_dir: Optional[Path] = None) -> Path:
    """Persist the signed envelope locally and mirror it to Object Lock.

    The local path layout is ``{base_dir}/YYYY/MM/YYYY-MM-DD.root.json`` and
    is the canonical read path for ``load_signed_root`` / verification. When
    ``BUDDI_AUDIT_ROOTS_BUCKET`` is configured (``s3://…`` or ``gs://…``) the
    same bytes are additionally written to that WORM bucket with Object Lock
    retention, giving an append-only archive that survives full host/DB
    compromise. Returns the *local* path; the bucket URI (if any) is recorded
    on ``daily.object_lock_uri``.
    """

    root_base = base_dir or _roots_dir()
    if daily.tenant_id:
        root_base = root_base / "tenants" / daily.tenant_id
    out_dir = root_base / daily.day[:4] / daily.day[5:7]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{daily.day}{_ROOT_FILE_SUFFIX}"
    payload = daily.to_envelope()
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    # Write atomically so a partial write cannot corrupt yesterday's
    # signed root. tmp → rename is sufficient for local fs / GCS-fuse.
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    tmp_path.replace(path)

    target = _object_lock_target()
    if target:
        # A failure to write the immutable archive copy is a compliance
        # event, not something to swallow: re-raise so the seal loop logs the
        # day as un-sealed and operators are alerted. The local copy is
        # already durable, so a later backfill can re-mirror it.
        try:
            daily.object_lock_uri = _export_to_object_lock(target, daily, serialized.encode("utf-8"))
            logger.info(
                "Signed root for %s mirrored to Object Lock bucket: %s",
                daily.day,
                daily.object_lock_uri,
            )
        except Exception as e:
            logger.error("Object Lock export failed for %s (%s): %s", daily.day, target, e)
            raise
    return path


def load_signed_root(
    day: str,
    base_dir: Optional[Path] = None,
    tenant_id: Optional[str] = None,
) -> Optional[DailyRoot]:
    """Return the persisted envelope for ``day``, or None if missing."""

    base = base_dir or _roots_dir()
    if tenant_id:
        base = base / "tenants" / str(tenant_id)
    path = base / day[:4] / day[5:7] / f"{day}{_ROOT_FILE_SUFFIX}"
    if not path.exists():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load signed root for %s: %s", day, e)
        return None
    return DailyRoot.from_envelope(envelope)


def list_signed_root_days(
    base_dir: Optional[Path] = None,
    tenant_id: Optional[str] = None,
) -> List[str]:
    """Inventory of every signed daily root currently on disk."""

    base = base_dir or _roots_dir()
    if tenant_id:
        base = base / "tenants" / str(tenant_id)
    if not base.exists():
        return []
    days: List[str] = []
    for path in sorted(base.glob(f"*/*/*{_ROOT_FILE_SUFFIX}")):
        days.append(path.name[: -len(_ROOT_FILE_SUFFIX)])
    return days


def verify_signed_roots_against_db(
    db: Session,
    base_dir: Optional[Path] = None,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Recompute each signed root from the live DB and compare.

    For each day with a persisted envelope:
      1. Recompute the Merkle root from the current ``audit_events`` rows.
      2. Verify the persisted envelope's signature matches the recomputed
         ``(day, root, event_count)`` triple.
      3. Compare the recomputed root against the persisted root.

    A divergence is reported per-day so an operator can see exactly which
    day was tampered with. ``verified=True`` requires every checked day
    to pass both signature verification and root recomputation.
    """

    days = list_signed_root_days(base_dir, tenant_id=tenant_id)
    per_day: List[Dict[str, Any]] = []
    valid_days = 0
    for iso_day in days:
        envelope = load_signed_root(iso_day, base_dir, tenant_id=tenant_id)
        if envelope is None:
            per_day.append({"day": iso_day, "status": "missing_envelope", "verified": False})
            continue
        try:
            target_day = date.fromisoformat(iso_day)
        except ValueError:
            per_day.append({"day": iso_day, "status": "invalid_day_label", "verified": False})
            continue

        recomputed = build_daily_root_unsigned(db, target_day, tenant_id=tenant_id)
        root_matches = recomputed.merkle_root == envelope.merkle_root
        sig_ok = verify_envelope(
            envelope.signature,
            envelope.day,
            envelope.merkle_root,
            envelope.event_count,
            tenant_id=tenant_id,
        )
        day_verified = bool(root_matches and sig_ok)
        if day_verified:
            valid_days += 1
        per_day.append(
            {
                "day": iso_day,
                "tenant_id": tenant_id,
                "verified": day_verified,
                "signature_valid": sig_ok,
                "root_matches_db": root_matches,
                "persisted_root": envelope.merkle_root,
                "recomputed_root": recomputed.merkle_root,
                "event_count": envelope.event_count,
                "algorithm": envelope.signature.get("algorithm"),
                "key_id": envelope.signature.get("key_id"),
            }
        )
    return {
        "verified": valid_days == len(days),
        "checked_days": len(days),
        "valid_days": valid_days,
        "days": per_day,
    }


def build_daily_root_unsigned(
    db: Session,
    day: date,
    tenant_id: Optional[str] = None,
) -> DailyRoot:
    """Build a ``DailyRoot`` without signing — used by verification."""

    tenant_str = str(tenant_id) if tenant_id else None
    events = _events_for_day(db, day, tenant_id=tenant_str)
    leaves = [leaf_hash(e) for e in events]
    return DailyRoot(
        day=day.isoformat(),
        merkle_root=compute_merkle_root(leaves),
        event_count=len(events),
        event_hashes=[
            e.get("cryptographic_hash") or h for e, h in zip(events, leaves)
        ],
        signature={},
        tenant_id=tenant_str,
    )


# ---------------------------------------------------------------------------
# Object Lock (WORM) export
# ---------------------------------------------------------------------------


def _object_lock_target() -> Optional[str]:
    """The configured Object Lock bucket URI (``s3://…`` / ``gs://…``), or None."""

    return os.getenv("BUDDI_AUDIT_ROOTS_BUCKET", "").strip() or None


def _object_lock_retention() -> tuple:
    """Resolve (retention mode, retention days) for the WORM mirror.

    Defaults to ``COMPLIANCE`` mode for ~7 years (2555 days) — comfortably
    beyond the HIPAA 6-year documentation-retention floor. COMPLIANCE mode
    cannot be shortened or bypassed by *any* principal, including the root
    account, which is the whole point of the moat.
    """

    mode = os.getenv("BUDDI_AUDIT_OBJECT_LOCK_MODE", "COMPLIANCE").strip().upper()
    try:
        days = int(os.getenv("BUDDI_AUDIT_OBJECT_LOCK_DAYS", "2555"))
    except ValueError:
        days = 2555
    return mode, days


def _object_lock_key(prefix: str, daily: DailyRoot) -> str:
    """Mirror the local ``YYYY/MM/DAY.root.json`` layout under the bucket prefix."""

    parts = [
        prefix.strip("/"),
        "tenants" if daily.tenant_id else "",
        daily.tenant_id or "",
        daily.day[:4],
        daily.day[5:7],
        f"{daily.day}{_ROOT_FILE_SUFFIX}",
    ]
    return "/".join(p for p in parts if p)


def _export_to_object_lock(target: str, daily: DailyRoot, body: bytes) -> str:
    """Write ``body`` to the configured WORM bucket; return the object URI."""

    scheme, sep, rest = target.partition("://")
    if not sep:
        raise ValueError(f"Object Lock bucket must be a URI (s3://… or gs://…), got {target!r}")
    bucket, _, prefix = rest.partition("/")
    if not bucket:
        raise ValueError(f"Object Lock bucket URI is missing a bucket name: {target!r}")
    key = _object_lock_key(prefix, daily)
    scheme = scheme.lower()
    if scheme == "s3":
        return _put_s3_object_lock(bucket, key, body)
    if scheme in {"gs", "gcs"}:
        return _put_gcs_object_lock(bucket, key, body)
    raise ValueError(f"Unsupported Object Lock bucket scheme {scheme!r} (use s3:// or gs://)")


def _put_s3_object_lock(bucket: str, key: str, body: bytes) -> str:
    """Upload to S3 with an Object Lock retention header."""

    client = _s3_client()
    mode, days = _object_lock_retention()
    kwargs: Dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentType": "application/json",
    }
    if mode in {"COMPLIANCE", "GOVERNANCE"}:
        kwargs["ObjectLockMode"] = mode
        kwargs["ObjectLockRetainUntilDate"] = datetime.now(timezone.utc) + timedelta(days=days)
    client.put_object(**kwargs)
    return f"s3://{bucket}/{key}"


def _put_gcs_object_lock(bucket: str, key: str, body: bytes) -> str:
    """Upload to GCS, refusing to overwrite an existing generation (write-once).

    The bucket's retention policy (provisioned via IaC) is the primary
    immutability control; we additionally request per-object retention where
    the SDK supports it, and use ``if_generation_match=0`` so a re-seal can
    never clobber an already-archived root.
    """

    client = _gcs_client()
    blob = client.bucket(bucket).blob(key)
    blob.upload_from_string(body, content_type="application/json", if_generation_match=0)
    try:
        mode, days = _object_lock_retention()
        if mode in {"COMPLIANCE", "GOVERNANCE", "LOCKED"}:
            blob.retention.mode = "Locked"
            blob.retention.retain_until_time = datetime.now(timezone.utc) + timedelta(days=days)
            blob.patch()
    except Exception as e:  # pragma: no cover — depends on SDK / bucket capabilities
        logger.warning(
            "GCS per-object retention not applied for %s: %s; "
            "relying on the bucket retention policy for immutability",
            key,
            e,
        )
    return f"gs://{bucket}/{key}"


def _s3_client():  # pragma: no cover — thin SDK seam (monkeypatched in tests)
    """Return a boto3 S3 client. Lazy import so the SDK is optional."""

    import boto3  # type: ignore[import-not-found]  # optional dep

    return boto3.client("s3", region_name=os.getenv("AWS_REGION") or None)


def _gcs_client():  # pragma: no cover — thin SDK seam (monkeypatched in tests)
    """Return a google-cloud-storage client. Lazy import so the SDK is optional."""

    from google.cloud import storage  # type: ignore[import-not-found]  # optional dep

    return storage.Client()


__all__ = [
    "EMPTY_TREE_ROOT",
    "DailyRoot",
    "MerkleSigner",
    "build_daily_root",
    "build_daily_root_unsigned",
    "compute_merkle_root",
    "export_daily_root",
    "get_signer",
    "leaf_hash",
    "list_signed_root_days",
    "load_signed_root",
    "reset_signer_cache",
    "verify_envelope",
    "verify_signed_roots_against_db",
]
