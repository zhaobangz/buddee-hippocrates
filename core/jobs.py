"""Async job queue storage helpers.

This module owns enqueue, poll, claim, and completion state transitions for
LLM-bound background work. It intentionally does not import from ``backend`` so
it stays usable from both the FastAPI app and the standalone Cloud Run worker.

All helpers operate on a caller-supplied ``sqlalchemy.orm.Session``. They never
open their own sessions, which keeps transaction boundaries explicit and makes
the functions easy to unit-test.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.models import Job

VALID_JOB_TYPES = {"shadow_audit", "prior_auth"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def compute_idempotency_key(
    tenant_id: uuid.UUID,
    encounter_id: str | None,
    note_hash: str | None,
    job_type: str,
) -> str:
    """Return the canonical job idempotency key used by API enqueue paths."""

    return hashlib.sha256(
        f"{tenant_id}:{encounter_id or ''}:{note_hash or ''}:{job_type}".encode("utf-8")
    ).hexdigest()


def compute_payload_hash(payload: dict[str, Any], *keys: str) -> str:
    """Stable SHA-256 hash over selected request payload fields.

    ``note_hash`` in the API contract is supplied by callers when present, but
    many legacy/demo requests do not include one. This helper gives those
    requests a deterministic substitute without storing PHI in the key.
    """

    selected = {key: payload.get(key) for key in keys if key in payload}
    return hashlib.sha256(
        json.dumps(selected, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


async def enqueue(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    job_type: str,
    input_payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> Job:
    """Insert a pending job, returning an existing row on idempotency hit."""

    if job_type not in VALID_JOB_TYPES:
        raise ValueError(f"Unknown job_type: {job_type}")

    if idempotency_key:
        existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
        if existing is not None:
            return existing

    job = Job(
        tenant_id=tenant_id,
        job_type=job_type,
        status="pending",
        input_payload=input_payload,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
            if existing is not None:
                return existing
        raise
    return job


def get_job(db: Session, job_id: uuid.UUID, tenant_id: uuid.UUID) -> Job | None:
    """Fetch a job by ID, scoped to tenant."""

    return db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()


def claim_next_pending(db: Session) -> Job | None:
    """Atomically claim the oldest pending job with FOR UPDATE SKIP LOCKED."""

    job = (
        db.query(Job)
        .filter(Job.status == "pending")
        .order_by(Job.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    job.status = "processing"
    job.started_at = _now()
    db.flush()
    return job


def mark_completed(db: Session, job: Job, result: dict[str, Any]) -> None:
    """Set status='completed', result_payload=result, completed_at=now()."""

    job.status = "completed"
    job.result_payload = result
    job.error_message = None
    job.completed_at = _now()
    db.flush()


def mark_failed(db: Session, job: Job, error: str) -> None:
    """Set status='failed', error_message=error, completed_at=now()."""

    job.status = "failed"
    job.error_message = (error or "")[:2000]
    job.completed_at = _now()
    db.flush()


# Backward-compatible aliases for earlier local build-out code/tests. New code
# should call enqueue/get_job/mark_completed/mark_failed directly.
async def create_job(
    db: Session,
    tenant_id: uuid.UUID,
    job_type: str,
    input_payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> Job:
    return await enqueue(
        db,
        tenant_id=tenant_id,
        job_type=job_type,
        input_payload=input_payload,
        idempotency_key=idempotency_key,
    )


complete_job = mark_completed
fail_job = mark_failed


__all__ = [
    "Job",
    "VALID_JOB_TYPES",
    "claim_next_pending",
    "complete_job",
    "compute_idempotency_key",
    "compute_payload_hash",
    "create_job",
    "enqueue",
    "fail_job",
    "get_job",
    "mark_completed",
    "mark_failed",
]