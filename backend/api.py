"""
FastAPI backend for Buddi Clinical Agent System
Exposes the clinical agent functionality as REST API endpoints
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import logging

from core.agent import Agent
from core.config import Config
from core.tracing import setup_tracing, get_tracer, shutdown_tracing
from core.safety import get_recent_audit_events

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize tracing
setup_tracing(service_name="buddi-clinical-backend")
tracer = get_tracer(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Buddi Clinical Agent API",
    description="REST API for the Buddi Clinical Agent System — Healthcare Workflow Intelligence",
    version="2.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance (initialized in startup)
agent: Optional[Agent] = None


# ── Request / Response Models ────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str
    include_history: bool = False


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str
    status: str = "success"
    message_id: Optional[str] = None


class PatientContextRequest(BaseModel):
    """Request model for setting patient context"""
    patient_id: str
    name: str = ""
    conditions: List[str] = []
    medications: List[str] = []
    allergies: List[str] = []
    notes: str = ""


class ShadowModeRequest(BaseModel):
    """Request model for shadow mode comparison"""
    message: str
    expert_action: str


class ShadowModeResponse(BaseModel):
    """Response model for shadow mode comparison"""
    input: str
    expert_baseline: str
    agent_suggestion: str
    match: bool
    status: str = "success"


class StatusResponse(BaseModel):
    """Response model for status endpoint"""
    agent_running: bool
    assistant_name: str
    memory_enabled: bool
    use_voice: bool
    healthcare_tools: Dict[str, bool]
    safety_enabled: bool


# ── Lifecycle Events ─────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    global agent
    try:
        with tracer.start_as_current_span("startup") as span:
            logger.info("Initializing Buddi Clinical Agent...")
            agent = Agent()
            span.set_attribute("agent.initialized", True)
            logger.info(f"{Config.ASSISTANT_NAME} is ready!")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        shutdown_tracing()
        logger.info("Agent shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# ── Health & Status ──────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "buddi-clinical-agent-api",
    }

@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Get the current status of the clinical agent"""
    return StatusResponse(
        agent_running=agent is not None,
        assistant_name=Config.ASSISTANT_NAME,
        memory_enabled=Config.MEMORY_ENABLED,
        use_voice=Config.USE_VOICE,
        healthcare_tools={
            "ehr_reader" : Config.ENABLE_EHR_READER,
            "prior_auth": Config.ENABLE_PRIOR_AUTH,
            "clinical_guidelines": Config.ENABLE_CLINICAL_GUIDELINES,
            "follow_up": Config.ENABLE_FOLLOW_UP,
            "scheduling": Config.ENABLE_SCHEDULING,
        },
        safety_enabled=Config.ENABLE_SAFETY_LAYER,
    )


# ── Chat ─────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the clinical agent and get a response"""
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        with tracer.start_as_current_span("chat_request") as span:
            span.set_attribute("input.length", len(request.message))
            logger.info(f"Processing message: {request.message[:100]}")  # type: ignore

            response_text = agent.handle(request.message)
            span.set_attribute("response.length", len(response_text))

            return ChatResponse(response=response_text, status="success")
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


# ── Patient Context ──────────────────────────────────────────────────

@app.post("/api/patient-context")
async def set_patient_context(request: PatientContextRequest):
    """Set the current patient context"""
    if agent is None or agent.memory is None:
        raise HTTPException(status_code=503, detail="Agent or memory not available")

    agent.memory.set_patient_context(
        patient_id=request.patient_id,
        name=request.name,
        conditions=request.conditions,
        medications=request.medications,
        allergies=request.allergies,
        notes=request.notes,
    )
    return {"status": "success", "message": f"Patient context set for {request.name}"}


@app.get("/api/patient-context")
async def get_patient_context():
    """Get the current patient context"""
    if agent is None or agent.memory is None:
        raise HTTPException(status_code=503, detail="Agent or memory not available")

    ctx = agent.memory.get_patient_context()
    return {"status": "success", "patient_context": ctx}


@app.delete("/api/patient-context")
async def clear_patient_context():
    """Clear the current patient context"""
    if agent is None or agent.memory is None:
        raise HTTPException(status_code=503, detail="Agent or memory not available")

    agent.memory.clear_patient_context()
    return {"status": "success", "message": "Patient context cleared"}


# ── Patient History ──────────────────────────────────────────────────

@app.get("/api/patient-history")
async def get_patient_history(count: int = 10):
    """Get recent conversation history/activity for the patient"""
    if agent is None or agent.memory is None:
        raise HTTPException(status_code=503, detail="Agent or memory not available")

    history = agent.memory.recall(num_interactions=count)
    return {"status": "success", "history": history, "count": len(history)}


# ── Risk Assessment ──────────────────────────────────────────────────

@app.get("/api/risk-assessment")
async def get_risk_assessment():
    """Perform a risk assessment based on current patient context"""
    if agent is None or agent.memory is None:
        raise HTTPException(status_code=503, detail="Agent or memory not available")

    ctx = agent.memory.get_patient_context()
    if not ctx or not ctx.get("patient_id"):
        return {"status": "success", "risks": [], "summary": "No patient context set"}

    # Use the logic from ehr_reader (already imported)
    from tools.ehr_reader import _identify_risks
    risks = _identify_risks(
        ctx.get("conditions", []),
        ctx.get("medications", []),
        ctx.get("allergies", [])
    )

    # Map risk strings to UI-friendly badges/levels
    structured_risks = []
    for r in risks:
        level = "high"
        if "monitor" in r.lower() or "review" in r.lower():
            level = "med"
        elif "history" in r.lower():
            level = "low"
        structured_risks.append({"label": r, "level": level})

    return {
        "status": "success",
        "risks": structured_risks,
        "summary": f"Detected {len(structured_risks)} focus areas for clinical review"
    }


# ── Audit Log ────────────────────────────────────────────────────────

@app.get("/api/audit-log")
async def get_audit_log(count: int = 20):
    """Retrieve recent audit log entries"""
    events = get_recent_audit_events(count)
    return {"status": "success", "events": events, "count": len(events)}


# ── Workflows ────────────────────────────────────────────────────────

@app.get("/api/workflows")
async def list_workflows():
    """List available clinical workflow types"""
    return {
        "status": "success",
        "workflows": [
            {"id": "prior_auth", "name": "Prior Authorization", "description": "Generate and track prior authorization forms", "icon": "📋"},
            {"id": "patient_brief", "name": "Patient Brief", "description": "Generate pre-visit patient intelligence brief", "icon": "🏥"},
            {"id": "follow_up", "name": "Follow-Up", "description": "Create and manage patient follow-ups", "icon": "📞"},
            {"id": "guidelines", "name": "Clinical Guidelines", "description": "Look up condition-specific clinical guidelines", "icon": "📚"},
            {"id": "scheduling", "name": "Scheduling", "description": "Schedule labs, imaging, and referrals", "icon": "📅"},
            {"id": "risk_check", "name": "Risk Assessment", "description": "Review patient risk factors and alerts", "icon": "⚠️"},
        ],
    }


# ── Shadow Mode ────────────────────────────────────────────────────────

@app.post("/api/shadow-mode/compare", response_model=ShadowModeResponse)
async def shadow_mode_compare(request: ShadowModeRequest):
    """Compare the agent's intent detection with an expert's baseline"""
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        with tracer.start_as_current_span("shadow_mode_compare") as span:
            span.set_attribute("input.length", len(request.message))
            logger.info(f"Running shadow mode evaluation for: {request.message[:100]}")

            comparison = agent.shadow_mode_compare(request.message, request.expert_action)
            return ShadowModeResponse(**comparison, status="success")
    except Exception as e:
        logger.info(f"Error in shadow mode comparison: {e}")
        raise HTTPException(status_code=500, detail=f"Error in shadow mode: {str(e)}")


# ── Reset ────────────────────────────────────────────────────────────

@app.post("/api/reset")
async def reset_agent():
    """Reset the agent's memory"""
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        with tracer.start_as_current_span("reset_agent"):
            if agent.memory:
                agent.memory.clear_history()
                agent.memory.clear_patient_context()
                return {"status": "success", "message": "Agent memory and patient context cleared"}
            return {"status": "success", "message": "No memory to clear"}
    except Exception as e:
        logger.error(f"Error resetting agent: {e}")
        raise HTTPException(status_code=500, detail=f"Error resetting agent: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
