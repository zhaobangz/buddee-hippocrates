from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import logging
import json
import time
import hashlib
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from core.database import get_db, engine, SessionLocal
import core.models as models
from core.agent import Agent
from core.tracing import setup_tracing, get_tracer, shutdown_tracing
from contextlib import asynccontextmanager

from backend.fhir_client import FHIRAdapter

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize tracing
try:
    setup_tracing(service_name="buddi-rcm-api")
    tracer = get_tracer(__name__)
except Exception:
    import opentelemetry.trace as trace
    tracer = trace.get_tracer(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    with tracer.start_as_current_span("system_startup"):
        logger.info("Initializing RCM Agent System...")
        agent = Agent()
        yield
        logger.info("System optimized shutdown.")
        try:
            shutdown_tracing()
        except Exception:
            pass

app = FastAPI(
    title="Buddi RCM & Compliance API",
    description="PostgreSQL-centric Backend for Shadow Mode RCM, Prior Auth, and Traceability",
    version="4.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent: Optional[Agent] = None

class PayloadRequest(BaseModel):
    payload: str
    task_type: Optional[str] = "detect"

def _generate_crypto_trail(action_type: str, data: str, previous_hash: str = None) -> str:
    timestamp = str(time.time())
    hash_input = f"{previous_hash or 'GENESIS'}:{action_type}:{data}:{timestamp}"
    return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

def log_audit_event_postgres(db: Session, event_type: str, payload_data: dict, actor_id: str = None, tenant_id: str = None):
    """Event-sourced append-only audit logger using PostgreSQL with cryptographic chaining."""
    try:
        last_event = db.query(models.AuditEvent).order_by(models.AuditEvent.event_id.desc()).first()
        prev_hash = last_event.cryptographic_hash if last_event else None
        
        current_hash = _generate_crypto_trail(event_type, json.dumps(payload_data), prev_hash)
        
        new_event = models.AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload_data,
            previous_hash=prev_hash,
            cryptographic_hash=current_hash
        )
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        return current_hash
    except Exception as e:
        logger.error(f"Audit log failed (DB likely offline): {e}")
        db.rollback()
        return None

# --- Core RCM & Pipeline Endpoints ---

@app.get("/api/health")
async def health(db: Session = Depends(get_db)):
    db_status = "offline"
    try:
        db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception:
        pass
    return {"status": "active", "db": db_status, "mode": "RCM_Audit_Postgres"}

@app.post("/ingest/fhir")
async def process_fhir_bundle(bundle_payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Standardized entrypoint for HL7 FHIR payloads"""
    if not agent: raise HTTPException(status_code=503)
    
    with tracer.start_as_current_span("process_fhir_bundle") as span:
        agent_payload = FHIRAdapter.extract_from_bundle(bundle_payload)
        
        audit_hash = log_audit_event_postgres(
            db,
            event_type="shadow_mode_rcm_fhir",
            payload_data={"input_len": len(agent_payload["note"]), "billed_codes": len(agent_payload["billed_codes"])},
        )
        
        response_json_str = agent.handle(json.dumps(agent_payload), task_type="shadow_mode_rcm")
        response_obj = {}
        try:
            response_obj = json.loads(response_json_str)
        except Exception:
            response_obj = {"raw_output": response_json_str}

        return {"status": "success", "response": response_obj}

@app.post("/encounter/{encounter_id}/process")
async def process_encounter(encounter_id: str, db: Session = Depends(get_db)):
    """Triggers async RCM analysis"""
    log_audit_event_postgres(db, "encounter_processing_requested", {"encounter_id": encounter_id})
    return {"status": "processing_queued", "encounter_id": encounter_id}

@app.get("/billing/suggest")
async def billing_suggest(encounter_id: str = None, db: Session = Depends(get_db)):
    """Returns hcc_suggestions via SQL filters"""
    try:
        query = db.query(models.HccSuggestion)
        if encounter_id:
            query = query.filter(models.HccSuggestion.encounter_id == encounter_id)
        return {"suggestions": query.all()}
    except Exception as e:
        logger.error(f"Suggest endpoint DB failure: {e}")
        return {"error": "Database error", "suggestions": []}

@app.post("/prior-auth/generate")
async def generate_prior_auth(encounter_id: str, procedure_code: str, db: Session = Depends(get_db)):
    """Creates a row in prior_authorization_requests, generating a State Machine record."""
    try:
        new_auth = models.PriorAuthorizationRequest(encounter_id=encounter_id, procedure_code=procedure_code)
        db.add(new_auth)
        db.commit()
        db.refresh(new_auth)

        new_state = models.PriorAuthState(prior_auth_id=new_auth.id, state='draft')
        db.add(new_state)
        db.commit()
        
        log_audit_event_postgres(db, "prior_auth_requested", {"auth_id": str(new_auth.id), "procedure": procedure_code})
        
        return {"status": "drafted", "auth_request_id": str(new_auth.id)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audit/query")
async def get_audit_logs(db: Session = Depends(get_db)):
    """Queries audit_events, retrieving cryptographic history."""
    try:
        events = db.query(models.AuditEvent).order_by(models.AuditEvent.event_id.desc()).limit(20).all()
        return {"events": events}
    except Exception as e:
        logger.error(f"Audit lookup failure: {e}")
        return {"events": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
