"""Buddi RCM & Compliance API — v4.1 (post-April-21 audit).

Changes relative to v4.0:

* SEC-01 — CORS allow-list is loaded from the ``CORS_ORIGINS`` env var.
  Wildcards are explicitly rejected. ``allow_credentials=True`` is enabled.
* SEC-02 — every router depends on :func:`backend.auth.require_api_client`,
  so no endpoint is publicly reachable.
* SEC-10 — the FHIR ingest endpoint validates the bundle with
  :class:`core.schemas.FHIRBundle` and rejects payloads larger than
  ``MAX_FHIR_BUNDLE_BYTES``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

import core.models as models
from backend.auth import require_api_client
from backend.fhir_client import FHIRAdapter
from core.agent import Agent
from core.database import engine, get_db  # noqa: F401 (engine re-exported for callers)
from core.schemas import MAX_FHIR_BUNDLE_BYTES, FHIRBundle
from core.tracing import get_tracer, setup_tracing, shutdown_tracing

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Tracing bootstrap ----------------------------------------------------
try:
    setup_tracing(service_name="buddi-rcm-api")
    tracer = get_tracer(__name__)
except Exception:
    import opentelemetry.trace as trace

    tracer = trace.get_tracer(__name__)


# --- Lifespan -------------------------------------------------------------
agent: Optional[Agent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    with tracer.start_as_current_span("system_startup"):
        logger.info("Initializing RCM Agent System...")
        try:
            agent = Agent()
        except Exception as e:
            # In CI / test contexts we may not have full dependencies. We log
            # but do not crash — endpoints that need the agent will 503.
            logger.warning("Agent bootstrap failed: %s", e)
            agent = None
        yield
        logger.info("System optimized shutdown.")
        try:
            shutdown_tracing()
        except Exception:
            pass


# --- CORS ----------------------------------------------------------------
def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    # SEC-01: reject wildcards outright — allow_credentials=True + "*" is a
    # browser-enforced misconfiguration, but also violates our HIPAA posture.
    return [o for o in origins if o != "*"]


app = FastAPI(
    title="Buddi RCM & Compliance API",
    description="PostgreSQL-centric Backend for Shadow Mode RCM, Prior Auth, and Traceability",
    version="4.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# --- Request/response models --------------------------------------------
class PayloadRequest(BaseModel):
    payload: str
    task_type: Optional[str] = "detect"


# --- Audit helpers -------------------------------------------------------
def _generate_crypto_trail(action_type: str, data: str, previous_hash: str | None = None) -> str:
    timestamp = str(time.time())
    hash_input = f"{previous_hash or 'GENESIS'}:{action_type}:{data}:{timestamp}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def log_audit_event_postgres(
    db: Session,
    event_type: str,
    payload_data: dict,
    actor_id: str | None = None,
    tenant_id: str | None = None,
) -> str | None:
    """Append-only audit logger with cryptographic chaining."""
    try:
        last_event = (
            db.query(models.AuditEvent)
            .order_by(models.AuditEvent.event_id.desc())
            .first()
        )
        prev_hash = last_event.cryptographic_hash if last_event else None
        current_hash = _generate_crypto_trail(
            event_type, json.dumps(payload_data), prev_hash
        )
        new_event = models.AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload_data,
            previous_hash=prev_hash,
            cryptographic_hash=current_hash,
        )
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        return current_hash
    except Exception as e:
        logger.error("Audit log failed (DB likely offline): %s", e)
        db.rollback()
        return None


# --- Routes --------------------------------------------------------------
# NOTE: Every endpoint below is protected by ``require_api_client``.
# Even the health check requires a valid credential; use the internal
# container health probe (future DO-02) for anonymous liveness.

AUTH = Depends(require_api_client)


@app.get("/api/health")
async def health(client: str = AUTH, db: Session = Depends(get_db)):
    db_status = "offline"
    try:
        db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception:
        pass
    return {
        "status": "active",
        "db": db_status,
        "mode": "RCM_Audit_Postgres",
        "client": client,
    }


@app.post("/ingest/fhir")
async def process_fhir_bundle(
    request: Request,
    client: str = AUTH,
    db: Session = Depends(get_db),
):
    """Standardized entrypoint for HL7 FHIR payloads (SEC-10 validated)."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent unavailable")

    # SEC-10: enforce a hard byte cap before parsing JSON — a multi-gigabyte
    # payload must never make it into the agent pipeline.
    raw = await request.body()
    if len(raw) > MAX_FHIR_BUNDLE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"FHIR bundle exceeds {MAX_FHIR_BUNDLE_BYTES} bytes",
        )
    try:
        raw_bundle: Dict[str, Any] = json.loads(raw.decode("utf-8"))
        bundle = FHIRBundle.model_validate(raw_bundle)
    except (ValidationError, ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid FHIR bundle: {e}") from e

    with tracer.start_as_current_span("process_fhir_bundle") as span:
        agent_payload = FHIRAdapter.extract_from_bundle(bundle.model_dump())
        span.set_attribute("note_size_bytes", len(agent_payload["note"].encode("utf-8")))
        span.set_attribute("billed_code_count", len(agent_payload["billed_codes"]))

        audit_hash = log_audit_event_postgres(
            db,
            event_type="shadow_mode_rcm_fhir",
            payload_data={
                "input_len": len(agent_payload["note"]),
                "billed_codes": len(agent_payload["billed_codes"]),
            },
            actor_id=client,
        )

        response_json_str = agent.handle(
            json.dumps(agent_payload), task_type="shadow_mode_rcm"
        )
        try:
            response_obj = json.loads(response_json_str)
        except Exception:
            response_obj = {"raw_output": response_json_str}

        return {"status": "success", "response": response_obj, "audit_hash": audit_hash}


@app.post("/encounter/{encounter_id}/process")
async def process_encounter(
    encounter_id: str,
    client: str = AUTH,
    db: Session = Depends(get_db),
):
    log_audit_event_postgres(
        db,
        "encounter_processing_requested",
        {"encounter_id": encounter_id},
        actor_id=client,
    )
    return {"status": "processing_queued", "encounter_id": encounter_id}


@app.get("/billing/suggest")
async def billing_suggest(
    encounter_id: str | None = None,
    client: str = AUTH,
    db: Session = Depends(get_db),
):
    try:
        query = db.query(models.HccSuggestion)
        if encounter_id:
            query = query.filter(models.HccSuggestion.encounter_id == encounter_id)
        return {"suggestions": query.all()}
    except Exception as e:
        logger.error("Suggest endpoint DB failure: %s", e)
        return {"error": "Database error", "suggestions": []}


@app.post("/prior-auth/generate")
async def generate_prior_auth(
    encounter_id: str,
    procedure_code: str,
    client: str = AUTH,
    db: Session = Depends(get_db),
):
    try:
        new_auth = models.PriorAuthorizationRequest(
            encounter_id=encounter_id, procedure_code=procedure_code
        )
        db.add(new_auth)
        db.commit()
        db.refresh(new_auth)

        new_state = models.PriorAuthState(prior_auth_id=new_auth.id, state="draft")
        db.add(new_state)
        db.commit()

        log_audit_event_postgres(
            db,
            "prior_auth_requested",
            {"auth_id": str(new_auth.id), "procedure": procedure_code},
            actor_id=client,
        )
        return {"status": "drafted", "auth_request_id": str(new_auth.id)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/audit/query")
async def get_audit_logs(client: str = AUTH, db: Session = Depends(get_db)):
    try:
        events = (
            db.query(models.AuditEvent)
            .order_by(models.AuditEvent.event_id.desc())
            .limit(20)
            .all()
        )
        return {"events": events}
    except Exception as e:
        logger.error("Audit lookup failure: %s", e)
        return {"events": []}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
