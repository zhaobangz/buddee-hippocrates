"""
Buddi Clinical Agent — Production API v3
Integrated with tracing, shadow mode, and enhanced routing.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import logging

from core.agent import Agent
from core.config import Config
from core.safety import get_recent_audit_events
from core.tracing import setup_tracing, get_tracer, shutdown_tracing
from contextlib import asynccontextmanager

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize tracing
setup_tracing(service_name="buddi-clinical-api")
tracer = get_tracer(__name__)

# Lifecycle Management
@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    with tracer.start_as_current_span("system_startup"):
        logger.info("Initializing Agent System...")
        agent = Agent()
        yield
        logger.info("System optimized shutdown.")
        shutdown_tracing()

app = FastAPI(
    title="Buddi Clinical API",
    description="Full-scale Clinical Decision Support Engine",
    version="3.1.0",
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

class ChatRequest(BaseModel):
    message: str

class PatientContext(BaseModel):
    patient_id: str
    name: str
    conditions: List[str] = []
    medications: List[str] = []
    notes: Optional[str] = None

class ShadowModeRequest(BaseModel):
    message: str
    expert_action: str

# --- Endpoints ---

@app.get("/api/health")
async def health():
    return {"status": "active", "agent": agent is not None}

@app.get("/api/status")
async def get_status():
    """Real-time health monitor for clinical tools and safety layers."""
    return {
        "agent_running": agent is not None,
        "assistant_name": Config.ASSISTANT_NAME,
        "version": Config.VERSION,
        "memory_enabled": Config.MEMORY_ENABLED,
        "safety_layers": ["audit_trail", "human_in_the_loop", "prompt_sanitization"]
    }

@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not agent: raise HTTPException(status_code=503)
    with tracer.start_as_current_span("handle_chat") as span:
        span.set_attribute("input.length", len(request.message))
        response = agent.handle(request.message)
        return {"response": response, "status": "success"}

@app.get("/api/patient")
async def get_patient_profile():
    """Consolidated Patient Intelligence: Context + History + Brief"""
    if not agent or not agent.memory: raise HTTPException(status_code=503)
    
    context = agent.memory.get_patient_context()
    if not context or not context.get("patient_id"):
        return {"status": "empty", "message": "No active patient context"}

    # Generate real-time brief
    from tools.ehr_reader import generate_patient_brief
    brief = generate_patient_brief(context)
    
    # Recent history
    history = agent.memory.recall(num_interactions=5)
    
    return {
        "context": context,
        "intelligence_brief": brief,
        "recent_history": history,
        "status": "success"
    }

@app.post("/api/patient")
async def set_patient_profile(data: PatientContext):
    if not agent or not agent.memory: raise HTTPException(status_code=503)
    agent.memory.set_patient_context(
        patient_id=data.patient_id,
        name=data.name,
        conditions=data.conditions,
        medications=data.medications,
        notes=data.notes
    )
    return {"status": "success"}

@app.get("/api/risk")
async def get_risk_assessment():
    """High-level risk dashboard data"""
    if not agent or not agent.memory: raise HTTPException(status_code=503)
    ctx = agent.memory.get_patient_context()
    if not ctx: return {"risks": [], "summary": "No context"}
    
    from tools.ehr_reader import _identify_risks
    risks = _identify_risks(ctx.get("conditions", []), ctx.get("medications", []))
    
    # Structure for frontend heatmap
    structured = [{"label": r, "level": "high" if "risk" in r.lower() else "medium"} for r in risks]
    return {"risks": structured, "patient_id": ctx.get("patient_id")}

@app.get("/api/audit")
async def get_audit_logs():
    return {"events": get_recent_audit_events(20)}

@app.post("/api/shadow-mode/compare")
async def shadow_mode_compare(request: ShadowModeRequest):
    """Compare agent intent against expert baseline (QA)"""
    if not agent: raise HTTPException(status_code=503)
    # Detect intent via agent but return comparison
    detected = agent._detect_intent(request.message)
    return {
        "input": request.message,
        "expert_baseline": request.expert_action,
        "agent_suggestion": detected,
        "match": detected.lower() == request.expert_action.lower()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
