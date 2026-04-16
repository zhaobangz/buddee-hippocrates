from fastapi import APIRouter
from app.services.audit_service import audit_service

router = APIRouter()

@router.get("/")
async def get_audit_trail(limit: int = 50):
    return audit_service.get_recent_events(limit)
