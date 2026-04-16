from fastapi import APIRouter
from app.schemas import RiskDashboard
from app.services.risk_service import risk_service

router = APIRouter()

@router.get("/{patient_id}", response_model=RiskDashboard)
async def get_risk_dashboard(patient_id: str):
    return risk_service.calculate_risk_scores(patient_id)
