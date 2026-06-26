"""Tests for the build-out B3 async job queue (PROMPT_03 Task 7).

The queue helpers (enqueue / claim / complete / fail / idempotency) are
exercised against a *real* Postgres session: they rely on server-side
``FOR UPDATE SKIP LOCKED`` and a ``UNIQUE`` idempotency constraint that an
in-memory mock cannot model. The DB-backed tests therefore skip cleanly when
the test Postgres on :5433 is unreachable (the default locally); CI provisions
it and runs ``alembic upgrade head`` first.

Each DB test does all of its work inside one uncommitted transaction that the
fixture rolls back on teardown, so nothing leaks between tests. The async
``enqueue`` coroutine is driven with ``asyncio.run`` so the suite needs no
pytest-asyncio mode configured.

The HTTP surface is covered both ways: the async ``202`` enqueue + poll path
(needs a real tenant, via ``tenant_api_key``) and the legacy ``?sync=true``
inline path (works without a DB — persistence soft-fails).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from core import jobs as job_queue
from core.models import Job


def _run(coro):
    """Drive an async coroutine to completion from a synchronous test."""
    return asyncio.run(coro)


def _enqueue(db, tenant_id, *, job_type="shadow_audit", payload=None, idempotency_key=None):
    return _run(
        job_queue.enqueue(
            db,
            tenant_id=tenant_id,
            job_type=job_type,
            input_payload=payload if payload is not None else {"note": "demo", "billed_codes": []},
            idempotency_key=idempotency_key,
        )
    )


def _drain_pending(db):
    """Clear any pending/processing rows *within this transaction* only.

    The worker is disabled under pytest, so stray pending rows are inert. This
    makes the global ``claim_next_pending()`` deterministically return the job
    the test just enqueued. The delete is never committed (the fixture rolls
    back on teardown), so it cannot touch another test's persisted data.
    """
    db.query(Job).filter(Job.status.in_(["pending", "processing"])).delete(
        synchronize_session=False
    )
    db.flush()


@pytest.fixture
def db_tenant():
    """Yield ``(session, tenant_id)`` backed by a committed ``Tenant`` row.

    Skips when the test Postgres is unreachable. On teardown it rolls back the
    test's uncommitted work, then deletes the tenant (which CASCADE-removes any
    committed jobs for it).
    """
    from core import models
    from core.database import SessionLocal

    db = SessionLocal()
    try:
        tenant = models.Tenant(name=f"jobs-test-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        db.commit()
        tenant_id = tenant.id
    except Exception as exc:  # noqa: BLE001 - any DB failure => skip, not fail
        db.rollback()
        db.close()
        pytest.skip(f"test Postgres unavailable: {exc}")

    try:
        yield db, tenant_id
    finally:
        try:
            db.rollback()
            db.query(models.Tenant).filter(models.Tenant.id == tenant_id).delete()
            db.commit()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            db.rollback()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Queue helpers (real session)
# ---------------------------------------------------------------------------


def test_enqueue_and_poll(db_tenant):
    db, tenant_id = db_tenant
    _drain_pending(db)

    job = _enqueue(db, tenant_id)
    assert job.status == "pending"
    assert job.started_at is None
    assert job.input_payload != {"note": "demo", "billed_codes": []}
    assert job_queue.job_input_payload(job) == {"note": "demo", "billed_codes": []}

    claimed = job_queue.claim_next_pending(db)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "processing"
    assert claimed.started_at is not None


def test_idempotency(db_tenant):
    db, tenant_id = db_tenant
    key = f"idem-{uuid.uuid4().hex}"

    first = _enqueue(db, tenant_id, idempotency_key=key)
    second = _enqueue(db, tenant_id, idempotency_key=key)

    assert first.id == second.id
    assert db.query(Job).filter(Job.idempotency_key == key).count() == 1


def test_mark_completed(db_tenant):
    db, tenant_id = db_tenant
    _drain_pending(db)
    _enqueue(db, tenant_id)

    job = job_queue.claim_next_pending(db)
    assert job is not None

    result = {"recovered_revenue": 1234.5, "identified_codes": []}
    job_queue.mark_completed(db, job, result)

    db.expire(job)  # force a reload so we assert what actually hit the DB
    assert job.status == "completed"
    assert job.result_payload != result
    assert job_queue.job_result_payload(job) == result
    assert job.completed_at is not None


def test_mark_failed(db_tenant):
    db, tenant_id = db_tenant
    _drain_pending(db)
    _enqueue(db, tenant_id)

    job = job_queue.claim_next_pending(db)
    assert job is not None

    job_queue.mark_failed(db, job, "boom: model timeout")

    db.expire(job)
    assert job.status == "failed"
    assert job.error_message == "boom: model timeout"
    assert job.completed_at is not None


def test_tenant_isolation(db_tenant):
    from core import models

    db, tenant_a = db_tenant
    # Second tenant flushed (not committed) so the FK is satisfied; the fixture
    # rollback discards it and its jobs on teardown.
    tenant_b_row = models.Tenant(name=f"jobs-test-b-{uuid.uuid4().hex[:8]}")
    db.add(tenant_b_row)
    db.flush()
    tenant_b = tenant_b_row.id

    job_a = _enqueue(db, tenant_a)
    job_b = _enqueue(db, tenant_b)

    # Cross-tenant reads return None; each tenant sees only its own job.
    assert job_queue.get_job(db, job_b.id, tenant_a) is None
    assert job_queue.get_job(db, job_a.id, tenant_b) is None
    assert job_queue.get_job(db, job_b.id, tenant_b) is not None
    assert job_queue.get_job(db, job_a.id, tenant_a) is not None


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def test_api_202(client, tenant_api_key):
    # Needs a DB (job insert) + a real tenant for the FK; skips otherwise.
    headers = tenant_api_key(["clinician"])
    resp = client.post(
        "/api/shadow/audit",
        headers=headers,
        json={"note": "demo", "billed_codes": [], "demo": True},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert body["poll_url"] == f"/api/jobs/{body['job_id']}"


def test_api_sync(client, auth_headers):
    # ?sync=true runs inline; demo=True forces the deterministic diabetic note.
    # Works without a DB — persistence soft-fails and the result still returns.
    resp = client.post(
        "/api/shadow/audit?sync=true",
        headers=auth_headers,
        json={"note": "demo", "billed_codes": [], "demo": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "identified_codes" in body
    assert "recovered_revenue" in body
    assert body["intent_detected"] == "shadow_mode_rcm"


def test_api_job_poll(client, tenant_api_key):
    headers = tenant_api_key(["clinician"])
    enqueue_resp = client.post(
        "/api/shadow/audit",
        headers=headers,
        json={"note": "demo", "billed_codes": [], "demo": True},
    )
    assert enqueue_resp.status_code == 202
    job_id = enqueue_resp.json()["job_id"]

    poll = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert poll.status_code == 200
    body = poll.json()
    assert body["job_id"] == job_id
    # The worker is disabled under pytest, so the job stays pending.
    assert body["status"] in {"pending", "processing", "completed"}


def test_get_job_invalid_uuid_is_400(client, auth_headers):
    resp = client.get("/api/jobs/not-a-uuid", headers=auth_headers)
    assert resp.status_code == 400


def test_tenant_cannot_poll_another_tenants_job(client, tenant_api_key):
    # API-level mirror of test_tenant_isolation: a job enqueued by tenant A is
    # 404 (not 403/200) when polled with tenant B's key.
    headers_a = tenant_api_key(["clinician"])
    headers_b = tenant_api_key(["clinician"])

    enqueue_resp = client.post(
        "/api/shadow/audit",
        headers=headers_a,
        json={"note": "demo", "billed_codes": [], "demo": True},
    )
    assert enqueue_resp.status_code == 202
    job_id = enqueue_resp.json()["job_id"]

    assert client.get(f"/api/jobs/{job_id}", headers=headers_a).status_code == 200
    assert client.get(f"/api/jobs/{job_id}", headers=headers_b).status_code == 404
