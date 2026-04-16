from fastapi import APIRouter, Depends
from app.schemas import ChatRequest, ChatResponse
from app.agents.orchestrator import orchestrator
from app.services.audit_service import audit_service

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def clinical_chat(request: ChatRequest):
    # Retrieve context if patient_id provided
    context = None
    if request.patient_id:
        from app.services.patient_service import patient_service
        context = patient_service.get_patient_summary(request.patient_id).dict()

    result = await orchestrator.execute(request.message, patient_context=context)
    
    # Audit log the interaction
    audit_service.log_event(
        action="clinical_chat",
        metadata={"message_len": len(request.message), "intent": result["intent_detected"]},
        risk_level="low"
    )
    
    return result
