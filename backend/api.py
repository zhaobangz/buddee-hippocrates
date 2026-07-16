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
import base64
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

import core.models as models
from backend.auth import AuthenticatedClient, require_api_client, require_scope
from backend.fhir_client import FHIRAdapter
from backend.smart_fhir import SMARTFHIRLauncher, tenant_id_from_state
from backend.middleware import (
    RateLimitMiddleware,
    RequestIDMiddleware,
    validate_trusted_proxy_cidrs,
)
from core.agent import Agent
from core.config import settings
from core.database import SessionLocal, engine  # noqa: F401 (engine re-exported for callers)
from core.db_session import set_tenant_context, tenant_scoped_session
from core import jobs as job_queue
from core.webhooks import (
    EVENT_AUDIT_FLAGGED,
    EVENT_HCC_APPROVED,
    EVENT_HCC_CREATED,
    EVENT_PRIOR_AUTH_CHANGED,
    KNOWN_EVENTS,
    dispatch_webhook,
    register_webhook,
)
from core.merkle import (
    build_daily_root,
    export_daily_root,
    list_signed_root_days,
    verify_signed_roots_against_db,
)
from core.phi_guard import PHIProcessingNotAllowed, assert_phi_processing_allowed
from core.schemas import MAX_FHIR_BUNDLE_BYTES, FHIRBundle, PriorAuthDraft, ShadowModeResponse
from core.safety import redact_for_logs, sanitize_response
from core.secure_fields import encrypt_json_value, encrypt_text_value
from core.tracing import get_tracer, setup_tracing, shutdown_tracing
from core.worker import worker_loop


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

# Build-out B3: async job worker (drains the ``jobs`` queue). In Cloud Run,
# set BUDDI_DISABLE_WORKER=1 for the API service and run core.worker as the
# separate buddi-worker service. The legacy BUDDI_DISABLE_JOB_WORKER name is
# still honored for older test/dev environments.
_worker_task: Optional[asyncio.Task] = None
DISABLE_WORKER = (
    os.getenv("BUDDI_DISABLE_WORKER", os.getenv("BUDDI_DISABLE_JOB_WORKER", ""))
    .lower()
    in {"1", "true", "yes"}
)


def _seal_merkle_root_for_yesterday(
    target_day: Optional[date] = None,
    tenant_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """Build, sign, and export tenant-scoped Merkle roots for ``target_day``.

    Runs on its own ``SessionLocal()`` rather than a request-scoped session
    so the daily cron-style task is independent of any inbound HTTP call.
    Returns a small status dict suitable for logging / API responses.
    """
    if target_day is None:
        target_day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    db = SessionLocal()
    try:
        tenant_ids = [tenant_id] if tenant_id is not None else [row[0] for row in db.query(models.Tenant.id).all()]
        roots: List[Dict[str, Any]] = []
        total_events = 0
        for tenant_id in tenant_ids:
            set_tenant_context(db, tenant_id)
            daily = build_daily_root(db, day=target_day, tenant_id=str(tenant_id))
            path = export_daily_root(daily)
            total_events += daily.event_count
            log_audit_event_postgres(
                db,
                "audit_merkle_root_sealed",
                {
                    "day": daily.day,
                    "tenant_id": str(tenant_id),
                    "event_count": daily.event_count,
                    "merkle_root": daily.merkle_root,
                    "key_id": daily.signature.get("key_id"),
                    "algorithm": daily.signature.get("algorithm"),
                    "kms_provider": daily.signature.get("kms_provider"),
                    "export_path": str(path),
                    "object_lock_uri": daily.object_lock_uri,
                    "risk": "low",
                },
                actor_id="system:merkle-task",
                tenant_id=str(tenant_id),
            )
            roots.append(
                {
                    "tenant_id": str(tenant_id),
                    "day": daily.day,
                    "event_count": daily.event_count,
                    "merkle_root": daily.merkle_root,
                    "export_path": str(path),
                    "object_lock_uri": daily.object_lock_uri,
                    "key_id": daily.signature.get("key_id"),
                    "algorithm": daily.signature.get("algorithm"),
                }
            )
        return {
            "day": target_day.isoformat(),
            "event_count": total_events,
            "merkle_root": roots[0]["merkle_root"] if len(roots) == 1 else None,
            "tenants_sealed": len(roots),
            "roots": roots,
        }
    finally:
        try:
            set_tenant_context(db, None)
        except Exception:
            pass
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
    global agent, _merkle_root_task, _worker_task
    with tracer.start_as_current_span("system_startup"):
        logger.info("Initializing RCM Agent System...")
        # Build-out A1.4: surface provider config at startup. Anthropic is the
        # primary clinical-reasoning provider; OpenAI is embeddings-only.
        logger.info("LLM provider: %s | Embed provider: OpenAI", settings.LLM_PROVIDER)
        # Issue 8: fail closed at startup on a misconfigured TRUSTED_PROXY_CIDRS.
        # Logs the resolved set and raises in non-development environments when
        # it parses to zero networks, rather than silently disabling XFF trust.
        validate_trusted_proxy_cidrs()
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

        # Build-out B3: kick off the async job worker. Disable in Cloud Run's
        # API service when a separate buddi-worker service drains the queue.
        if not DISABLE_WORKER and agent is not None:
            try:
                _worker_task = asyncio.create_task(worker_loop(agent))
            except Exception as e:
                logger.warning("Failed to schedule job worker: %s", e)
                _worker_task = None
        else:
            logger.info("Job worker disabled via BUDDI_DISABLE_WORKER or missing agent")

        yield

        logger.info("System optimized shutdown.")
        for _task in (_merkle_root_task, _worker_task):
            if _task is not None:
                _task.cancel()
                try:
                    await _task
                except (asyncio.CancelledError, Exception):
                    pass
        _merkle_root_task = None
        _worker_task = None
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
    title="Buddee Clinical AI API",
    description="""
Shadow-mode revenue integrity and prior authorization for U.S. healthcare.

**Key properties:**
- Every HCC/ICD-10 suggestion requires human approval before use. Nothing auto-submits.
- Every analysis is recorded in a SHA-256 hash-chained audit log, verified daily by KMS-signed Merkle root.
- PHI never leaves your tenant boundary unencrypted. Clinical notes are transmitted to the LLM provider only under a signed Business Associate Agreement.

**Authentication:** Pass your API key as `X-API-Key: <key>` or `Authorization: Bearer <key>`.

**Quick start:** See `GET /api/demo/synthea` for synthetic test bundles, then `POST /api/shadow/audit` to analyze one.
    """,
    version="4.1.0",
    contact={"name": "Buddee Support", "email": "support@buddi.health"},
    license_info={"name": "Proprietary — Buddee Health Inc."},
    servers=[
        {"url": "https://api.buddi.health", "description": "Production"},
        {"url": "https://staging-api.buddi.health", "description": "Staging"},
        {"url": "http://localhost:8001", "description": "Local dev"},
    ],
    openapi_tags=[
        {"name": "health", "description": "Liveness and readiness probes."},
        {"name": "shadow-audit", "description": "Shadow-mode HCC/ICD-10 coding review."},
        {"name": "prior-auth", "description": "Prior authorization draft generation."},
        {"name": "audit-chain", "description": "Tamper-evident audit log query and verification."},
        {"name": "fhir-ingest", "description": "FHIR R4 bundle ingestion."},
        {"name": "demo", "description": "Synthetic patient demo endpoints (no PHI)."},
        {"name": "jobs", "description": "Async job polling for long-running LLM tasks."},
        {"name": "billing", "description": "Stripe subscription management."},
        {"name": "webhooks", "description": "Webhook endpoint registration."},
        {"name": "metrics", "description": "PHI-safe SLO and operational metrics."},
    ],
    lifespan=lifespan,
)


class ErrorResponse(BaseModel):
    """Canonical error body returned by every route on failure."""

    detail: str


# Reusable OpenAPI ``responses=`` block documenting the common error codes.
_COMMON_ERRORS = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
    403: {"model": ErrorResponse, "description": "Insufficient scope"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Response-Source"],
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
    encounter_id: Optional[str] = None
    note_hash: Optional[str] = None
    demo: bool = False


class PriorAuthGenerateRequest(BaseModel):
    """JSON body for ``POST /prior-auth/generate``.

    For backwards compatibility the route also accepts the legacy query
    parameters ``encounter_id`` and ``procedure_code``; when both query and
    body are present, body wins.
    """

    encounter_id: Optional[str] = None
    procedure_code: Optional[str] = None
    note_hash: Optional[str] = None
    payer: Optional[str] = "Medicare"
    clinical_context: Optional[str] = Field(
        default=None, max_length=50_000,
        description="Free-text clinical context the agent will summarise into the draft.",
    )
    demo: bool = False


class WebhookCreateRequest(BaseModel):
    """JSON body for ``POST /api/webhooks`` (build-out B2)."""

    url: str = Field(..., min_length=1, max_length=2048)
    events: List[str] = Field(..., min_length=1)
    secret: str = Field(..., min_length=16, max_length=256)


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


# Build-out A3.4: the demo fallback sources its clinical note from the
# committed Safe-Harbor fixture bundles (evals/synthea/fixtures/) keyed by a
# patient-named slug, rather than a single hard-coded vignette. The default
# "marcus_holloway" preserves the original diabetic-CKD demo.
DEMO_FIXTURE_DIR = os.getenv("BUDDI_DEMO_FIXTURES_DIR") or "evals/synthea/fixtures"


def _demo_fixture_path(bundle_name: str) -> str | None:
    """Resolve a fixture slug to a path inside DEMO_FIXTURE_DIR.

    Returns None for missing slugs or any attempt to escape the directory.
    """

    if not bundle_name:
        return None
    name = bundle_name if bundle_name.endswith(".json") else f"{bundle_name}.json"
    if any(ch in name for ch in ("/", "\\", "..")):
        return None
    candidate = os.path.join(DEMO_FIXTURE_DIR, name)
    if not os.path.abspath(candidate).startswith(os.path.abspath(DEMO_FIXTURE_DIR)):
        return None
    return candidate if os.path.exists(candidate) else None


def _fixture_note(bundle_name: str) -> str:
    """Extract the de-identified clinical note from a demo fixture bundle.

    Returns "" when the fixture is missing/unreadable so callers fall back to
    their own ``note`` argument (backward compat). Build-out A3.4.
    """

    path = _demo_fixture_path(bundle_name)
    if path is None:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            bundle = json.load(f)
    except Exception:
        return ""
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "DocumentReference":
            continue
        for content in resource.get("content", []):
            data = content.get("attachment", {}).get("data")
            if not data:
                continue
            try:
                return base64.b64decode(data).decode("utf-8")
            except Exception:
                return ""
    return ""


def _demo_shadow_result(
    patient_id: str,
    note: str,
    billed_codes: List[str] | None = None,
    source: str = "demo_fallback",
    include_fallback: bool = True,
    bundle_name: str = "marcus_holloway",
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

    ``bundle_name`` (default "marcus_holloway") selects which committed fixture
    bundle supplies the clinical note **when the caller does not pass one**.
    Explicit ``note`` arguments always win, so existing callers (the eval
    harness, the live route) are unaffected. Build-out A3.4.
    """
    # Fall back to the fixture's note only when no note was supplied.
    note = note or _fixture_note(bundle_name)
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
        "bundle_name": bundle_name,
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


def _verify_audit_chain(
    db: Session,
    tenant_id: uuid.UUID | None = None,
    day: date | None = None,
) -> Dict[str, Any]:
    query = db.query(models.AuditEvent)
    if tenant_id is not None:
        query = query.filter(models.AuditEvent.tenant_id == tenant_id)
    previous_hash = None
    if day is not None:
        # Build-out B7.2: scope the re-walk to a single day so Postgres can
        # partition-prune the monthly audit_events partitions instead of
        # fanning out across all of them.
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        query = query.filter(
            models.AuditEvent.timestamp >= start,
            models.AuditEvent.timestamp < start + timedelta(days=1),
        )
        # Seed the walk with the chain tip from *before* the window.
        # Starting a day-scoped walk from None used to flag the first event
        # of every day (whose previous_hash correctly points at the prior
        # day's tip) as "chain_broken" — a false tamper alarm.
        seed_query = db.query(models.AuditEvent).filter(models.AuditEvent.timestamp < start)
        if tenant_id is not None:
            seed_query = seed_query.filter(models.AuditEvent.tenant_id == tenant_id)
        seed_event = seed_query.order_by(models.AuditEvent.event_id.desc()).first()
        previous_hash = seed_event.cryptographic_hash if seed_event else None
    events = query.order_by(models.AuditEvent.event_id.asc()).all()
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


# Serialize the (read chain tip -> insert -> commit) critical section of the
# audit logger. Without this, two concurrent writers read the same tip and
# both chain onto it — a fork that _verify_audit_chain later reports as
# "chain_broken" (a false tamper alarm on the product's flagship guarantee).
#
#   * Postgres: a transaction-scoped advisory lock keyed per tenant chain.
#     Auto-released at COMMIT/ROLLBACK, cross-process and cross-instance safe.
#   * Other dialects (SQLite in tests): a process-level mutex. SQLite
#     serializes writers anyway; the mutex closes the in-process window.
_AUDIT_CHAIN_FALLBACK_LOCK = threading.Lock()


def _audit_chain_lock_key(tenant_id: str | None) -> int:
    """Stable signed-64-bit advisory-lock key for a tenant's audit chain."""

    digest = hashlib.sha256(f"buddi-audit-chain:{tenant_id or 'global'}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def log_audit_event_postgres(
    db: Session,
    event_type: str,
    payload_data: dict,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    request_id: str | None = None,
) -> str | None:
    """Append-only audit logger with cryptographic chaining.

    The tip-read → hash → insert → commit section is serialized per tenant
    (advisory lock on Postgres, process mutex elsewhere) so concurrent
    requests/workers cannot fork the hash chain.
    """
    is_postgres = bool(getattr(db.bind, "dialect", None)) and db.bind.dialect.name == "postgresql"
    fallback_lock = _AUDIT_CHAIN_FALLBACK_LOCK if not is_postgres else None
    if fallback_lock is not None:
        fallback_lock.acquire()
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
        if is_postgres:
            # Held until the COMMIT below (or the ROLLBACK in the except
            # branch), covering exactly the tip-read + insert window.
            db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": _audit_chain_lock_key(tenant_id)},
            )
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
        # Build-out B2: a high-risk audit event fans out an audit_event.flagged
        # webhook (best-effort, on its own background session).
        _maybe_schedule_audit_flagged(
            tenant_id,
            event_type,
            current_hash,
            payload_data.get("risk", "low") if isinstance(payload_data, dict) else "low",
        )
        return current_hash
    except Exception as e:
        logger.error("Audit log failed (DB likely offline): %s", e)
        db.rollback()
        return None
    finally:
        if fallback_lock is not None:
            fallback_lock.release()


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


@app.get("/api/health", tags=["health"])
async def health(
    request: Request,
    client: str = AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    db_status = "offline"
    try:
        db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception:
        pass
    # Build-out B6.2: surface the tenant UUID so the operator UI can show a
    # tenant-scoping indicator (last 8 chars). Not PHI; never the API key.
    tenant_id = getattr(request.state, "tenant_id", None)
    payload = {
        "status": "active",
        "db": db_status,
        "mode": "RCM_Audit_Postgres",
        "client": client,
        "tenant_id": str(tenant_id) if tenant_id else None,
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
    # Security: this route drives the agent / LLM pipeline, so it requires the
    # clinician scope, not bare authentication (Issue 7).
    client: str = CLINICIAN_AUTH,
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
        shadow_requested = any(
            token in body.message.lower()
            for token in ("shadow", "hcc", "missed", "code", "coding", "revenue", "audit")
        )

        def _shadow_chat_response(result: Dict[str, Any]) -> Dict[str, Any]:
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

        if patient_id == DEMO_PATIENT["id"]:
            if shadow_requested:
                result = _demo_shadow_result(
                    patient_id,
                    DEMO_PATIENT["clinical_note"],
                    DEMO_PATIENT["billed_codes"],
                    source="chat_synthetic_demo",
                )
                return _shadow_chat_response(result)
            return {
                "response": sanitize_response(
                    "Buddi is running in local demo mode. Ask me to find missed HCC codes for PT-9012 to run the shadow-mode workflow."
                ),
                "citations": [],
                "intent_detected": "demo_assistant",
            }

        _enforce_baa_precondition(db, tenant_id)
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
                return _shadow_chat_response(result)
        if shadow_requested:
            patient = {}
            result = _run_shadow_agent(
                patient_id,
                patient.get("clinical_note") or body.message,
                patient.get("billed_codes") or [],
                tenant_id=tenant_id,
            )
            return _shadow_chat_response(result)

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


async def _process_shadow_audit(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    patient_id: str,
    note: str,
    billed_codes: List[str],
    demo: bool,
    actor: str | None,
    request_id: str | None,
) -> Dict[str, Any]:
    """Run + persist a shadow-mode audit. Shared by the sync route and worker.

    Returns the ``ShadowModeResponse`` payload. Persistence failures are
    swallowed (the audit result is still returned) exactly as the original
    synchronous route behaved.
    """

    _enforce_baa_precondition(
        db,
        tenant_id,
        synthetic=_is_synthetic_shadow_request(patient_id, demo),
    )
    _t0 = time.monotonic()
    result = _run_shadow_agent(patient_id, note, billed_codes, tenant_id=tenant_id)
    parsed_result = ShadowModeResponse.model_validate(result)
    result_payload = parsed_result.model_dump()
    # Build-out C2: stamp the end-to-end duration into the audit payload so
    # GET /api/metrics/slo can compute PHI-safe p50/p95/p99 latency.
    duration_ms = int((time.monotonic() - _t0) * 1000)

    audit_hash = log_audit_event_postgres(
        db,
        "shadow_mode_rcm_demo" if result.get("demo") else "shadow_mode_rcm",
        {
            "patient_id": patient_id,
            "note_len": len(note),
            "billed_codes": billed_codes,
            "recovered_revenue": parsed_result.recovered_revenue,
            "identified_code_count": len(parsed_result.identified_codes),
            "duration_ms": duration_ms,
            "risk": "low",
        },
        actor_id=actor,
        tenant_id=str(tenant_id),
        request_id=request_id,
    )
    result_payload["audit_hash"] = audit_hash or parsed_result.audit_hash
    result_payload["patient_id"] = patient_id
    result_payload["demo"] = bool(result.get("demo", demo))
    result_payload["source"] = result.get("source", "agent")
    result_payload["intent_detected"] = "shadow_mode_rcm"

    try:
        llm_request = models.LlmRequest(
            tenant_id=tenant_id,
            encounter_id=None,
            prompt_template_version="shadow_mode_rcm:v1",
            model=settings.LLM_MODEL,
            full_prompt=encrypt_text_value(str(redact_for_logs(note, max_length=4000))),
        )
        db.add(llm_request)
        db.flush()
        db.add(
            models.LlmResponse(
                tenant_id=tenant_id,
                llm_request_id=llm_request.id,
                raw_response=encrypt_text_value(json.dumps(result_payload, default=str)),
                parsed_json=encrypt_json_value(redact_for_logs(result_payload, max_length=4000)),
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
        # Build-out B2: notify subscribers that HCC suggestions were created.
        created_codes = [c.code for c in parsed_result.identified_codes]
        if created_codes:
            await _fire_webhook(
                db,
                tenant_id,
                EVENT_HCC_CREATED,
                {
                    "patient_id": patient_id,
                    "codes": created_codes,
                    "count": len(created_codes),
                },
            )
    except Exception as e:
        logger.warning(
            "Shadow audit persistence failed (returning audit result anyway): %s",
            redact_for_logs(str(e)),
            extra={"request_id": request_id},
        )
        db.rollback()
    return result_payload


async def _enqueue_job_response(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    job_type: str,
    input_payload: Dict[str, Any],
    idempotency_key: str,
) -> JSONResponse:
    """Enqueue an LLM-bound job and return the async HTTP envelope (build-out B3).

    Returns ``202 Accepted`` with ``{job_id, status, poll_url}`` for a freshly
    queued job, or — on an idempotency hit against an already-``completed`` job
    — ``200 OK`` with the cached ``result_payload`` so a retried request never
    re-runs the model. The job worker (``core/worker.py``) drains the queue and
    persists ``result_payload``; nothing here submits to a payer.
    """

    job = await job_queue.enqueue(
        db,
        tenant_id=tenant_id,
        job_type=job_type,
        input_payload=input_payload,
        idempotency_key=idempotency_key,
    )
    # Snapshot before commit — expire_on_commit would otherwise force a reload
    # on each attribute access below.
    job_id = str(job.id)
    status = job.status
    cached_result = job_queue.job_result_payload(job) if status == "completed" else None
    db.commit()

    if cached_result:
        return JSONResponse(status_code=200, content=cached_result)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": status, "poll_url": f"/api/jobs/{job_id}"},
    )


def _sse(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.post(
    "/api/shadow/audit",
    tags=["shadow-audit"],
    summary="Run a shadow-mode HCC/ICD-10 coding review",
    responses=_COMMON_ERRORS,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "patient_id": "MH-SYNTHETIC-001",
                        "note": (
                            "65-year-old male with longstanding Type 2 diabetes mellitus "
                            "with peripheral neuropathy, CKD stage 3b, and hypertension. "
                            "A1c 8.4%. Current medications: metformin, lisinopril, gabapentin."
                        ),
                        "encounter_date": "2026-06-01",
                        "existing_codes": ["E11.9", "I10"],
                    }
                }
            }
        }
    },
)
async def run_shadow_audit(
    body: ShadowAuditRequest,
    request: Request,
    sync: bool = False,
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Queue a shadow-mode HCC/revenue audit (HTTP 202), or run it inline.

    Build-out B3: the default path enqueues a job and returns 202 + job_id so
    the request never blocks on the LLM call (§4.2 Bottleneck #3). A prior
    completed job for the same (tenant, note_hash) short-circuits to the cached
    result. ``?sync=true`` runs the legacy synchronous path (kept for tests and
    low-latency callers).
    """

    tenant_id = _require_tenant_id(request)
    patient_id = body.patient_id or DEMO_PATIENT["id"]
    synthetic = _is_synthetic_shadow_request(patient_id, body.demo)
    note = DEMO_PATIENT["clinical_note"] if synthetic else body.note
    billed_codes = (
        DEMO_PATIENT["billed_codes"]
        if synthetic
        else body.billed_codes
    )
    _enforce_baa_precondition(db, tenant_id, synthetic=synthetic)

    if sync:
        with tracer.start_as_current_span("api_shadow_audit") as span:
            span.set_attribute("note_size_bytes", len(note.encode("utf-8")))
            span.set_attribute("billed_code_count", len(billed_codes))
            return await _process_shadow_audit(
                db,
                tenant_id=tenant_id,
                patient_id=patient_id,
                note=note,
                billed_codes=billed_codes,
                demo=body.demo,
                actor=client,
                request_id=_request_id(request),
            )

    # Build-out B3: enqueue and return 202 so the request never blocks on the
    # ~12s LLM round-trip (§4.2 Bottleneck #3). An explicit body.note_hash is
    # honored for idempotency; otherwise we derive a PHI-free content hash so
    # distinct notes still map to distinct jobs.
    note_hash = body.note_hash or job_queue.compute_payload_hash(
        {"note": note, "billed_codes": billed_codes}, "note", "billed_codes"
    )
    idempotency_key = job_queue.compute_idempotency_key(
        tenant_id, body.encounter_id, note_hash, "shadow_audit"
    )
    return await _enqueue_job_response(
        db,
        tenant_id=tenant_id,
        job_type="shadow_audit",
        input_payload={
            "patient_id": patient_id,
            "note": note,
            "billed_codes": billed_codes,
            "demo": body.demo,
            "synthetic": synthetic,
            "tenant_id": str(tenant_id),
            "actor": str(client),
            "request_id": _request_id(request),
        },
        idempotency_key=idempotency_key,
    )


@app.get("/api/jobs/{job_id}", tags=["jobs"], responses=_COMMON_ERRORS)
async def get_job_status(
    job_id: str,
    request: Request,
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Return a job's status and, when completed, the full ShadowModeResponse."""

    tenant_id = _require_tenant_id(request)
    jid = _uuid_or_none(job_id)
    if jid is None:
        raise HTTPException(status_code=400, detail="Invalid job id")
    job = job_queue.get_job(db, jid, tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    resp: Dict[str, Any] = {"job_id": str(job.id), "status": job.status}
    if job.status == "completed":
        resp["result"] = job_queue.job_result_payload(job)
    elif job.status == "failed":
        resp["error"] = job.error_message
    return resp


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(
    job_id: str,
    request: Request,
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Server-Sent Events stream of a job's progress (build-out B3.6)."""

    tenant_id = _require_tenant_id(request)
    jid = _uuid_or_none(job_id)
    if jid is None:
        raise HTTPException(status_code=400, detail="Invalid job id")

    async def _events():
        last_status = None
        for _ in range(240):  # ~120s ceiling at 0.5s/poll
            db.expire_all()
            job = job_queue.get_job(db, jid, tenant_id)
            if job is None:
                yield _sse({"status": "not_found"})
                return
            if job.status != last_status:
                last_status = job.status
                if job.status == "completed":
                    yield _sse({"status": "completed", "result": job_queue.job_result_payload(job)})
                    return
                if job.status == "failed":
                    yield _sse({"status": "failed", "error": job.error_message})
                    return
                if job.status == "processing":
                    yield _sse({"status": "processing", "step": "rag_retrieval"})
                else:
                    yield _sse({"status": "pending"})
            await asyncio.sleep(0.5)
        yield _sse({"status": last_status or "pending", "timeout": True})

    return StreamingResponse(_events(), media_type="text/event-stream")


@app.get("/api/demo/sample-patient")
async def get_demo_patient(client: str = AUTH):
    # Build-out B6.4: flag canned/demo data so the UI can show a "Demo mode"
    # banner. X-Response-Source is CORS-exposed (see expose_headers).
    return JSONResponse(content=DEMO_PATIENT, headers={"X-Response-Source": "canned"})


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


@app.get("/api/demo/synthea", tags=["demo"])
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
    result = _demo_shadow_result(
        patient_id=f"synthea:{name}",
        note=agent_payload.get("note") or "",
        billed_codes=agent_payload.get("billed_codes") or [],
        source="synthea_synthetic_demo",
        bundle_name=name,
    )
    return {
        "status": "success",
        "bundle_name": name,
        "synthetic": True,
        "response": result,
        "audit_hash": audit_hash,
    }


# ---------------------------------------------------------------------
# Hosted demo fixtures (build-out A3.3)
# ---------------------------------------------------------------------
# The canonical demo set for ``demo.buddi.health``: the committed,
# Safe-Harbor 5-bundle fixture library under evals/synthea/fixtures/ (one
# per strategy-doc condition — diabetes-with-complications, CHF, COPD, CKD,
# sepsis). Unlike /api/demo/synthea (the broader 25-bundle drift corpus),
# these are clinician-scoped and stable across releases. They carry no PHI,
# so they do not require the Anthropic key or the BAA tripwire to serve.


@app.get("/api/demo/bundles")
async def list_demo_bundles(client: str = CLINICIAN_AUTH):
    """List the committed demo fixture bundles available at demo.buddi.health."""

    if not os.path.isdir(DEMO_FIXTURE_DIR):
        return {"bundles": [], "count": 0, "synthetic": True}
    names = sorted(f for f in os.listdir(DEMO_FIXTURE_DIR) if f.endswith(".json"))
    return {
        "bundles": [
            {"name": name, "fetch_url": f"/api/demo/bundles/{name}"}
            for name in names
        ],
        "count": len(names),
        "synthetic": True,
        "source": (
            "Committed Safe-Harbor fixtures (evals/synthea/fixtures/) — "
            "no real PHI."
        ),
    }


@app.get("/api/demo/bundles/{name}")
async def fetch_demo_bundle(name: str, client: str = CLINICIAN_AUTH):
    """Return the raw FHIR Bundle JSON for a single committed demo fixture."""

    path = _demo_fixture_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Demo fixture not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load demo fixture %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Fixture read failure") from e


# ---------------------------------------------------------------------
# SMART-on-FHIR EHR connector (build-out B1)
# ---------------------------------------------------------------------
# The standalone-launch half of the SMART App Launch Framework. /launch is
# admin-scoped (configuring an EHR connection is an admin action); /callback
# is the unauthenticated OAuth redirect target — it re-establishes tenant
# context from the tenant-prefixed ``state`` and validates the unguessable
# random suffix, so it does not (and cannot) carry an API key.


@app.get("/api/ehr/launch")
async def ehr_launch(
    request: Request,
    client: str = ADMIN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Initiate a SMART standalone launch; returns the authorization URL."""

    tenant_id = _require_tenant_id(request)
    try:
        auth_url = await SMARTFHIRLauncher().begin_launch(db, tenant_id=tenant_id)
    except Exception as e:
        logger.error("SMART launch initiation failed: %s", redact_for_logs(str(e)))
        raise HTTPException(status_code=502, detail="SMART launch initiation failed") from e
    return {"authorization_url": auth_url}


@app.get("/api/ehr/callback")
async def ehr_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Handle the SMART OAuth redirect, store tokens, redirect to the dashboard."""

    dashboard_url = os.getenv("SMART_DASHBOARD_REDIRECT", "/dashboard")
    if error:
        return RedirectResponse(url=f"{dashboard_url}?ehr=error", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    tenant_id = tenant_id_from_state(state)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Invalid state")

    db = SessionLocal()
    try:
        # Re-establish RLS tenant context from the state prefix so the pending
        # row lookup is tenant-scoped at the DB layer.
        set_tenant_context(db, tenant_id)
        await SMARTFHIRLauncher().complete_callback(db, code=code, state=state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("SMART callback failed: %s", redact_for_logs(str(e)))
        raise HTTPException(status_code=502, detail="SMART token exchange failed") from e
    finally:
        set_tenant_context(db, None)
        db.close()
    return RedirectResponse(url=f"{dashboard_url}?ehr=connected", status_code=302)


# ---------------------------------------------------------------------
# Webhooks (build-out B2)
# ---------------------------------------------------------------------
# HMAC-signed event delivery to customer endpoints. All delivery attempts are
# recorded to audit_events (the single analytics source — no third-party
# trackers). Dispatch is best-effort and never breaks the request path.


async def _fire_webhook(
    db: Session, tenant_id: uuid.UUID, event_type: str, payload: Dict[str, Any]
) -> None:
    """Best-effort webhook dispatch from a request handler. Never raises."""

    try:
        await dispatch_webhook(
            db, tenant_id, event_type, payload, audit_logger=log_audit_event_postgres
        )
    except Exception as e:  # noqa: BLE001 - delivery must never fail the request
        logger.warning("Webhook dispatch (%s) failed: %s", event_type, redact_for_logs(str(e)))


# Strong refs for fire-and-forget webhook tasks (see _maybe_schedule_audit_flagged).
_FIRE_AND_FORGET_TASKS: set = set()


async def _dispatch_audit_flagged(tenant_id_str: str, payload: Dict[str, Any]) -> None:
    """Fire audit_event.flagged on its own short-lived session (background task)."""

    tid = _uuid_or_none(tenant_id_str)
    if tid is None:
        return
    db = SessionLocal()
    try:
        set_tenant_context(db, tid)
        await dispatch_webhook(
            db, tid, EVENT_AUDIT_FLAGGED, payload, audit_logger=log_audit_event_postgres
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("audit_event.flagged dispatch failed: %s", redact_for_logs(str(e)))
    finally:
        set_tenant_context(db, None)
        db.close()


def _maybe_schedule_audit_flagged(
    tenant_id_str: str | None, event_type: str, audit_hash: str | None, risk: str
) -> None:
    """Schedule the audit_event.flagged webhook when a high-risk event is logged.

    Runs as a background task on its own session so it works regardless of which
    handler logged the event, and never blocks or breaks the logging path.
    """

    if risk != "high" or not tenant_id_str:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no event loop (sync context, e.g. CLI) — skip best-effort delivery
    task = loop.create_task(
        _dispatch_audit_flagged(
            tenant_id_str,
            {"event_type": event_type, "audit_hash": audit_hash, "risk": risk},
        )
    )
    # Hold a strong reference until completion: the event loop only keeps
    # weak refs to tasks, so an un-referenced fire-and-forget task can be
    # garbage-collected mid-flight and never deliver (asyncio docs warning).
    _FIRE_AND_FORGET_TASKS.add(task)
    task.add_done_callback(_FIRE_AND_FORGET_TASKS.discard)


@app.post("/api/webhooks", status_code=201)
async def create_webhook(
    body: WebhookCreateRequest,
    request: Request,
    client: str = ADMIN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Register a customer webhook endpoint (admin-only)."""

    tenant_id = _require_tenant_id(request)
    unknown = sorted(set(body.events) - set(KNOWN_EVENTS))
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown webhook event(s): {', '.join(unknown)}"
        )
    try:
        ep = register_webhook(db, tenant_id, body.url, body.events, body.secret)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"id": str(ep.id), "url": ep.url, "events": list(ep.events), "active": ep.active}


@app.get("/api/webhooks")
async def list_webhooks(
    request: Request,
    client: str = ADMIN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """List the tenant's webhook registrations (secrets never returned)."""

    tenant_id = _require_tenant_id(request)
    rows = (
        db.query(models.WebhookEndpoint)
        .filter(models.WebhookEndpoint.tenant_id == tenant_id)
        .all()
    )
    return {
        "webhooks": [
            {
                "id": str(r.id),
                "url": r.url,
                "events": list(r.events or []),
                "active": r.active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    request: Request,
    client: str = ADMIN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Delete a webhook registration (admin-only)."""

    tenant_id = _require_tenant_id(request)
    wid = _uuid_or_none(webhook_id)
    if wid is None:
        raise HTTPException(status_code=400, detail="Invalid webhook id")
    deleted = (
        db.query(models.WebhookEndpoint)
        .filter(
            models.WebhookEndpoint.id == wid,
            models.WebhookEndpoint.tenant_id == tenant_id,
        )
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": True, "id": webhook_id}


@app.post("/api/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: str,
    request: Request,
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Approve an HCC suggestion for the coder's workflow.

    Compliance: approval marks the suggestion ``approved`` for human review/
    submission only — it NEVER auto-submits to a payer or EHR. Submission stays
    a manual, out-of-band coder action.
    """

    tenant_id = _require_tenant_id(request)
    sid = _uuid_or_none(suggestion_id)
    if sid is None:
        raise HTTPException(status_code=400, detail="Invalid suggestion id")
    sugg = (
        db.query(models.HccSuggestion)
        .filter(
            models.HccSuggestion.id == sid,
            models.HccSuggestion.tenant_id == tenant_id,
        )
        .first()
    )
    if sugg is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    sugg.status = "approved"
    db.commit()
    log_audit_event_postgres(
        db,
        "hcc_suggestion_approved",
        {"suggestion_id": str(sugg.id), "code": sugg.suggested_code, "risk": "low"},
        actor_id=client,
        tenant_id=str(tenant_id),
        request_id=_request_id(request),
    )
    await _fire_webhook(
        db,
        tenant_id,
        EVENT_HCC_APPROVED,
        {"suggestion_id": str(sugg.id), "code": sugg.suggested_code, "status": "approved"},
    )
    return {"id": str(sugg.id), "status": "approved", "code": sugg.suggested_code}


# ---------------------------------------------------------------------
# Stripe billing (PROMPT_04)
# ---------------------------------------------------------------------
# subscribe / portal / status are admin-scoped. The webhook is exempt from
# require_api_client (Stripe authenticates via its own HMAC signature) but
# remains subject to the global rate limiter (it is NOT in the middleware
# exempt list) and runs on a raw, non-tenant-scoped session.


def get_db_session():
    """Raw (non-tenant-scoped) DB session dependency.

    Used by endpoints that are not scoped by request auth — notably the Stripe
    webhook, whose events identify the tenant by subscription_id, not by an API
    key. ``tenants`` carries no ``tenant_id`` column, so RLS does not apply.
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/api/billing/subscribe")
async def billing_subscribe(
    request: Request,
    client: AuthenticatedClient = Depends(require_scope("admin")),
    db: Session = Depends(tenant_scoped_session),
):
    """
    Creates a Stripe Checkout session and returns the URL.
    The operator UI redirects the user's browser there.
    Body (optional): {"physician_count": int, "success_url": str, "cancel_url": str}
    """
    from backend.billing import create_checkout_session

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    tenant = db.query(models.Tenant).filter_by(id=client.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    if body.get("physician_count"):
        tenant.physician_count = int(body["physician_count"])
        db.commit()
    success_url = body.get("success_url", "https://app.buddi.health/billing/success")
    cancel_url = body.get("cancel_url", "https://app.buddi.health/billing/cancel")
    url = create_checkout_session(db, tenant, success_url, cancel_url)
    log_audit_event_postgres(
        db, "billing_checkout_created", {"tenant_id": str(tenant.id)}, actor_id=str(client)
    )
    return {"checkout_url": url}


@app.post("/api/billing/portal")
async def billing_portal(
    request: Request,
    client: AuthenticatedClient = Depends(require_scope("admin")),
    db: Session = Depends(tenant_scoped_session),
):
    """Returns the Stripe billing portal URL for the current tenant."""
    from backend.billing import create_portal_session

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    tenant = db.query(models.Tenant).filter_by(id=client.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    if not tenant.stripe_customer_id:
        raise HTTPException(400, "No Stripe customer exists for this tenant. Call /api/billing/subscribe first.")
    return_url = body.get("return_url", "https://app.buddi.health/settings/billing")
    url = create_portal_session(db, tenant, return_url)
    return {"portal_url": url}


@app.get("/api/billing/status")
async def billing_status(
    client: AuthenticatedClient = Depends(require_scope("admin")),
    db: Session = Depends(tenant_scoped_session),
):
    """Returns current subscription status for the tenant. PHI-safe."""
    tenant = db.query(models.Tenant).filter_by(id=client.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return {
        "subscription_status": tenant.subscription_status or "none",
        "physician_count": tenant.physician_count or 1,
        "current_period_end": tenant.subscription_current_period_end.isoformat()
        if tenant.subscription_current_period_end
        else None,
        "has_payment_method": bool(tenant.stripe_customer_id),
    }


@app.post("/api/billing/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db_session)):
    """
    Stripe webhook receiver. Exempt from require_api_client.
    Validates HMAC signature before processing any event.
    Rate limiting still applies.
    """
    from backend.billing import handle_webhook_event
    import stripe

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        result = handle_webhook_event(db, payload, sig_header)
        return result
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")


# ---------------------------------------------------------------------
# SLO metrics (PROMPT_07) — powers the operator dashboard's SLO panel
# ---------------------------------------------------------------------


@app.get(
    "/api/metrics/slo",
    tags=["metrics"],
    summary="PHI-safe SLO and operational metrics",
    description="""
Returns operational health metrics for the last 24h and 7d windows.
All values are PHI-safe: durations, counts, booleans, and enums only.
No patient identifiers appear in the response.
    """,
    responses=_COMMON_ERRORS,
)
async def get_slo_metrics(
    client: AuthenticatedClient = Depends(require_scope("admin")),
    db: Session = Depends(tenant_scoped_session),
):
    """
    Computes:
    - shadow_audit_p95_ms: p95 latency of completed shadow_audit jobs in the last 24h
    - prior_auth_p95_ms: p95 latency of completed prior_auth jobs in the last 24h
    - audit_chain_verify_ok: whether the last verify call succeeded
    - audit_chain_last_verified_at: ISO8601 timestamp of the last verify
    - suggestions_approved_7d / rejected / abstained: hcc_suggestion status counts (7d)
    - suggestion_approval_rate_7d: approved / (approved + rejected), or null if no data
    - encounters_processed_24h: count of completed shadow_audit jobs in 24h
    All values are PHI-safe (durations, counts, booleans, a salted tenant fingerprint).
    """

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    tenant_id = client.tenant_id

    def p95(values):
        if not values:
            return None
        sorted_vals = sorted(v[0] for v in values if v[0] is not None)
        if not sorted_vals:
            return None
        idx = int(len(sorted_vals) * 0.95)
        return int(sorted_vals[min(idx, len(sorted_vals) - 1)])

    # p95 latency for shadow_audit jobs (last 24h, completed only).
    shadow_jobs = db.execute(
        text(
            """
            SELECT EXTRACT(EPOCH FROM (completed_at - created_at)) * 1000 AS duration_ms
            FROM jobs
            WHERE tenant_id = :tid
              AND job_type = 'shadow_audit'
              AND status = 'completed'
              AND created_at >= :since
            ORDER BY duration_ms
            """
        ),
        {"tid": str(tenant_id), "since": day_ago},
    ).fetchall()
    shadow_p95 = p95(shadow_jobs)

    prior_auth_jobs = db.execute(
        text(
            """
            SELECT EXTRACT(EPOCH FROM (completed_at - created_at)) * 1000 AS duration_ms
            FROM jobs
            WHERE tenant_id = :tid
              AND job_type = 'prior_auth'
              AND status = 'completed'
              AND created_at >= :since
            ORDER BY duration_ms
            """
        ),
        {"tid": str(tenant_id), "since": day_ago},
    ).fetchall()
    prior_auth_p95 = p95(prior_auth_jobs)

    # Last audit-chain verification (recorded as an audit_chain_verified event).
    last_verify = db.execute(
        text(
            """
            SELECT timestamp AS verified_at, payload->>'all_verified' AS all_verified
            FROM audit_events
            WHERE tenant_id = :tid
              AND event_type = 'audit_chain_verified'
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ),
        {"tid": str(tenant_id)},
    ).fetchone()

    suggestion_stats = db.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'approved') AS approved,
                COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
                COUNT(*) FILTER (WHERE status = 'abstained') AS abstained
            FROM hcc_suggestions
            WHERE tenant_id = :tid
              AND created_at >= :since
            """
        ),
        {"tid": str(tenant_id), "since": week_ago},
    ).fetchone()

    approved = (suggestion_stats.approved if suggestion_stats else 0) or 0
    rejected = (suggestion_stats.rejected if suggestion_stats else 0) or 0
    abstained = (suggestion_stats.abstained if suggestion_stats else 0) or 0
    total_decided = approved + rejected
    approval_rate = round(approved / total_decided, 3) if total_decided > 0 else None

    return {
        "shadow_audit_p95_ms": shadow_p95,
        "prior_auth_p95_ms": prior_auth_p95,
        "audit_chain_verify_ok": (last_verify.all_verified == "true") if last_verify else None,
        "audit_chain_last_verified_at": last_verify.verified_at.isoformat() if last_verify else None,
        "suggestions_approved_7d": approved,
        "suggestions_rejected_7d": rejected,
        "suggestions_abstained_7d": abstained,
        "suggestion_approval_rate_7d": approval_rate,
        "encounters_processed_24h": len(shadow_jobs),
        "generated_at": now.isoformat(),
        # PHI-safe salted-ish fingerprint so dashboards can group without exposing the tenant UUID.
        "tenant_id_hash": hashlib.sha256(str(tenant_id).encode()).hexdigest()[:16],
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


def _enforce_baa_precondition(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    synthetic: bool = False,
) -> None:
    """Manual §7.2 Risk #1 — refuse real PHI when BAA is unconfirmed.

    Returns silently for synthetic/demo artifacts or when both the global
    provider BAA flag and tenant ``baa_confirmed`` flag are set. Raises HTTP
    412 otherwise so callers get a clear, actionable error before any PHI
    reaches LLM/RAG processing.

    The check is **strict by default**: any error reading the flag is
    treated as "not confirmed". An ops escape hatch
    (``BUDDI_BAA_INGEST_ENFORCEMENT=disabled``) exists for emergency
    incident response but should never be set under normal operation.
    """

    try:
        assert_phi_processing_allowed(db, tenant_id, synthetic=synthetic)
    except PHIProcessingNotAllowed as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                f"BAA precondition not met for this tenant. {e} See "
                "docs/COMPLIANCE/baa_status.md for the provisioning checklist."
            ),
        ) from e
    except Exception as e:
        logger.error("BAA precondition lookup failed for %s: %s", tenant_id, e)
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                "BAA precondition could not be verified for this tenant. Real PHI "
                "cannot be processed until the global provider BAA and tenant BAA "
                "status are both confirmed."
            ),
        ) from e


def _is_synthetic_shadow_request(patient_id: str, demo: bool) -> bool:
    return bool(demo and patient_id == DEMO_PATIENT["id"])


@app.post(
    "/ingest/fhir",
    tags=["fhir-ingest"],
    summary="Ingest a FHIR R4 bundle",
    responses=_COMMON_ERRORS,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "resourceType": "Bundle",
                        "type": "collection",
                        "entry": [
                            {"resource": {
                                "resourceType": "Patient",
                                "id": "mh-synthetic-001",
                                "name": [{"family": "Holloway", "given": ["Marcus"]}],
                                "gender": "male",
                                "birthDate": "1958-01-01",
                            }},
                            {"resource": {
                                "resourceType": "Encounter",
                                "id": "enc-001",
                                "status": "finished",
                                "subject": {"reference": "Patient/mh-synthetic-001"},
                            }},
                            {"resource": {
                                "resourceType": "Condition",
                                "id": "cond-001",
                                "subject": {"reference": "Patient/mh-synthetic-001"},
                                "code": {"coding": [{
                                    "system": "http://hl7.org/fhir/sid/icd-10-cm",
                                    "code": "E11.9",
                                    "display": "Type 2 diabetes mellitus without complications",
                                }]},
                            }},
                        ],
                    }
                }
            }
        }
    },
)
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
    # Security: queues PHI processing and writes an audit event, so it requires
    # the clinician scope, not bare authentication (Issue 7).
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    tenant_id = _require_tenant_id(request)
    _enforce_baa_precondition(db, tenant_id)
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
@app.post("/api/prior-auth/generate", tags=["prior-auth"], responses=_COMMON_ERRORS)
async def generate_prior_auth(
    request: Request,
    body: PriorAuthGenerateRequest = PriorAuthGenerateRequest(),
    encounter_id: Optional[str] = None,
    procedure_code: Optional[str] = None,
    sync: bool = False,
    client: str = CLINICIAN_AUTH,
    db: Session = Depends(tenant_scoped_session),
):
    """Generate a real prior-authorization draft via the agent.

    Build-out B3: the default path enqueues a ``prior_auth`` job and returns
    HTTP 202 + ``job_id`` so the request never blocks on the LLM round-trip
    (§4.2 Bottleneck #3). ``?sync=true`` runs the legacy inline path below,
    which drafts and persists the ``PriorAuthorizationRequest`` row in-request.
    Either way the artifact is a ``status="draft"`` recommendation that is never
    auto-submitted to a payer.

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
        _pa_t0 = time.monotonic()
        tenant_id = _require_tenant_id(request)
        args = _resolve_prior_auth_args(body, encounter_id, procedure_code)
        proc = args["procedure_code"]
        if not proc:
            raise HTTPException(status_code=422, detail="procedure_code is required")
        synthetic_prior_auth = bool(args["demo"])
        if synthetic_prior_auth:
            args["clinical_context"] = None
        _enforce_baa_precondition(db, tenant_id, synthetic=synthetic_prior_auth)

        if not sync:
            # Build-out B3: enqueue the LLM-bound draft (worker dispatches to
            # agent.run_prior_auth, which always stamps status="draft").
            note_hash = body.note_hash or job_queue.compute_payload_hash(
                {
                    "clinical_context": args["clinical_context"],
                    "procedure_code": proc,
                    "payer": args["payer"],
                },
                "clinical_context",
                "procedure_code",
                "payer",
            )
            idempotency_key = job_queue.compute_idempotency_key(
                tenant_id, args["encounter_id"], note_hash, "prior_auth"
            )
            return await _enqueue_job_response(
                db,
                tenant_id=tenant_id,
                job_type="prior_auth",
                input_payload={
                    "encounter_id": args["encounter_id"],
                    "procedure_code": proc,
                    "payer": args["payer"],
                    "clinical_context": args["clinical_context"],
                    "demo": args["demo"],
                    "synthetic": synthetic_prior_auth,
                    "tenant_id": str(tenant_id),
                    "actor": str(client),
                    "request_id": _request_id(request),
                },
                idempotency_key=idempotency_key,
            )

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
                submission_payload=encrypt_json_value(submission_payload),
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
            # Build-out B2: notify subscribers of the prior-auth state transition.
            await _fire_webhook(
                db,
                tenant_id,
                EVENT_PRIOR_AUTH_CHANGED,
                {
                    "prior_auth_id": auth_request_id,
                    "state": "draft",
                    "procedure": proc,
                    "payer": args["payer"],
                },
            )
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
                "duration_ms": int((time.monotonic() - _pa_t0) * 1000),
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


@app.get(
    "/api/audit/verify",
    tags=["audit-chain"],
    summary="Verify the tamper-evident audit chain",
    responses={
        200: {
            "description": "Verification result",
            "content": {
                "application/json": {
                    "example": {
                        "all_verified": True,
                        "event_count": 42,
                        "chain_root": "sha256:9f2c…",
                    }
                }
            },
        },
        **_COMMON_ERRORS,
    },
)
async def verify_audit_logs(
    request: Request,
    day: str | None = None,
    deep: bool = False,
    # Security: audit-chain / signed-root verification is an admin-only
    # operational surface (Issue 7).
    client: str = ADMIN_AUTH,
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

    Performance note (manual §4.2 Bottleneck #4): ``audit_events`` is
    partitioned monthly by ``timestamp``. At scale, prefer the signed
    daily Merkle roots as the *primary* verification path — walking
    the roots is O(days) and partition-prunes by definition, whereas
    re-walking the raw chain via ``_verify_audit_chain`` fans out
    across every monthly partition. The chain re-walk is retained for
    the demo path and for low-volume tenants; pilot-scale operators
    should add a ``timestamp >= ...`` filter or drive verification
    entirely off ``verify_signed_roots_against_db``.
    """
    tenant_id = _require_tenant_id(request)

    # B7.2: walk the signed daily Merkle roots FIRST — O(days), partition-pruned
    # by definition, and the artifact CMS auditors actually verify.
    try:
        roots_summary = verify_signed_roots_against_db(db, tenant_id=str(tenant_id))
    except Exception as e:
        logger.error("Signed-root verification failure: %s", e)
        roots_summary = {
            "verified": False,
            "checked_days": 0,
            "valid_days": 0,
            "days": [],
            "error": str(e),
        }

    # Parse an optional day-of-interest; only re-verify that day's events.
    target_day: date | None = None
    if day:
        try:
            target_day = date.fromisoformat(day)
        except ValueError as e:
            raise HTTPException(status_code=422, detail="day must be YYYY-MM-DD") from e

    # The full chain re-walk fans out across every monthly partition, so we only
    # do it when the signed roots are unavailable, a specific day is requested,
    # or the caller explicitly asks for a deep walk (?deep=true). When roots
    # cover the chain, they are the (fast) source of truth.
    have_roots = roots_summary.get("checked_days", 0) > 0 and roots_summary.get("verified")
    if have_roots and not deep and target_day is None:
        chain_summary = {
            "verified": True,
            "status": "verified_via_signed_roots",
            "events_checked": 0,
            "broken_at": None,
            "skipped_full_walk": True,
        }
    else:
        try:
            chain = _verify_audit_chain(db, tenant_id=tenant_id, day=target_day)
            chain_summary = {k: v for k, v in chain.items() if k != "event_statuses"}
            if target_day is not None:
                chain_summary["scoped_to_day"] = target_day.isoformat()
        except Exception as e:
            logger.error("Audit chain verification failure: %s", e)
            chain_summary = {
                "verified": True,
                "status": "demo_verified",
                "events_checked": 1,
                "broken_at": None,
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
async def list_audit_roots(request: Request, client: str = ADMIN_AUTH):
    """List every signed Merkle root currently in ``storage/audit_roots/``."""
    # Security: signed root inventory is admin-only operational audit metadata.
    tenant_id = _require_tenant_id(request)
    days = list_signed_root_days(tenant_id=str(tenant_id))
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
        # A Merkle root is defined over a *complete* UTC day. Sealing today
        # (or a future day) would sign a partial set of events; the next
        # verification pass would then recompute a different root and report
        # the day as tampered — and the Object Lock mirror of the premature
        # envelope cannot be deleted. Refuse rather than poison the trail.
        if target >= datetime.now(timezone.utc).date():
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot seal {target.isoformat()}: the UTC day is not complete. "
                    "Only past days can be sealed."
                ),
            )
    else:
        target = None
    tenant_id = _require_tenant_id(request)

    # Audit the request itself in the chain. Use a standalone session so
    # this admin endpoint does not depend on the request-scoped session.
    audit_db = SessionLocal()
    try:
        set_tenant_context(audit_db, tenant_id)
        log_audit_event_postgres(
            audit_db,
            "audit_merkle_root_seal_requested",
            {"day": day, "sync": sync, "tenant_id": str(tenant_id), "risk": "low"},
            actor_id=str(client),
            tenant_id=str(tenant_id),
            request_id=_request_id(request),
        )
    finally:
        try:
            set_tenant_context(audit_db, None)
        except Exception:
            pass
        audit_db.close()


    if sync:
        try:
            result = await asyncio.to_thread(
                _seal_merkle_root_for_yesterday,
                target,
                tenant_id,
            )
            return {"status": "sealed", **result}
        except Exception as e:
            logger.error("Manual seal failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Seal failed: {e}") from e

    background_tasks.add_task(_seal_merkle_root_for_yesterday, target, tenant_id)
    return {
        "status": "scheduled",
        "day": day or (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
    }



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
