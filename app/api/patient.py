from fastapi import APIRouter
from app.schemas import PatientIntelligence
from app.services.patient_service import patient_service

router = APIRouter()

@router.get("/{patient_id}", response_model=PatientIntelligence)
async def get_patient_detail(patient_id: str):
    return patient_service.get_patient_summary(patient_id)

@router.get("/{patient_id}/timeline")
async def get_patient_timeline(patient_id: str):
    return patient_service.get_patient_timeline(patient_id)
