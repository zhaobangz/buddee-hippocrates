import logging
import uuid
import datetime
from sqlalchemy.orm import Session
from core.database import SessionLocal
from core.models import RecoveryEvent

logger = logging.getLogger(__name__)

def log_financial_recovery(audit_hash: str, pt_id: str, amount: float):
    """Binds the shadow-mode recovery event to the cryptographic audit trail."""
    db: Session = SessionLocal()
    try:
        event = RecoveryEvent(
            id=str(uuid.uuid4()),
            audit_hash=audit_hash,
            patient_id=pt_id,
            recovered_revenue=amount,
            timestamp=datetime.datetime.utcnow()
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        logger.info(f"Logged RecoveryEvent: {event.id} with revenue ${amount}")
        return event
    except Exception as e:
        logger.error(f"Failed to log recovery: {e}")
        db.rollback()
    finally:
        db.close()
