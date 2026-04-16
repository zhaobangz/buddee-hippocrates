from typing import Dict, Any, List
from datetime import datetime
from app.schemas import PatientIntelligence

class PatientService:
    def get_patient_summary(self, patient_id: str) -> PatientIntelligence:
        # Mock data for production structure demonstration
        return PatientIntelligence(
            patient_id=patient_id,
            name="John Doe",
            summary="65yo male with T2DM and Hypertension. Improving glycemic control.",
            key_conditions=["Type 2 Diabetes", "Hypertension", "Hyperparathyroidism"],
            last_updated=datetime.utcnow()
        )

    def get_patient_timeline(self, patient_id: str) -> List[Dict[str, Any]]:
        return [
            {"date": "2024-01-10", "event": "A1C Lab Result", "value": "7.2%"},
            {"date": "2024-02-15", "event": "Primary Care Visit", "note": "Stable"},
            {"date": "2024-03-20", "event": "Medication Refill", "med": "Metformin"}
        ]

patient_service = PatientService()
