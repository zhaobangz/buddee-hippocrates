import json
import os
from datetime import datetime
from typing import List, Dict, Any
from app.schemas import AuditEvent
from app.core.config import settings

class AuditService:
    def __init__(self):
        self.log_path = settings.SAFETY_LOG_PATH
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def log_event(self, action: str, metadata: Dict[str, Any], risk_level: str = "low"):
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "metadata": metadata,
            "risk_level": risk_level
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path, "r") as f:
            lines = f.readlines()
            return [json.loads(l) for l in lines[-limit:]]

audit_service = AuditService()
