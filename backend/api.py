"""
Buddi RCM API v4.0
Integrated with cryptographic audit trails, shadow mode RCM, and QA Audits.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import logging
import json
import time
import hashlib

from core.agent import Agent
from core.config import Config
from core.safety import get_recent_audit_events
from core.tracing import setup_tracing, get_tracer, shutdown_tracing
from contextlib import asynccontextmanager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize tracing
setup_tracing(service_name="buddi-rcm-api")
tracer = get_tracer(__name__)

# Lifecycle Management
@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    with tracer.start_as_current_span("system_startup"):
        logger.info("Initializing RCM Agent System...")
        agent = Agent()
        yield
        logger.info("System optimized shutdown.")
        shutdown_tracing()

app = FastAPI(
    title="Buddi RCM & Compliance API",
    description="Backend for Shadow Mode Revenue Integrity and Chart Auditing",
    version="4.0.0",
    lifespan=lifespan
)

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent: Optional[Agent] = None

# --- Models ---
class PayloadRequest(BaseModel):
    payload: str
    task_type: Optional[str] = "detect" # shadow_mode_rcm, specialty_prior_auth, retrospective_qa_audit

class PatientContext(BaseModel):
    patient_id: str
    name: str
    conditions: List[str] = []
    medications: List[str] = []

# cryptographic audit functions
def _generate_crypto_trail(action_type: str, data: str) -> str:
    timestamp = str(time.time())
    payload_hash = hashlib.sha256(f"{action_type}:{data}:{timestamp}".encode('utf-8')).hexdigest()
    return payload_hash

from core.safety import get_recent_audit_events, log_audit_event, verify_audit_chain
# ... (rest of imports unchanged)

# --- Endpoints ---

@app.get("/api/health")
async def health():
    return {"status": "active", "agent": agent is not None, "mode": "RCM_Audit"}

@app.post("/api/process")
async def process_task(request: PayloadRequest):
    """Core endpoint for processing RCM or QA Audit tasks"""
    if not agent: raise HTTPException(status_code=503)
    with tracer.start_as_current_span("process_task") as span:
        span.set_attribute("task_type", request.task_type)
        
        # Process task
        response = agent.handle(request.payload, task_type=request.task_type)
        
        # Use the NEW cryptographically chained audit log
        log_audit_event(
            event_type=request.task_type,
            details={"payload": request.payload, "output_preview": response[:200]},
            user_id="api_consumer"
        )
        
        return {
            "response": response, 
            "status": "success"
        }

@app.get("/api/audit/verify")
async def verify_audit():
    """Verify the integrity of the audit chain."""
    return verify_audit_chain()

@app.get("/api/audit")
async def get_audit_logs():
    """Fetch recent compliance events, fully cryptographically auditable."""
    return {"events": get_recent_audit_events(20)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
