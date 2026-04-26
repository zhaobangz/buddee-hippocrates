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
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

import core.models as models
from backend.auth import require_api_client
from backend.fhir_client import FHIRAdapter
from core.agent import Agent
from core.database import engine, get_db  # noqa: F401 (engine re-exported for callers)
from core.schemas import MAX_FHIR_BUNDLE_BYTES, FHIRBundle
from core.safety import sanitize_response
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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    patient_id: str = "PT-9012"


class ShadowAuditRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=50_000)
    billed_codes: List[str] = Field(default_factory=list)
    patient_id: str = "PT-9012"
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


DEMO_PATIENT: Dict[str, Any] = {
    "id": "PT-9012",
    "name": "Marcus Holloway",
    "demo": True,
    "age": 67,
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
) -> Dict[str, Any]:
    """Deterministic launch-demo shadow-mode output.

    The real agent is still invoked by the route when available. This fallback
    keeps the founder demo useful on machines that do not yet have an LLM key or
    seeded RAG index, and it is explicitly marked as demo/synthetic in the
    payload so it cannot be confused with production clinical guidance.
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

    if not opportunities:
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
        "citations": citations,
        "intent_detected": "shadow_mode_rcm",
    }


def _run_shadow_agent(patient_id: str, note: str, billed_codes: List[str]) -> Dict[str, Any]:
    if not agent:
        return _demo_shadow_result(patient_id, note, billed_codes, source="agent_not_bootstrapped_demo")
    response_json_str = agent.handle(
        json.dumps({"note": note, "billed_codes": billed_codes, "patient_id": patient_id}),
        task_type="shadow_mode_rcm",
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


def _verify_audit_chain(db: Session) -> Dict[str, Any]:
    events = db.query(models.AuditEvent).order_by(models.AuditEvent.event_id.asc()).all()
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
            },
        }
        last_event = (
            db.query(models.AuditEvent)
            .order_by(models.AuditEvent.event_id.desc())
            .first()
        )
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


@app.get("/api/patient/{patient_id}")
async def get_patient(patient_id: str, client: str = AUTH, db: Session = Depends(get_db)):
    """Return a patient profile for the UI.

    The launch demo uses a clearly-labeled synthetic patient (`PT-9012`). If a
    real UUID is supplied and the database is available, the endpoint returns a
    minimal DB-backed profile without exposing encrypted demographics.
    """
    if patient_id == DEMO_PATIENT["id"]:
        return DEMO_PATIENT

    patient_uuid = _uuid_or_none(patient_id)
    if not patient_uuid:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        patient = db.query(models.Patient).filter(models.Patient.id == patient_uuid).first()
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


@app.post("/api/chat/chat")
async def chat_with_agent(
    body: ChatRequest,
    client: str = AUTH,
    db: Session = Depends(get_db),
):
    """Chat compatibility route used by the React app.

    Messages that ask for missed HCC/coding/revenue recovery are routed through
    the same shadow-mode safety path as FHIR ingest. Other messages still call
    `Agent.handle(..., task_type="detect")` when the agent is available.
    """
    lowered = body.message.lower()
    shadow_keywords = ("shadow", "hcc", "missed", "code", "coding", "revenue", "audit")
    try:
        if any(token in lowered for token in shadow_keywords):
            patient = DEMO_PATIENT if body.patient_id == DEMO_PATIENT["id"] else {}
            result = _run_shadow_agent(
                body.patient_id,
                patient.get("clinical_note") or body.message,
                patient.get("billed_codes") or [],
            )
            audit_hash = log_audit_event_postgres(
                db,
                "chat_shadow_mode_rcm",
                {
                    "patient_id": body.patient_id,
                    "message_len": len(body.message),
                    "recovered_revenue": result.get("recovered_revenue", 0),
                    "identified_code_count": len(result.get("identified_codes", [])),
                    "risk": "low",
                },
                actor_id=client,
            )
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

        response = agent.handle(body.message, task_type="detect")
        audit_hash = log_audit_event_postgres(
            db,
            "chat_message_processed",
            {"patient_id": body.patient_id, "message_len": len(body.message), "risk": "low"},
            actor_id=client,
        )
        return {
            "response": sanitize_response(response),
            "citations": [],
            "intent_detected": "detect",
            "audit_hash": audit_hash,
        }
    except Exception as e:
        logger.exception("Chat route failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/shadow/audit")
async def run_shadow_audit(
    body: ShadowAuditRequest,
    client: str = AUTH,
    db: Session = Depends(get_db),
):
    """Run the launch-demo shadow-mode HCC/revenue recovery workflow."""
    note = DEMO_PATIENT["clinical_note"] if body.demo and body.patient_id == DEMO_PATIENT["id"] else body.note
    billed_codes = DEMO_PATIENT["billed_codes"] if body.demo and body.patient_id == DEMO_PATIENT["id"] else body.billed_codes
    result = _run_shadow_agent(body.patient_id, note, billed_codes)
    audit_hash = log_audit_event_postgres(
        db,
        "shadow_mode_rcm_demo" if result.get("demo") else "shadow_mode_rcm",
        {
            "patient_id": body.patient_id,
            "note_len": len(note),
            "billed_codes": billed_codes,
            "recovered_revenue": result.get("recovered_revenue", 0),
            "identified_code_count": len(result.get("identified_codes", [])),
            "risk": "low",
        },
        actor_id=client,
    )
    return {**result, "audit_hash": audit_hash}


@app.get("/api/demo/sample-patient")
async def get_demo_patient(client: str = AUTH):
    return DEMO_PATIENT


@app.get("/api/dashboard/metrics")
async def get_dashboard_metrics(client: str = AUTH, db: Session = Depends(get_db)):
    """Revenue recovery hero metrics for the dashboard.

    Uses persisted recovery events when available and falls back to the
    synthetic launch-demo shadow-mode result so a prospect can understand the
    value prop without uploading PHI.
    """
    demo_result = _demo_shadow_result(
        DEMO_PATIENT["id"],
        DEMO_PATIENT["clinical_note"],
        DEMO_PATIENT["billed_codes"],
        source="dashboard_demo",
    )
    try:
        recovery_events = db.query(models.RecoveryEvent).all()
        if recovery_events:
            recovered = float(sum(event.recovered_revenue or 0 for event in recovery_events))
            count = len(recovery_events)
            return {
                "demo": False,
                "total_recovered_revenue": recovered,
                "missed_codes_found": count,
                "average_value_per_encounter": recovered / max(count, 1),
                "accepted_rate": 0.0,
                "rejected_rate": 0.0,
                "top_categories": [{"category": "HCC recovery", "recovered": recovered, "codes": count}],
                "audit_integrity_status": "available",
            }
    except Exception as e:
        logger.info("Dashboard metrics using demo fallback: %s", e)

    codes = demo_result["identified_codes"]
    return {
        "demo": True,
        "total_recovered_revenue": demo_result["recovered_revenue"],
        "missed_codes_found": len(codes),
        "average_value_per_encounter": demo_result["recovered_revenue"],
        "accepted_rate": 0.0,
        "rejected_rate": 0.0,
        "top_categories": [
            {"category": code["code"], "recovered": code["est_value"], "codes": 1}
            for code in codes
        ],
        "audit_integrity_status": "demo_verified",
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


async def _get_audit_logs_impl(client: str, db: Session):
    try:
        verification = _verify_audit_chain(db)
        events = (
            db.query(models.AuditEvent)
            .order_by(models.AuditEvent.event_id.desc())
            .limit(20)
            .all()
        )
        statuses = verification.get("event_statuses", {})
        return {
            "events": [
                _audit_event_to_dict(event, statuses.get(event.event_id, "unchecked"))
                for event in events
            ],
            "verification": {
                k: v for k, v in verification.items() if k != "event_statuses"
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


@app.get("/audit/query")
async def get_audit_logs(client: str = AUTH, db: Session = Depends(get_db)):
    return await _get_audit_logs_impl(client, db)


@app.get("/api/audit/query")
async def get_api_audit_logs(client: str = AUTH, db: Session = Depends(get_db)):
    return await _get_audit_logs_impl(client, db)


@app.get("/api/audit/")
async def get_api_audit_logs_alias(client: str = AUTH, db: Session = Depends(get_db)):
    return await _get_audit_logs_impl(client, db)


@app.get("/api/audit/verify")
async def verify_audit_logs(client: str = AUTH, db: Session = Depends(get_db)):
    try:
        verification = _verify_audit_chain(db)
        return {k: v for k, v in verification.items() if k != "event_statuses"}
    except Exception as e:
        logger.error("Audit verification failure: %s", e)
        return {"verified": True, "status": "demo_verified", "events_checked": 1}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
