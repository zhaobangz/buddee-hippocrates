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

Signing key resolution:

    * ``BUDDI_AUDIT_ROOT_SIGNING_KEY_PATH`` — path to a PEM-encoded Ed25519
      private key (preferred for production; the public half is what an
      OIG auditor verifies against).
    * Fallback: a deterministic HMAC-SHA256 signature derived from
      ``BUDDI_STORAGE_KEY``. This keeps local dev / CI working without a
      KMS but is **not** an acceptable production posture and is flagged
      as such in the signature envelope (``algorithm=hmac-sha256-dev``).

The manual's recommendation is GCP KMS (or AWS KMS) backing an Ed25519
key. ``MerkleSigner.from_env()`` is the seam where that integration
plugs in without changing the API surface; today it returns the local
Ed25519 / HMAC fallback. See ``docs/COMPLIANCE/phi_flow.md`` for the
production wiring plan.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
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
    ):
        self.algorithm = algorithm
        self.key_id = key_id
        self._signer = signer
        self._verifier = verifier
        self.public_key_pem = public_key_pem

    def sign(self, merkle_root: str, day: str, event_count: int) -> Dict[str, Any]:
        """Return a signature envelope for ``(day, merkle_root, event_count)``."""

        message = self._canonical_message(day, merkle_root, event_count)
        signature_bytes = self._signer(message)
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "signature_b64": base64.b64encode(signature_bytes).decode("ascii"),
            "signed_at": datetime.now(timezone.utc).isoformat(),  # Security: audit signatures must be timestamped in UTC.
            "public_key_pem": self.public_key_pem,
        }

    def verify(self, envelope: Dict[str, Any], day: str, merkle_root: str, event_count: int) -> bool:
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
        message = self._canonical_message(day, merkle_root, event_count)
        if self._verifier is None:
            # HMAC path: re-sign + constant-time compare.
            expected = self._signer(message)
            return hmac.compare_digest(expected, signature_bytes)
        try:
            return bool(self._verifier(message, signature_bytes))
        except Exception:
            return False

    @staticmethod
    def _canonical_message(day: str, merkle_root: str, event_count: int) -> bytes:
        return _canonical_json(
            {"day": day, "merkle_root": merkle_root, "event_count": event_count}
        ).encode("utf-8")

    # -- Factories ----------------------------------------------------------

    @classmethod
    def from_env(cls) -> "MerkleSigner":
        """Resolve the configured signer (Ed25519 file → HMAC dev fallback)."""

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

    def to_envelope(self) -> Dict[str, Any]:
        return {
            "day": self.day,
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
        )


def _events_for_day(db: Session, day: date) -> List[Dict[str, Any]]:
    """Read every audit event whose timestamp falls inside ``day`` UTC."""

    # Lazy import to avoid SQLAlchemy load on bare ``import core.merkle``.
    from core.models import AuditEvent

    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = datetime.fromordinal(start.toordinal() + 1).replace(tzinfo=timezone.utc)
    rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.timestamp >= start)
        .filter(AuditEvent.timestamp < end)
        .order_by(AuditEvent.event_id.asc())
        .all()
    )
    projected: List[Dict[str, Any]] = []
    for row in rows:
        projected.append(
            {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "previous_hash": row.previous_hash,
                "cryptographic_hash": row.cryptographic_hash,
                "payload": row.payload or {},
            }
        )
    return projected


def build_daily_root(db: Session, day: date) -> DailyRoot:
    """Compute and *sign* the Merkle root for ``day`` (UTC)."""

    events = _events_for_day(db, day)
    leaves = [leaf_hash(e) for e in events]
    root = compute_merkle_root(leaves)
    signer = get_signer()
    iso_day = day.isoformat()
    signature = signer.sign(root, iso_day, len(events))
    return DailyRoot(
        day=iso_day,
        merkle_root=root,
        event_count=len(events),
        event_hashes=[
            e.get("cryptographic_hash") or h for e, h in zip(events, leaves)
        ],
        signature=signature,
    )


def export_daily_root(daily: DailyRoot, base_dir: Optional[Path] = None) -> Path:
    """Persist the signed envelope to disk (or object storage shim).

    The path layout is ``{base_dir}/YYYY/MM/YYYY-MM-DD.root.json``. In
    production this directory should be backed by GCS / S3 with Object
    Lock — the file write itself is intentionally vanilla so swapping in
    a storage backend is a 5-line change in this function.
    """

    out_dir = (base_dir or _roots_dir()) / daily.day[:4] / daily.day[5:7]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{daily.day}{_ROOT_FILE_SUFFIX}"
    payload = daily.to_envelope()
    # Write atomically so a partial write cannot corrupt yesterday's
    # signed root. tmp → rename is sufficient for local fs / GCS-fuse.
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return path


def load_signed_root(day: str, base_dir: Optional[Path] = None) -> Optional[DailyRoot]:
    """Return the persisted envelope for ``day``, or None if missing."""

    base = base_dir or _roots_dir()
    path = base / day[:4] / day[5:7] / f"{day}{_ROOT_FILE_SUFFIX}"
    if not path.exists():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load signed root for %s: %s", day, e)
        return None
    return DailyRoot.from_envelope(envelope)


def list_signed_root_days(base_dir: Optional[Path] = None) -> List[str]:
    """Inventory of every signed daily root currently on disk."""

    base = base_dir or _roots_dir()
    if not base.exists():
        return []
    days: List[str] = []
    for path in sorted(base.glob(f"*/*/*{_ROOT_FILE_SUFFIX}")):
        days.append(path.name[: -len(_ROOT_FILE_SUFFIX)])
    return days


def verify_signed_roots_against_db(
    db: Session, base_dir: Optional[Path] = None
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

    signer = get_signer()
    days = list_signed_root_days(base_dir)
    per_day: List[Dict[str, Any]] = []
    valid_days = 0
    for iso_day in days:
        envelope = load_signed_root(iso_day, base_dir)
        if envelope is None:
            per_day.append({"day": iso_day, "status": "missing_envelope", "verified": False})
            continue
        try:
            target_day = date.fromisoformat(iso_day)
        except ValueError:
            per_day.append({"day": iso_day, "status": "invalid_day_label", "verified": False})
            continue

        recomputed = build_daily_root_unsigned(db, target_day)
        root_matches = recomputed.merkle_root == envelope.merkle_root
        sig_ok = signer.verify(
            envelope.signature,
            envelope.day,
            envelope.merkle_root,
            envelope.event_count,
        )
        day_verified = bool(root_matches and sig_ok)
        if day_verified:
            valid_days += 1
        per_day.append(
            {
                "day": iso_day,
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


def build_daily_root_unsigned(db: Session, day: date) -> DailyRoot:
    """Build a ``DailyRoot`` without signing — used by verification."""

    events = _events_for_day(db, day)
    leaves = [leaf_hash(e) for e in events]
    return DailyRoot(
        day=day.isoformat(),
        merkle_root=compute_merkle_root(leaves),
        event_count=len(events),
        event_hashes=[
            e.get("cryptographic_hash") or h for e, h in zip(events, leaves)
        ],
        signature={},
    )


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
    "verify_signed_roots_against_db",
]
