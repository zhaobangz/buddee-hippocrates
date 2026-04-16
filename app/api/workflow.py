from fastapi import APIRouter
from app.schemas import PriorAuthRequest, PriorAuthResponse, ScheduleRequest
from app.services.workflow_service import workflow_service
from app.services.audit_service import audit_service

router = APIRouter()

@router.post("/prior-auth", response_model=PriorAuthResponse)
async def create_prior_auth(request: PriorAuthRequest):
    result = await workflow_service.generate_prior_auth(request)
    
    audit_service.log_event(
        action="prior_auth_generation",
        metadata={"patient_id": request.patient_id, "procedure": request.procedure_code},
        risk_level="high" # Requires human-in-the-loop
    )
    
    return result

@router.post("/schedule")
async def schedule_visit(request: ScheduleRequest):
    return workflow_service.coordinate_scheduling(request.patient_id, request.reason)
