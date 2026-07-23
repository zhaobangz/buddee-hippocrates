"""Async background worker for the Buddi jobs queue.

This module can run in-process from the FastAPI lifespan or as the standalone
entrypoint for a separate Cloud Run ``buddi-worker`` service. It keeps draining
after per-job failures so one bad payload never crashes the queue.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from core import jobs as job_store
from core.agent import Agent
from core.database import SessionLocal
from core.db_session import GucStamper, set_tenant_context, set_worker_context
from core.models import Job
from core.phi_guard import assert_phi_processing_allowed, payload_is_synthetic
from core.safety import redact_for_logs

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = float(os.getenv("BUDDI_WORKER_POLL_INTERVAL", "2"))
# I-1/QW-9: when the queue is empty the poll interval backs off exponentially
# up to this ceiling, so an idle worker stops costing ~43k queries/day.
POLL_MAX_INTERVAL_SECONDS = float(os.getenv("BUDDI_WORKER_POLL_MAX_INTERVAL", "30"))


def next_idle_delay(idle_streak: int) -> float:
    """Exponential backoff for empty-queue polls (2s → 4s → 8s → … → max)."""

    return min(POLL_INTERVAL_SECONDS * (2 ** max(idle_streak, 0)), POLL_MAX_INTERVAL_SECONDS)


async def process_job(agent: Agent, job: Job, input_payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a job to the correct agent method. Returns result dict."""

    if job.job_type == "shadow_audit":
        result = await agent.run_shadow_audit(input_payload)
    elif job.job_type == "prior_auth":
        result = await agent.run_prior_auth(input_payload)
    else:
        raise ValueError(f"Unknown job_type: {job.job_type}")
    return result


async def worker_loop(agent: Agent, stop_event: asyncio.Event | None = None) -> None:
    """Continuously polls for pending jobs until stopped or cancelled."""

    logger.info(
        "Buddi worker loop started (poll_interval=%.1fs, max_idle_interval=%.1fs)",
        POLL_INTERVAL_SECONDS,
        POLL_MAX_INTERVAL_SECONDS,
    )
    idle_streak = 0
    while True:
        if stop_event and stop_event.is_set():
            break
        db = SessionLocal()
        # Re-stamp the worker/tenant GUCs at every transaction start.
        # ``set_config(..., true)`` is transaction-scoped, so the commit
        # right after claiming a job used to clear ``app.worker_mode`` for
        # the rest of the loop body — breaking the job-status UPDATE under
        # FORCE RLS on production Postgres.
        stamper = GucStamper(tenant_id=None, worker_mode=True)
        try:
            stamper.install(db)
            job = job_store.claim_next_pending(db)
            if job is None:
                stamper.remove(db)
                db.close()
                await asyncio.sleep(next_idle_delay(idle_streak))
                idle_streak += 1
                continue
            idle_streak = 0
            db.commit()
            logger.info(
                "Processing job id=%s type=%s tenant=%s",
                job.id,
                job.job_type,
                job.tenant_id,
            )
            try:
                input_payload = job_store.job_input_payload(job)
                stamper.set_tenant(db, job.tenant_id)
                assert_phi_processing_allowed(
                    db,
                    job.tenant_id,
                    synthetic=payload_is_synthetic(input_payload),
                )
                result = await process_job(agent, job, input_payload)
                job_store.mark_completed(db, job, result)
                db.commit()
                logger.info("Job completed id=%s", job.id)
            except Exception as e:
                db.rollback()
                db2 = SessionLocal()
                failure_stamper = GucStamper(tenant_id=None, worker_mode=True)
                try:
                    failure_stamper.install(db2)
                    j2 = db2.query(Job).filter_by(id=job.id).first()
                    if j2:
                        job_store.mark_failed(db2, j2, str(e))
                        db2.commit()
                finally:
                    failure_stamper.remove(db2)
                    db2.close()
                logger.exception("Job failed id=%s: %s", job.id, redact_for_logs(str(e)))
        except asyncio.CancelledError:
            stamper.remove(db)
            db.close()
            raise
        except Exception:
            logger.exception("Worker loop error (continuing)")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        finally:
            stamper.remove(db)
            try:
                set_tenant_context(db, None)
                set_worker_context(db, False)
            except Exception as exc:
                logger.debug("Failed to clear GUC in worker cleanup: %s", exc)
            try:
                db.close()
            except Exception as exc:
                logger.debug("Failed to close DB in worker cleanup: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop(Agent()))
