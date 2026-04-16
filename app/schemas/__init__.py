from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- Chat ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    patient_id: Optional[str] = None
    stream: bool = False

class ChatResponse(BaseModel):
    response: str
    citations: List[str] = []
    confidence_score: float = 1.0
    intent_detected: str

# --- Patient ---
class PatientIntelligence(BaseModel):
    patient_id: str
    name: str
    summary: str
    key_conditions: List[str]
    last_updated: datetime

# --- Risk ---
class RiskScore(BaseModel):
    label: str
    value: float  # 0 to 1
    tier: str  # low, medium, high
    trend: str  # improving, stable, worsening

class RiskDashboard(BaseModel):
    patient_id: str
    scores: List[RiskScore]
    missing_labs: List[str]
    next_best_action: str

# --- Workflow ---
class PriorAuthRequest(BaseModel):
    patient_id: str
    procedure_code: str
    diagnosis_code: str
    clinical_notes: str

class PriorAuthResponse(BaseModel):
    auth_id: str
    status: str
    generated_letter: str
    requires_review: bool

class ScheduleRequest(BaseModel):
    patient_id: str
    preferred_window: str
    reason: str

# --- Audit ---
class AuditEvent(BaseModel):
    event_id: str
    action: str
    user_id: str
    timestamp: datetime
    metadata: Dict[str, Any]
    risk_level: str
