"""Financial recovery ledger bound to the cryptographic audit trail.

Re-audit (April 21) follow-ups applied here:
  * CQ-04 — ``datetime.utcnow()`` replaced with
    ``datetime.now(datetime.timezone.utc)``.
  * DB-05 — ``RecoveryEvent.id`` now holds a real ``uuid.UUID`` (see
    ``core.models``). The caller no longer has to stringify the value.
"""

from __future__ import annotations

import datetime
import logging
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.database import SessionLocal
from core.models import RecoveryEvent

logger = logging.getLogger(__name__)


def log_financial_recovery(audit_hash: str, pt_id: str, amount: float) -> RecoveryEvent | None:
    """Append a RecoveryEvent row, bound to the cryptographic audit hash.

    Returns the persisted row on success, or ``None`` if the write failed
    (a non-fatal state — the LLM pipeline keeps running and the audit
    trail still holds the corresponding event).
    """
    db: Session = SessionLocal()
    try:
        event = RecoveryEvent(
            id=uuid.uuid4(),
            audit_hash=audit_hash,
            patient_id=pt_id,
            recovered_revenue=amount,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        logger.info("Logged RecoveryEvent: %s with revenue $%s", event.id, amount)
        return event
    except SQLAlchemyError as e:
        logger.error("Failed to log recovery: %s", e)
        db.rollback()
        return None
    finally:
        db.close()
