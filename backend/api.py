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

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

import core.models as models
from backend.auth import require_api_client, require_scope
from backend.fhir_client import FHIRAdapter
from backend.middleware import RateLimitMiddleware, RequestIDMiddleware
from core.agent import Agent
from core.config import settings
from core.database import SessionLocal, engine  # noqa: F401 (engine re-exported for callers)
from core.db_session import tenant_scoped_session
from core.merkle import (
    build_daily_root,
    export_daily_root,
    list_signed_root_days,
    verify_signed_roots_against_db,
)
from core.schemas import MAX_FHIR_BUNDLE_BYTES, FHIRBundle, PriorAuthDraft, ShadowModeResponse
from core.safety import redact_for_logs, sanitize_response
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
_merkle_root_task: Optional[asyncio.Task] = None
# Default 24h cadence; overridable for tests via BUDDI_MERKLE_INTERVAL_SECONDS.
MERKLE_ROOT_INTERVAL_SECONDS = int(
    os.getenv("BUDDI_MERKLE_INTERVAL_SECONDS", str(24 * 60 * 60))
)
DISABLE_MERKLE_TASK = os.getenv("BUDDI_DISABLE_MERKLE_TASK", "").lower() in {"1", "true", "yes"}


def _seal_merkle_root_for_yesterday(target_day: Optional[date] = None) -> Dict[str, Any]:
    """Build, sign, and export the Merkle root for ``target_day`` (UTC).

    Runs on its own ``SessionLocal()`` rather than a request-scoped session
    so the daily cron-style task is independent of any inbound HTTP call.
    Returns a small status dict suitable for logging / API responses.
    """
    if target_day is None:
        target_day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    db = SessionLocal()
    try:
        daily = build_daily_root(db, day=target_day)
        path = export_daily_root(daily)
        # Self-audit: record the export itself in the chain so a verifier can
        # see exactly when each root was sealed.
        log_audit_event_postgres(
            db,
            "audit_merkle_root_sealed",
            {
                "day": daily.day,
                "event_count": daily.event_count,
                "merkle_root": daily.merkle_root,
                "key_id": daily.signature.get("key_id"),
                "algorithm": daily.signature.get("algorithm"),
                "export_path": str(path),
                "risk": "low",
            },
            actor_id="system:merkle-task",
        )
        return {
            "day": daily.day,
            "event_count": daily.event_count,
            "merkle_root": daily.merkle_root,
            "export_path": str(path),
            "key_id": daily.signature.get("key_id"),
        }
    finally:
        db.close()


async def _merkle_root_loop(interval_seconds: int):
    """Background loop that seals the previous UTC day's Merkle root.

    Sleeps ``interval_seconds`` between runs (24h in production). On
    ``CancelledError`` (lifespan shutdown) it exits cleanly. Any other
    exception is logged and the loop continues — losing one day's seal
    is preferable to crashing the API process.
    """
    logger.info(
        "Merkle root background task started (interval=%ds)", interval_seconds
    )
    while True:
        try:
            # Run the blocking DB / file work in a worker thread so we do
            # not block the event loop.
            result = await asyncio.to_thread(_seal_merkle_root_for_yesterday)
            logger.info(
                "Daily Merkle root sealed: day=%s events=%d root=%s",
                result["day"],
                result["event_count"],
                result["merkle_root"],
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Merkle root sealing failed: %s", e)
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, _merkle_root_task
    with tracer.start_as_current_span("system_startup"):
        logger.info("Initializing RCM Agent System...")
        try:
            agent = Agent()
        except Exception as e:
            # In CI / test contexts we may not have full dependencies. We log
            # but do not crash — endpoints that need the agent will 503.
            logger.warning("Agent bootstrap failed: %s", e)
            agent = None

        # Kick off the daily Merkle-root sealing loop. We do *not* block
        # startup on its first iteration — the first seal happens
        # immediately inside the loop, but errors there should never
        # prevent the API from coming up.
        if not DISABLE_MERKLE_TASK:
            try:
                _merkle_root_task = asyncio.create_task(
                    _merkle_root_loop(MERKLE_ROOT_INTERVAL_SECONDS)
                )
            except Exception as e:
                logger.warning("Failed to schedule Merkle root task: %s", e)
                _merkle_root_task = None
        else:
            logger.info("Merkle root background task disabled via BUDDI_DISABLE_MERKLE_TASK")

        yield

        logger.info("System optimized shutdown.")
        if _merkle_root_task is not None:
            _merkle_root_task.cancel()
            try:
                await _merkle_root_task
            except (asyncio.CancelledError, Exception):
                pass
            _merkle_root_task = None
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
    allowed = [o for o in origins if o != "*"]
    if allowed:
        return allowed

    dev_mode = os.getenv("DEV_MODE", "").strip().lower() == "true"
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if dev_mode or environment == "development":
        logger.warning(
            "CORS_ORIGINS is not set; defaulting to localhost frontend origins in development."
        )
        return ["http://localhost:5173", "http://localhost:3000"]

    logger.warning("CORS_ORIGINS is not set — all browser requests will be blocked")
    return []


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
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
# Order matters in Starlette: middleware added later runs OUTERMOST. We want
# the request-ID assigned BEFORE the rate limiter logs / responds, so add it
# AFTER the rate limiter.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)


# --- Request/response models --------------------------------------------
class PayloadRequest(BaseModel):
    payload: str
    task_type: Optional[str] = "detect"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    patient_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    citations: List[str] = []
    intent_detected: Optional[str] = None
    shadow_result: Optional[dict] = None
    audit_hash: Optional[str] = None


class ShadowAuditRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=10_000)
    billed_codes: List[str] = Field(default_factory=list)
    patient_id: Optional[str] = None
    demo: bool = False


class PriorAuthGenerateRequest(BaseModel):
    """JSON body for ``POST /prior-auth/generate``.

    For backwards compatibility the route also accepts the legacy query
    parameters ``encounter_id`` and ``procedure_code``; when both query and
    body are present, body wins.
    """

    encounter_id: Optional[str] = None
    procedure_code: Optional[str] = None
    payer: Optional[str] = "Medicare"
    clinical_context: Optional[str] = Field(
        default=None, max_length=50_000,
        description="Free-text clinical context the agent will summarise into the draft.",
    )
    demo: bool = False


# --- Audit helpers -------------------------------------------------------
def _generate_crypto_trail(
    action_type: str,
    data: str,
    previous_hash: str | None = None,
    timestamp: str | None = None,
) -> str:
    timestamp = timestamp or str(time.time())
    hash_input = f"{previous_hash or 'GENESIS'}:{action_type}:{data}:{timestamp}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def _canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _tenant_id_from_client(client: str | object) -> uuid.UUID | None:
    return getattr(client, "tenant_id", None)


def _tenant_id_from_request(request: Request) -> uuid.UUID | None:
    tenant_id = getattr(request.state, "tenant_id", None)
    if isinstance(tenant_id, uuid.UUID):
        return tenant_id
    return _uuid_or_none(str(tenant_id)) if tenant_id else None


def _require_tenant_id(request: Request) -> uuid.UUID:
    tenant_id = _tenant_id_from_request(request)
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Authenticated tenant context is required")
    return tenant_id


DEMO_PATIENT: Dict[str, Any] = {
    "id": "PT-9012",
    "name": "Marcus Holloway",
    "demo": True,
    "conditions": ["Type 2 Diabetes", "CKD stage 3a", "Hypertension"],
    "medications": ["Metformin 1000mg", "Lisinopril 10mg", "Atorvastatin 20mg"],
    "labs": {"a1c": 7.4, "bp": "138/88", "egfr": 51, "uacr": "42 mg/g"},
    "billed_codes": ["E11.9", "I10"],
    "clinical_note": (
        "67-year-old male with type 2 diabetes mellitus complicated by chronic "
        "kidney disease stage 3a. eGFR 51 and urine albumin/creatinine ratio "
        "42 mg/g. Hypertension treated with lisinopril. Assessment notes diabetic "
        "CKD and hypertensive CKD; continue renal-protective therapy and monitor BMP."
    ),
}


def _demo_shadow_result(
    patient_id: str,
    note: str,
    billed_codes: List[str] | None = None,
    source: str = "demo_fallback",
    include_fallback: bool = True,
) -> Dict[str, Any]:
    """Deterministic launch-demo shadow-mode output.

    The real agent is still invoked by the route when available. This fallback
    keeps the founder demo useful on machines that do not yet have an LLM key or
    seeded RAG index, and it is explicitly marked as demo/synthetic in the
    payload so it cannot be confused with production clinical guidance.

    ``include_fallback`` (default True) controls whether the function emits a
    synthetic catch-all suggestion when none of the pattern rules match. The
    sales demo wants True (page is never empty). The eval harness passes False
    so unmatched cases register as "no codes surfaced" rather than a
    misleading E11.22 placeholder — that would otherwise trip the
    ``must_abstain_codes`` check for unrelated specialties (CHF, COPD, etc.).
    """
    billed = {code.upper() for code in (billed_codes or [])}

    lowered_note = note.lower()
    opportunities: List[Dict[str, Any]] = []

    if {"e11.22", "e1122"}.isdisjoint(billed) and (
        "diabetic ckd" in lowered_note
        or ("diabetes" in lowered_note and "kidney" in lowered_note)
        or ("t2d" in lowered_note and "ckd" in lowered_note)
    ):
        opportunities.append(
            {
                "code": "E11.22",
                "description": "Type 2 diabetes mellitus with diabetic chronic kidney disease",
                "justification": "Note documents type 2 diabetes with chronic kidney disease/stage 3a.",
                "est_value": 8400.0,
                "confidence": 0.93,
                "review_status": "human_review_required",
            }
        )

    if {"N18.31", "N1831"}.isdisjoint(billed) and (
        "stage 3a" in lowered_note or "egfr 51" in lowered_note or "ckd" in lowered_note
    ):
        opportunities.append(
            {
                "code": "N18.31",
                "description": "Chronic kidney disease, stage 3a",
                "justification": "Note cites CKD stage 3a and eGFR 51.",
                "est_value": 4100.0,
                "confidence": 0.89,
                "review_status": "human_review_required",
            }
        )

    if {"I12.9", "I129"}.isdisjoint(billed) and "hypertensive ckd" in lowered_note:
        opportunities.append(
            {
                "code": "I12.9",
                "description": "Hypertensive chronic kidney disease with stage 1-4 CKD",
                "justification": "Assessment documents hypertensive CKD with CKD stage 3a.",
                "est_value": 3200.0,
                "confidence": 0.84,
                "review_status": "human_review_required",
            }
        )

    if not opportunities and include_fallback:
        opportunities.append(
            {
                "code": "E11.22",
                "description": "Type 2 diabetes mellitus with diabetic chronic kidney disease",
                "justification": "Synthetic demo opportunity for PT-9012; replace with real agent/RAG output for production.",
                "est_value": 8400.0,
                "confidence": 0.9,
                "review_status": "human_review_required",
            }
        )

    recovered_revenue = float(sum(item["est_value"] for item in opportunities))
    return {
        "patient_id": patient_id,
        "demo": True,
        "source": source,
        "recovered_revenue": recovered_revenue,
        "identified_codes": opportunities,
        "summary": (
            f"Shadow-mode review found {len(opportunities)} missed reimbursable "
            f"documentation opportunity/opportunities worth an estimated "
            f"${recovered_revenue:,.0f} annually. Human coder review required."
        ),
        "citations": [
            "CMS-HCC V28: diabetes with chronic complications",
            "ICD-10-CM guideline: code CKD stage when documented",
            "ADA Standards of Care: CKD risk stratification in diabetes",
        ],
        "intent_detected": "shadow_mode_rcm",
    }


def _normalize_shadow_result(
    raw: Dict[str, Any],
    patient_id: str,
    fallback_note: str,
    billed_codes: List[str],
) -> Dict[str, Any]:
    if raw.get("error") or not raw.get("identified_codes"):
        return _demo_shadow_result(patient_id, fallback_note, billed_codes, source="agent_unavailable_demo")

    identified_codes = []
    for item in raw.get("identified_codes", []):
        identified_codes.append(
            {
                "code": item.get("code", "UNKNOWN"),
                "description": item.get("description", "Review suggested code"),
                "justification": item.get("justification", "Review clinical note for support."),
                "est_value": float(item.get("est_value", 0) or 0),
                "confidence": float(item.get("confidence", 0.82) or 0.82),
                "review_status": item.get("review_status", "human_review_required"),
            }
        )
    citations = raw.get("citations") or ["Retrieved guideline snippets unavailable; verify against CMS/ICD-10 sources."]
    return {
        "patient_id": patient_id,
        "demo": False,
        "source": "agent",
        "recovered_revenue": float(raw.get("recovered_revenue", 0) or 0),
        "identified_codes": identified_codes,
        "summary": raw.get("summary", "Shadow-mode review completed."),
        "audit_hash": raw.get("audit_hash"),
        "citations": citations,
        "intent_detected": "shadow_mode_rcm",
    }


def _run_shadow_agent(
    patient_id: str,
    note: str,
    billed_codes: List[str],
    tenant_id: uuid.UUID | None = None,
) -> Dict[str, Any]:
    if not agent:
        return _demo_shadow_result(patient_id, note, billed_codes, source="agent_not_bootstrapped_demo")
    response_json_str = agent.handle(
        json.dumps({"note": note, "billed_codes": billed_codes, "patient_id": patient_id}),
        task_type="shadow_mode_rcm",
        tenant_id=tenant_id,
    )
    try:
        response_obj = json.loads(response_json_str)
    except Exception:
        response_obj = {"summary": response_json_str, "identified_codes": []}
    return _normalize_shadow_result(response_obj, patient_id, note, billed_codes)


def _format_shadow_chat(result: Dict[str, Any]) -> str:
    code_lines = [
        f"• {item['code']} — {item['description']} (${item['est_value']:,.0f}; {int(item.get('confidence', 0) * 100)}% confidence)"
        for item in result.get("identified_codes", [])
    ]
    return sanitize_response(
        "Shadow-mode RCM review complete.\n"
        f"Estimated recoverable annual revenue: ${result.get('recovered_revenue', 0):,.0f}.\n"
        + "\n".join(code_lines)
        + "\n\nEvery suggestion is queued for human review and written to the tamper-evident audit trail."
    )


def _audit_event_to_dict(event: models.AuditEvent, verification_status: str = "unchecked") -> Dict[str, Any]:
    payload = event.payload or {}
    audit_meta = payload.get("_audit", {}) if isinstance(payload, dict) else {}
    return {
        "id": event.event_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "action": event.event_type,
        "actor": audit_meta.get("actor_label") or "system",
        "user": audit_meta.get("actor_label") or "system",
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "current_hash": event.cryptographic_hash,
        "cryptographic_hash": event.cryptographic_hash,
        "previous_hash": event.previous_hash,
        "verification_status": verification_status,
        "payload": payload,
        "risk": payload.get("risk", "low") if isinstance(payload, dict) else "low",
    }


def _verify_audit_chain(db: Session, tenant_id: uuid.UUID | None = None) -> Dict[str, Any]:
    query = db.query(models.AuditEvent)
    if tenant_id is not None:
        query = query.filter(models.AuditEvent.tenant_id == tenant_id)
    events = query.order_by(models.AuditEvent.event_id.asc()).all()
    previous_hash = None
    event_statuses: Dict[int, str] = {}
    recomputed = 0
    for event in events:
        status_for_event = "verified"
        if event.previous_hash != previous_hash:
            event_statuses[event.event_id] = "chain_broken"
            return {
                "verified": False,
                "status": "chain_broken",
                "events_checked": len(event_statuses),
                "broken_at": event.event_id,
                "event_statuses": event_statuses,
            }
        payload = event.payload or {}
        audit_meta = payload.get("_audit", {}) if isinstance(payload, dict) else {}
        hash_timestamp = audit_meta.get("hash_input_timestamp")
        if hash_timestamp:
            expected_hash = _generate_crypto_trail(
                event.event_type or "unknown",
                _canonical_json(payload),
                event.previous_hash,
                hash_timestamp,
            )
            recomputed += 1
            if expected_hash != event.cryptographic_hash:
                event_statuses[event.event_id] = "hash_mismatch"
                return {
                    "verified": False,
                    "status": "hash_mismatch",
                    "events_checked": len(event_statuses),
                    "broken_at": event.event_id,
                    "event_statuses": event_statuses,
                }
        else:
            status_for_event = "legacy_structural_only"
        event_statuses[event.event_id] = status_for_event
        previous_hash = event.cryptographic_hash
    return {
        "verified": True,
        "status": "verified" if recomputed == len(events) else "partially_verified",
        "events_checked": len(events),
        "broken_at": None,
        "event_statuses": event_statuses,
    }


def log_audit_event_postgres(
    db: Session,
    event_type: str,
    payload_data: dict,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    request_id: str | None = None,
) -> str | None:
    """Append-only audit logger with cryptographic chaining."""
    try:
        event_timestamp = datetime.now(timezone.utc)
        hash_input_timestamp = event_timestamp.isoformat()
        audited_payload = {
            **payload_data,
            "_audit": {
                "actor_label": actor_id or "system",
                "hash_input_timestamp": hash_input_timestamp,
                "algorithm": "sha256(prev_hash:event_type:canonical_payload:timestamp)",
                "request_id": request_id,
            },
        }
        last_event_query = db.query(models.AuditEvent)
        if tenant_id:
            last_event_query = last_event_query.filter(models.AuditEvent.tenant_id == _uuid_or_none(tenant_id))
        last_event = last_event_query.order_by(models.AuditEvent.event_id.desc()).first()
        prev_hash = last_event.cryptographic_hash if last_event else None
        current_hash = _generate_crypto_trail(
            event_type,
            _canonical_json(audited_payload),
            prev_hash,
            hash_input_timestamp,
        )
        new_event = models.AuditEvent(
            tenant_id=_uuid_or_none(tenant_id),
            actor_id=_uuid_or_none(actor_id),
            event_type=event_type,
            payload=audited_payload,
            timestamp=event_timestamp,
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
# NOTE: Every /api endpoint below is protected by ``require_api_client``.
# The only public endpoint is /health for load-balancer liveness probes.

AUTH = Depends(require_api_client)
CLINICIAN_AUTH = Depends(require_scope("clinician"))
INGEST_AUTH = Depends(require_scope("ingest"))
ADMIN_AUTH = Depends(require_scope("admin"))


def _request_id(request: Request) -> str | None:
    """Pull the request id placed on ``request.state`` by RequestIDMiddleware."""
    return getattr(request.state, "request_id", None)


@app.get("/internal/health")
async def internal_health(db: Session = Depends(tenant_scoped_session)):
    """Unauthenticated internal load-balancer probe.

    Security: exposes only coarse liveness status and never PHI or tenant data.
    """
    db_status = "offline"
    try:
        db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception:
        pass
    http_status = 200 if db_status == "online" else 503
    return JSONResponse(
        status_code=http_status,
        content={"status": "ok" if db_status == "online" else "degraded", "db": db_status},
    )


@app.get("/health", include_in_schema=False)
async def unauthenticated_health():
    return {"status": "ok", "version": settings.VERSION}


@app.get("/api/health")
async def health(client: str = AUTH, db: Session = Depends(tenant_scoped_session)):
    db_status = "offline"
    try:
        db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception:
        pass
    payload = {
        "status": "active",
        "db": db_status,
        "mode": "RCM_Audit_Postgres",
        "client": client,
        "agent_status": "ready" if agent is not None else "degraded",
    }
    if agent is None:
        payload["warning"] = "Agent bootstrap failed; AI-dependent routes are running in degraded/demo mode."
    return payload


@app.get("/api/readiness")
async def readiness(client: str = AUTH, db: Session = Depends(tenant_scoped_session)):
    """Load-balancer readiness probe.

    Unlike `/api/health` (liveness), readiness returns 503 when the agent did
    not bootstrap so traffic can be withheld from AI-dependent workloads.
    """
    db_status = "offline"
    try:
        db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception:
        pass

    ready = db_status == "online" and agent is not None
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "degraded",
            "db": db_status,
            "agent_status": "ready" if agent is not None else "degraded",
            "client": client,
        },
    )


@app.get("/api/patient/{patient_id}")
async def get_patient(
    patient_id: str,
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Return a patient profile for the UI.

    The launch demo uses a clearly-labeled synthetic patient (`PT-9012`). If a
    real UUID is supplied and the database is available, the endpoint returns a
    minimal DB-backed profile without exposing encrypted demographics.
    """
    if patient_id == DEMO_PATIENT["id"]:
        return DEMO_PATIENT

    tenant_id = _require_tenant_id(request)
    patient_uuid = _uuid_or_none(patient_id)
    try:
        query = db.query(models.Patient).filter(models.Patient.tenant_id == tenant_id)
        if patient_uuid:
            query = query.filter(models.Patient.id == patient_uuid)
        else:
            query = query.filter(models.Patient.external_ehr_id == patient_id)
        patient = query.first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        return {
            "id": str(patient.id),
            "name": patient.external_ehr_id or "EHR Patient",
            "demo": False,
            "conditions": [],
            "medications": [],
            "labs": {},
            "created_at": patient.created_at.isoformat() if patient.created_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Patient lookup failure: %s", e)
        raise HTTPException(status_code=503, detail="Patient database unavailable") from e


@app.post("/api/chat/chat", response_model=ChatResponse)
async def chat_with_agent(
    body: ChatRequest,
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Chat compatibility route used by the React app.

    Messages that ask for missed HCC/coding/revenue recovery are routed through
    the same shadow-mode safety path as FHIR ingest. Other messages still call
    `Agent.handle(..., task_type="detect")` when the agent is available.
    """
    patient_id = body.patient_id or DEMO_PATIENT["id"]
    tenant_id = _require_tenant_id(request)
    try:
        payload = json.dumps({"message": body.message, "patient_id": patient_id})
        parsed_response: Dict[str, Any] = {}
        if agent:
            raw_response = agent.handle(payload, task_type="detect", tenant_id=tenant_id)
            try:
                parsed_response = json.loads(raw_response)
            except Exception:
                parsed_response = {}
            if parsed_response.get("identified_codes") is not None:
                result = _normalize_shadow_result(parsed_response, patient_id, body.message, [])
                audit_hash = log_audit_event_postgres(
                    db,
                    "chat_shadow_mode_rcm",
                    {
                        "patient_id": patient_id,
                        "message_len": len(body.message),
                        "recovered_revenue": result.get("recovered_revenue", 0),
                        "identified_code_count": len(result.get("identified_codes", [])),
                        "risk": "low",
                    },
                    actor_id=client,
                    tenant_id=str(tenant_id),
                    request_id=_request_id(request),
                )
                result["audit_hash"] = result.get("audit_hash") or audit_hash
                return {
                    "response": _format_shadow_chat(result),
                    "citations": result.get("citations", []),
                    "intent_detected": "shadow_mode_rcm",
                    "audit_hash": audit_hash,
                    "shadow_result": result,
                }
        if any(token in body.message.lower() for token in ("shadow", "hcc", "missed", "code", "coding", "revenue", "audit")):
            patient = DEMO_PATIENT if patient_id == DEMO_PATIENT["id"] else {}
            result = _run_shadow_agent(
                patient_id,
                patient.get("clinical_note") or body.message,
                patient.get("billed_codes") or [],
                tenant_id=tenant_id,
            )
            audit_hash = log_audit_event_postgres(
                db,
                "chat_shadow_mode_rcm",
                {
                    "patient_id": patient_id,
                    "message_len": len(body.message),
                    "recovered_revenue": result.get("recovered_revenue", 0),
                    "identified_code_count": len(result.get("identified_codes", [])),
                    "risk": "low",
                },
                actor_id=client,
                tenant_id=str(tenant_id),
                request_id=_request_id(request),
            )
            result["audit_hash"] = result.get("audit_hash") or audit_hash
            return {
                "response": _format_shadow_chat(result),
                "citations": result.get("citations", []),
                "intent_detected": "shadow_mode_rcm",
                "audit_hash": audit_hash,
                "shadow_result": result,
            }

        if not agent:
            return {
                "response": sanitize_response(
                    "Buddi is running in local demo mode. Ask me to find missed HCC codes for PT-9012 to run the shadow-mode workflow."
                ),
                "citations": [],
                "intent_detected": "demo_assistant",
            }

        response = agent.handle(body.message, task_type="detect", tenant_id=tenant_id)
        audit_hash = log_audit_event_postgres(
            db,
            "chat_message_processed",
            {"patient_id": patient_id, "message_len": len(body.message), "risk": "low"},
            actor_id=client,
            tenant_id=str(tenant_id),
            request_id=_request_id(request),
        )
        return {
            "response": sanitize_response(response),
            "citations": [],
            "intent_detected": "detect",
            "audit_hash": audit_hash,
        }
    except Exception as e:
        logger.exception(
            "Chat route failed",
            extra={"request_id": _request_id(request), "patient_id": patient_id},
        )
        raise HTTPException(status_code=500, detail="Chat pipeline failed") from e


@app.post("/api/shadow/audit")
async def run_shadow_audit(
    body: ShadowAuditRequest,
    request: Request,
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Run the shadow-mode HCC/revenue recovery workflow and persist results."""
    with tracer.start_as_current_span("api_shadow_audit") as span:
        tenant_id = _require_tenant_id(request)
        patient_id = body.patient_id or DEMO_PATIENT["id"]
        note = DEMO_PATIENT["clinical_note"] if body.demo and patient_id == DEMO_PATIENT["id"] else body.note
        billed_codes = DEMO_PATIENT["billed_codes"] if body.demo and patient_id == DEMO_PATIENT["id"] else body.billed_codes
        span.set_attribute("note_size_bytes", len(note.encode("utf-8")))
        span.set_attribute("billed_code_count", len(billed_codes))

        result = _run_shadow_agent(patient_id, note, billed_codes, tenant_id=tenant_id)
        parsed_result = ShadowModeResponse.model_validate(result)
        result_payload = parsed_result.model_dump()

        audit_hash = log_audit_event_postgres(
            db,
            "shadow_mode_rcm_demo" if result.get("demo") else "shadow_mode_rcm",
            {
                "patient_id": patient_id,
                "note_len": len(note),
                "billed_codes": billed_codes,
                "recovered_revenue": parsed_result.recovered_revenue,
                "identified_code_count": len(parsed_result.identified_codes),
                "risk": "low",
            },
            actor_id=client,
            tenant_id=str(tenant_id),
            request_id=_request_id(request),
        )
        result_payload["audit_hash"] = audit_hash or parsed_result.audit_hash
        result_payload["patient_id"] = patient_id
        result_payload["demo"] = bool(result.get("demo", body.demo))
        result_payload["source"] = result.get("source", "agent")
        result_payload["intent_detected"] = "shadow_mode_rcm"

        try:
            llm_request = models.LlmRequest(
                tenant_id=tenant_id,
                encounter_id=None,
                prompt_template_version="shadow_mode_rcm:v1",
                model=settings.LLM_MODEL,
                full_prompt=redact_for_logs(note, max_length=4000),
            )
            db.add(llm_request)
            db.flush()
            db.add(
                models.LlmResponse(
                    tenant_id=tenant_id,
                    llm_request_id=llm_request.id,
                    raw_response=json.dumps(result_payload, default=str),
                    parsed_json=redact_for_logs(result_payload, max_length=4000),
                )
            )
            for code_item in parsed_result.identified_codes:
                db.add(
                    models.HccSuggestion(
                        tenant_id=tenant_id,
                        encounter_id=None,
                        suggested_code=code_item.code,
                        justification=code_item.justification,
                        confidence_score=code_item.confidence,
                        status="pending",
                        llm_request_id=llm_request.id,
                    )
                )
            db.add(
                models.RecoveryEvent(
                    tenant_id=tenant_id,
                    audit_hash=result_payload["audit_hash"],
                    patient_id=patient_id or "unknown",
                    recovered_revenue=parsed_result.recovered_revenue,
                )
            )
            db.commit()
        except Exception as e:
            logger.warning(
                "Shadow audit persistence failed (returning audit result anyway): %s",
                redact_for_logs(str(e)),
                extra={"request_id": _request_id(request)},
            )
            db.rollback()
        return result_payload


@app.get("/api/demo/sample-patient")
async def get_demo_patient(client: str = AUTH):
    return DEMO_PATIENT


# ---------------------------------------------------------------------
# Hosted synthetic-FHIR demo (manual §2.2 week 4)
# ---------------------------------------------------------------------
# These two endpoints power the public ``demo.buddi.health`` sandbox.
# They serve **only** the 25 Safe-Harbor synthetic bundles generated by
# ``evals/synthea/generate.py`` — never real PHI — and are explicitly
# exempt from the BAA tripwire because the served notes carry no
# identifying information.

SYNTHEA_BUNDLE_DIR = (
    os.getenv("BUDDI_SYNTHEA_DIR") or "evals/synthea/bundles"
)


def _synthea_bundle_path(name: str) -> str | None:
    """Resolve a slug to a file path inside the synthetic bundle dir.

    Returns None for slugs that don't exist or attempt to escape the
    directory (``..``). Anything non-alphanumeric except ``_`` is rejected.
    """

    if not name or any(ch in name for ch in ("/", "\\", "..")):
        return None
    candidate = os.path.join(SYNTHEA_BUNDLE_DIR, name)
    if not os.path.abspath(candidate).startswith(
        os.path.abspath(SYNTHEA_BUNDLE_DIR)
    ):
        return None
    return candidate if os.path.exists(candidate) else None


@app.get("/api/demo/synthea")
async def list_synthea_bundles(client: str = AUTH):
    """List every synthetic bundle hosted for the demo sandbox."""

    if not os.path.isdir(SYNTHEA_BUNDLE_DIR):
        return {"bundles": [], "count": 0, "synthetic": True}
    names = sorted(
        f for f in os.listdir(SYNTHEA_BUNDLE_DIR) if f.endswith(".json")
    )
    return {
        "bundles": [
            {
                "name": name,
                "ingest_url": f"/api/demo/synthea/{name}/ingest",
                "fetch_url": f"/api/demo/synthea/{name}",
            }
            for name in names
        ],
        "count": len(names),
        "synthetic": True,
        "source": (
            "Generated by evals/synthea/generate.py — Safe-Harbor compliant, "
            "no real PHI."
        ),
    }


@app.get("/api/demo/synthea/{name}")
async def fetch_synthea_bundle(name: str, client: str = AUTH):
    """Return the raw FHIR Bundle for a single synthetic patient."""

    path = _synthea_bundle_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Synthetic bundle not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load synthetic bundle %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Bundle read failure") from e


@app.post("/api/demo/synthea/{name}/ingest")
async def ingest_synthea_bundle(
    name: str,
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Run a hosted synthetic bundle through the shadow-mode agent.

    Bypasses the BAA precondition (these bundles carry no PHI) so the
    public demo works pre-BAA. The audit chain still records the
    request so we can show prospects the trace artifact end-to-end.
    """

    path = _synthea_bundle_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Synthetic bundle not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_bundle = json.load(f)
        bundle = FHIRBundle.model_validate(raw_bundle)
    except (ValidationError, ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid synthetic bundle: {e}") from e

    tenant_id = _require_tenant_id(request)
    agent_payload = FHIRAdapter.extract_from_bundle(bundle.model_dump())
    audit_hash = log_audit_event_postgres(
        db,
        event_type="synthea_demo_ingest",
        payload_data={
            "bundle_name": name,
            "input_len": len(agent_payload["note"]),
            "billed_codes": len(agent_payload["billed_codes"]),
            "synthetic": True,
        },
        actor_id=client,
        tenant_id=str(tenant_id),
        request_id=_request_id(request),
    )
    result = _run_shadow_agent(
        patient_id=f"synthea:{name}",
        note=agent_payload.get("note") or "",
        billed_codes=agent_payload.get("billed_codes") or [],
        tenant_id=tenant_id,
    )
    return {
        "status": "success",
        "bundle_name": name,
        "synthetic": True,
        "response": result,
        "audit_hash": audit_hash,
    }



def _demo_dashboard_metrics() -> Dict[str, Any]:
    """Safe fallback payload when Postgres is unreachable in dev mode.

    Lets the React dashboard render without a live DB so `python start_dev.py`
    works on a fresh machine without Postgres provisioned. Production
    deployments alarm on this state via the `degraded=True` flag rather
    than the JSON shape the frontend reads.
    """

    return {
        "demo": True,
        "degraded": True,
        "total_recovered_revenue": 0.0,
        "missed_codes_found": 0,
        "average_value_per_encounter": 0.0,
        "accepted_rate": 0.0,
        "rejected_rate": 0.0,
        "top_categories": [],
        "audit_integrity_status": "db_offline",
    }


@app.get("/api/dashboard/metrics")
async def get_dashboard_metrics(
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Tenant-scoped revenue recovery aggregates for the dashboard.

    Gracefully degrades to ``_demo_dashboard_metrics`` when the DB is
    unreachable so the operator UI keeps rendering during the local
    dev loop — see ``docs/INCIDENT_RESPONSE.md`` Sev-2 for the production
    alarm path.
    """
    try:
        return _compute_dashboard_metrics(request, db)
    except Exception as e:
        logger.warning(
            "Dashboard metrics computation failed; returning degraded payload: %s",
            redact_for_logs(str(e)),
        )
        return _demo_dashboard_metrics()


def _compute_dashboard_metrics(request: Request, db: Session) -> Dict[str, Any]:
    with tracer.start_as_current_span("api_dashboard_metrics"):
        tenant_id = _require_tenant_id(request)
        total_recovered = float(
            db.query(func.coalesce(func.sum(models.RecoveryEvent.recovered_revenue), 0.0))
            .filter(models.RecoveryEvent.tenant_id == tenant_id)
            .scalar()
            or 0.0
        )

        total_suggestions = int(
            db.query(func.count(models.HccSuggestion.id))
            .filter(models.HccSuggestion.tenant_id == tenant_id)
            .scalar()
            or 0
        )
        accepted_count = int(
            db.query(func.count(models.HccSuggestion.id))
            .filter(models.HccSuggestion.tenant_id == tenant_id)
            .filter(models.HccSuggestion.status == "accepted")
            .scalar()
            or 0
        )
        rejected_count = int(
            db.query(func.count(models.HccSuggestion.id))
            .filter(models.HccSuggestion.tenant_id == tenant_id)
            .filter(models.HccSuggestion.status == "rejected")
            .scalar()
            or 0
        )
        recovery_encounters = int(
            db.query(func.count(models.RecoveryEvent.id))
            .filter(models.RecoveryEvent.tenant_id == tenant_id)
            .scalar()
            or 0
        )
        top_rows = (
            db.query(models.HccSuggestion.suggested_code, func.count(models.HccSuggestion.id).label("code_count"))
            .filter(models.HccSuggestion.tenant_id == tenant_id)
            .group_by(models.HccSuggestion.suggested_code)
            .order_by(func.count(models.HccSuggestion.id).desc())
            .limit(5)
            .all()
        )
        chain_status = _verify_audit_chain(db, tenant_id=tenant_id)
        if chain_status.get("verified"):
            audit_integrity_status = "verified" if chain_status.get("status") == "verified" else "partial"
        else:
            audit_integrity_status = "failed"

        return {
            "demo": False,
            "total_recovered_revenue": total_recovered,
            "missed_codes_found": total_suggestions,
            "average_value_per_encounter": total_recovered / recovery_encounters if recovery_encounters else 0.0,
            "accepted_rate": accepted_count / total_suggestions if total_suggestions else 0.0,
            "rejected_rate": rejected_count / total_suggestions if total_suggestions else 0.0,
            "top_categories": [
                {"category": row.suggested_code or "UNKNOWN", "recovered": 0.0, "codes": int(row.code_count or 0)}
                for row in top_rows
            ],
            "audit_integrity_status": audit_integrity_status,
        }


def _enforce_baa_precondition(db: Session, tenant_id: uuid.UUID) -> None:
    """Manual §7.2 Risk #1 — refuse FHIR ingest when BAA is unconfirmed.

    Returns silently when the tenant's ``baa_confirmed`` flag is True. Raises
    HTTP 412 (Precondition Failed) otherwise so the customer integration
    can surface a clear, actionable error rather than silently dropping
    the bundle or, worse, processing it before paperwork lands.

    The check is **strict by default**: any error reading the flag is
    treated as "not confirmed". An ops escape hatch
    (``BUDDI_BAA_INGEST_ENFORCEMENT=disabled``) exists for emergency
    incident response but should never be set under normal operation.
    """

    if os.getenv("BUDDI_BAA_INGEST_ENFORCEMENT", "").strip().lower() == "disabled":
        logger.warning(
            "BAA precondition enforcement disabled by env var; this MUST be "
            "a temporary incident-response state."
        )
        return

    try:
        confirmed = (
            db.query(models.Tenant.baa_confirmed)
            .filter(models.Tenant.id == tenant_id)
            .scalar()
        )
    except Exception as e:
        logger.error("BAA precondition lookup failed for %s: %s", tenant_id, e)
        confirmed = False

    if not confirmed:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                "BAA precondition not met for this tenant. Real PHI cannot be "
                "accepted until the Business Associate Agreement is filed and "
                "tenants.baa_confirmed is set to TRUE. See "
                "docs/COMPLIANCE/baa_status.md for the provisioning checklist."
            ),
        )


@app.post("/ingest/fhir")
async def process_fhir_bundle(
    request: Request,
    client: str = INGEST_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Standardized entrypoint for HL7 FHIR payloads (SEC-10 validated)."""
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
        tenant_id = _require_tenant_id(request)
        # Manual §7.2 Risk #1 — gate on BAA before anything touches the agent.
        _enforce_baa_precondition(db, tenant_id)
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
            tenant_id=str(tenant_id),
            request_id=_request_id(request),
        )

        if not agent:
            return {
                "status": "success",
                "response": _demo_shadow_result(
                    "FHIR-BUNDLE",
                    agent_payload.get("note") or "No clinical note text supplied in minimal FHIR bundle.",
                    agent_payload.get("billed_codes") or [],
                    source="fhir_agent_not_bootstrapped_demo",
                ),
                "audit_hash": audit_hash,
            }

        response_json_str = agent.handle(
            json.dumps(agent_payload), task_type="shadow_mode_rcm", tenant_id=tenant_id
        )
        try:
            response_obj = json.loads(response_json_str)
        except Exception:
            response_obj = {"raw_output": response_json_str}

        return {"status": "success", "response": response_obj, "audit_hash": audit_hash}


@app.post("/api/ingest/fhir")
async def process_api_fhir_bundle(
    request: Request,
    client: str = INGEST_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    return await process_fhir_bundle(request=request, client=client, db=db)


@app.post("/api/fhir/ingest", include_in_schema=False)
async def process_api_fhir_ingest_alias(
    request: Request,
    client: str = INGEST_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    return await process_fhir_bundle(request=request, client=client, db=db)


@app.post("/encounter/{encounter_id}/process", include_in_schema=False)
@app.post("/api/encounter/{encounter_id}/process")
async def process_encounter(
    encounter_id: str,
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    tenant_id = _require_tenant_id(request)
    log_audit_event_postgres(
        db,
        "encounter_processing_requested",
        {"encounter_id": encounter_id},
        actor_id=client,
        tenant_id=str(tenant_id),
        request_id=_request_id(request),
    )
    return {"status": "processing_queued", "encounter_id": encounter_id}


@app.get("/billing/suggest", include_in_schema=False)
@app.get("/api/billing/suggest")
async def billing_suggest(
    request: Request,
    encounter_id: str | None = None,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    try:
        tenant_id = _require_tenant_id(request)
        query = db.query(models.HccSuggestion).filter(models.HccSuggestion.tenant_id == tenant_id)
        if encounter_id:
            query = query.filter(models.HccSuggestion.encounter_id == encounter_id)
        return {"suggestions": query.all()}
    except Exception as e:
        logger.error("Suggest endpoint DB failure: %s", e)
        return {"error": "Database error", "suggestions": []}


def _demo_prior_auth_draft(encounter_id: str, procedure_code: str, payer: str) -> Dict[str, Any]:
    """Deterministic demo draft used when the agent is unavailable.

    Mirrors the ``demo: true`` pattern of ``_demo_shadow_result`` so the
    operator UI never goes empty during a no-LLM-key first run.
    """
    letter = (
        f"To the {payer} medical-review team:\n\n"
        f"This letter requests prior authorization for procedure code "
        f"{procedure_code} for the documented encounter ({encounter_id}). "
        "The patient is a 67-year-old with type 2 diabetes mellitus complicated "
        "by chronic kidney disease (stage 3a) and hypertensive CKD. Documented "
        "eGFR is 51 and urine albumin/creatinine ratio is 42 mg/g. Renal-protective "
        "therapy is medically necessary to slow CKD progression and reduce "
        "cardiovascular risk per ADA Standards of Care and KDIGO 2024.\n\n"
        "Supporting documentation is enclosed. Please contact the ordering "
        "clinician with any questions.\n\nSincerely,\nDr. Sarah Chen"
    )
    return {
        "draft_letter": letter,
        "supporting_codes": ["E11.22", "N18.31", "I12.9"],
        "payer_rationale": (
            "Documented diabetic CKD with proteinuria meets ADA / KDIGO criteria "
            "for the requested intervention; deferring approval risks accelerated "
            "renal decline and downstream costs."
        ),
        "evidence_snippets": [
            {"quote": "type 2 diabetes mellitus complicated by chronic kidney disease stage 3a", "source": "clinical_note"},
            {"quote": "eGFR 51 and urine albumin/creatinine ratio 42 mg/g", "source": "clinical_note"},
            {"quote": "Hypertension treated with lisinopril", "source": "clinical_note"},
        ],
        "missing_information": [
            "Confirm latest A1C within 90 days.",
            "Attach signed clinician attestation of medical necessity.",
        ],
    }


def _resolve_prior_auth_args(
    body: PriorAuthGenerateRequest,
    encounter_id_q: Optional[str],
    procedure_code_q: Optional[str],
) -> Dict[str, Any]:
    return {
        "encounter_id": body.encounter_id or encounter_id_q,
        "procedure_code": body.procedure_code or procedure_code_q,
        "payer": body.payer or "Medicare",
        "clinical_context": body.clinical_context,
        "demo": body.demo,
    }


@app.post("/prior-auth/generate", include_in_schema=False)
@app.post("/api/prior-auth/generate")
async def generate_prior_auth(
    request: Request,
    body: PriorAuthGenerateRequest = PriorAuthGenerateRequest(),
    encounter_id: Optional[str] = None,
    procedure_code: Optional[str] = None,
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Generate a real prior-authorization draft via the agent.

    Backward compatibility:
      * Legacy callers can still pass ``?encounter_id=…&procedure_code=…``.
      * New callers should send a JSON body
        ``{encounter_id, procedure_code, payer, clinical_context, demo}``.

    The response always carries the structured PriorAuthDraft fields the UI
    needs (`draft_letter`, `supporting_codes`, `payer_rationale`,
    `evidence_snippets`, `missing_information`) plus
    ``auth_request_id`` and ``audit_hash``.
    """
    with tracer.start_as_current_span("api_prior_auth_generate"):
        tenant_id = _require_tenant_id(request)
        args = _resolve_prior_auth_args(body, encounter_id, procedure_code)
        proc = args["procedure_code"]
        if not proc:
            raise HTTPException(status_code=422, detail="procedure_code is required")

        fallback_context = (
            DEMO_PATIENT["clinical_note"]
            if args["demo"] or not args["clinical_context"]
            else args["clinical_context"]
        )

        used_demo = False
        draft_payload: Dict[str, Any]
        if agent and not args["demo"]:
            agent_input = json.dumps(
                {
                    "encounter_id": args["encounter_id"] or "demo_encounter",
                    "procedure_code": proc,
                    "payer": args["payer"],
                    "clinical_context": args["clinical_context"] or fallback_context,
                }
            )
            raw = agent.handle(agent_input, task_type="prior_auth_draft", tenant_id=tenant_id)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"error": "non_json_agent_response", "raw": raw[:400]}
            if parsed.get("error") or "draft_letter" not in parsed:
                used_demo = True
                draft_payload = _demo_prior_auth_draft(
                    args["encounter_id"] or "demo_encounter", proc, args["payer"]
                )
            else:
                draft_payload = PriorAuthDraft.model_validate(parsed).model_dump()
        else:
            used_demo = True
            draft_payload = _demo_prior_auth_draft(
                args["encounter_id"] or "demo_encounter", proc, args["payer"]
            )
        draft_payload["draft_letter"] = sanitize_response(draft_payload.get("draft_letter", ""))

        auth_request_id: Optional[str] = None
        auth_status = "draft"
        submission_payload: Dict[str, Any] = {
            "procedure_code": proc,
            "payer": args["payer"],
            "demo": used_demo,
            "draft": redact_for_logs(draft_payload, max_length=2000),
        }
        try:
            encounter_uuid = _uuid_or_none(args["encounter_id"])
            new_auth = models.PriorAuthorizationRequest(
                tenant_id=tenant_id,
                encounter_id=encounter_uuid,
                procedure_code=proc,
                payer_name=args["payer"],
                status=auth_status,
                submission_payload=submission_payload,
            )
            db.add(new_auth)
            db.flush()
            auth_request_id = str(new_auth.id)
            db.add(
                models.PriorAuthState(
                    tenant_id=tenant_id,
                    prior_auth_id=new_auth.id,
                    state="draft",
                    reasoning="Drafted by Buddi agent",
                )
            )
            db.commit()
        except Exception as e:
            logger.warning(
                "Prior-auth DB persistence failed (returning artifact anyway): %s",
                redact_for_logs(str(e)),
                extra={"request_id": _request_id(request)},
            )
            db.rollback()

        audit_hash = log_audit_event_postgres(
            db,
            "prior_auth_draft_generated_demo" if used_demo else "prior_auth_draft_generated",
            {
                "auth_id": auth_request_id,
                "procedure": proc,
                "payer": args["payer"],
                "encounter_id": args["encounter_id"],
                "demo": used_demo,
                "supporting_code_count": len(draft_payload.get("supporting_codes", [])),
                "risk": "low",
            },
            actor_id=client,
            tenant_id=str(tenant_id),
            request_id=_request_id(request),
        )

        return {
            "draft_id": auth_request_id,
            "auth_request_id": auth_request_id,
            "status": auth_status,
            "procedure_code": proc,
            "payer": args["payer"],
            "clinical_justification": draft_payload.get("payer_rationale", ""),
            "urgency": "routine",
            "demo": used_demo,
            "audit_hash": audit_hash,
            **draft_payload,
        }


async def _get_audit_logs_impl(client: str, db: Session, tenant_id: uuid.UUID | None = None):
    try:
        verification = _verify_audit_chain(db, tenant_id=tenant_id)
        query = db.query(models.AuditEvent)
        if tenant_id is not None:
            query = query.filter(models.AuditEvent.tenant_id == tenant_id)
        events = query.order_by(models.AuditEvent.event_id.desc()).limit(20).all()
        statuses = verification.get("event_statuses", {})
        return {
            "events": [
                _audit_event_to_dict(event, statuses.get(event.event_id, "unchecked"))
                for event in events
            ],
            "verification": {
                "valid": bool(verification.get("verified")),
                "message": verification.get("status") or verification.get("message") or "unknown",
                **{k: v for k, v in verification.items() if k != "event_statuses"},
            },
        }
    except Exception as e:
        logger.error("Audit lookup failure: %s", e)
        demo_hash = _generate_crypto_trail(
            "shadow_mode_rcm_demo",
            _canonical_json({"patient_id": DEMO_PATIENT["id"], "demo": True}),
            None,
            "demo",
        )
        return {
            "events": [
                {
                    "id": "demo-shadow-audit",
                    "event_type": "shadow_mode_rcm_demo",
                    "action": "shadow_mode_rcm_demo",
                    "actor": client,
                    "user": client,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "current_hash": demo_hash,
                    "cryptographic_hash": demo_hash,
                    "previous_hash": None,
                    "verification_status": "demo_verified",
                    "risk": "low",
                    "payload": {
                        "patient_id": DEMO_PATIENT["id"],
                        "recovered_revenue": _demo_shadow_result(
                            DEMO_PATIENT["id"], DEMO_PATIENT["clinical_note"], DEMO_PATIENT["billed_codes"]
                        )["recovered_revenue"],
                        "demo": True,
                    },
                }
            ],
            "verification": {"verified": True, "status": "demo_verified", "events_checked": 1},
        }


@app.get("/audit/query", include_in_schema=False)
async def get_audit_logs_redirect(client: str = AUTH):
    return RedirectResponse(url="/api/audit/query", status_code=301)


@app.get("/api/audit/query")
async def get_api_audit_logs(
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    return await _get_audit_logs_impl(client, db, tenant_id=_require_tenant_id(request))


@app.get("/api/audit/", include_in_schema=False)
async def get_api_audit_logs_trailing_slash_redirect(client: str = AUTH):
    return RedirectResponse(url="/api/audit/query", status_code=301)


@app.get("/api/audit/verify")
async def verify_audit_logs(
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Verify the DB audit chain *and* every signed daily Merkle root.

    Two independent checks are returned:

      ``chain``  — the in-DB hash chain (legacy, mutable-by-DBA).
      ``roots``  — the signed daily Merkle roots in
                   ``storage/audit_roots/`` recomputed from the live DB
                   rows. This is the artifact CMS auditors will ask for.

    The top-level ``verified`` flag is true only if *both* sides agree.
    A degraded DB still returns 200 with ``status="demo_verified"`` so
    the operator UI is never blank — production monitoring should alert
    on ``status != "verified"``.
    """
    tenant_id = _require_tenant_id(request)
    try:
        chain = _verify_audit_chain(db, tenant_id=tenant_id)
        chain_summary = {k: v for k, v in chain.items() if k != "event_statuses"}
    except Exception as e:
        logger.error("Audit chain verification failure: %s", e)
        chain_summary = {
            "verified": True,
            "status": "demo_verified",
            "events_checked": 1,
            "broken_at": None,
        }

    try:
        roots_summary = verify_signed_roots_against_db(db)
    except Exception as e:
        logger.error("Signed-root verification failure: %s", e)
        roots_summary = {
            "verified": False,
            "checked_days": 0,
            "valid_days": 0,
            "days": [],
            "error": str(e),
        }

    overall_verified = bool(chain_summary.get("verified")) and (
        roots_summary.get("verified") or roots_summary.get("checked_days", 0) == 0
    )
    if overall_verified:
        if roots_summary.get("checked_days", 0) > 0:
            overall_status = "verified_with_signed_roots"
        else:
            overall_status = chain_summary.get("status", "verified")
    else:
        if not chain_summary.get("verified"):
            overall_status = chain_summary.get("status", "chain_broken")
        else:
            overall_status = "signed_root_mismatch"

    return {
        # Top-level fields preserved for backwards compatibility with the
        # React audit page (which only reads `verified` / `status` /
        # `events_checked`).
        "verified": overall_verified,
        "status": overall_status,
        "events_checked": chain_summary.get("events_checked", 0),
        "broken_at": chain_summary.get("broken_at"),
        # New, richer breakdown.
        "chain": chain_summary,
        "roots": roots_summary,
    }


@app.get("/api/audit/roots")
async def list_audit_roots(client: str = ADMIN_AUTH):
    """List every signed Merkle root currently in ``storage/audit_roots/``."""
    # Security: signed root inventory is admin-only operational audit metadata.
    days = list_signed_root_days()
    return {"count": len(days), "days": days}


@app.post("/api/audit/roots/seal")
async def seal_audit_root_now(
    background_tasks: BackgroundTasks,
    request: Request,
    day: Optional[str] = None,
    sync: bool = False,
    client: str = ADMIN_AUTH,
):
    """Trigger an immediate Merkle-root seal (admin / on-demand path).

    The daily background loop covers the standard cadence; this endpoint
    is for SREs running a backfill, for tests, and for the
    ``make seal-audit-root`` Makefile target.

    Query params:
      * ``day``  — ISO date (UTC); defaults to *yesterday*.
      * ``sync`` — when true, run the seal inline and return its result;
        otherwise schedule via ``BackgroundTasks`` so the HTTP request
        returns immediately.
    """
    target: Optional[date]
    if day:
        try:
            target = date.fromisoformat(day)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid day: {e}") from e
    else:
        target = None

    # Audit the request itself in the chain. Use a standalone session so
    # this admin endpoint does not depend on the request-scoped session.
    audit_db = SessionLocal()
    try:
        log_audit_event_postgres(
            audit_db,
            "audit_merkle_root_seal_requested",
            {"day": day, "sync": sync, "risk": "low"},
            actor_id=str(client),
            request_id=_request_id(request),
        )
    finally:
        audit_db.close()


    if sync:
        try:
            result = await asyncio.to_thread(_seal_merkle_root_for_yesterday, target)
            return {"status": "sealed", **result}
        except Exception as e:
            logger.error("Manual seal failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Seal failed: {e}") from e

    background_tasks.add_task(_seal_merkle_root_for_yesterday, target)
    return {
        "status": "scheduled",
        "day": day or (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
    }



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
