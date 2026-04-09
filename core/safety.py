"""Safety & Audit Layer — HIPAA compliance foundation.

Provides action validation, human approval gating, and audit logging.
This is the critical safety layer that ensures the clinical agent:
  - Never crosses into diagnosis territory
  - Logs all actions for compliance
  - Gates sensitive actions behind human approval
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.config import Config
from core.storage import SecureStorage

storage = SecureStorage()


# ── PII/PHI Redaction Patterns ───────────────────────────────────────

PII_PATTERNS = {
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "DOB": r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    "ZIP": r"\b\d{5}(?:-\d{4})?\b",
}


def redact_pii(text: str) -> str:
    """Redact Personal Identifiable Information (PII) from text."""
    redacted = text
    for label, pattern in PII_PATTERNS.items():
        redacted = re.sub(pattern, f"[{label}_REDACTED]", redacted)
    return redacted


# ── Actions that require human approval ──────────────────────────────

APPROVAL_REQUIRED_ACTIONS = {
    "prior_auth_submit",
    "medication_change",
    "referral_create",
    "treatment_recommendation",
    "escalation",
}

# ── Actions that are NOT allowed (safety boundaries) ─────────────────

BLOCKED_ACTIONS = {
    "diagnosis",
    "prescribe_medication",
    "medical_advice_direct",
}

# ── Keywords that suggest the LLM is crossing into diagnosis ─────────

DIAGNOSIS_BOUNDARY_PHRASES = [
    "you have",
    "you are diagnosed with",
    "i diagnose",
    "my diagnosis is",
    "you are suffering from",
    "you should take",
    "take this medication",
    "i prescribe",
]


def validate_action(action_type: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate whether an action is safe to perform.

    Returns:
        dict with 'allowed' (bool), 'requires_approval' (bool),
        and optional 'reason' string.
    """
    action_lower = action_type.lower().strip()

    if action_lower in BLOCKED_ACTIONS:
        return {
            "allowed": False,
            "requires_approval": False,
            "reason": f"Action '{action_type}' is blocked. The system does not provide diagnoses or prescriptions.",
        }

    requires_approval = (
        Config.REQUIRE_HUMAN_APPROVAL
        and action_lower in APPROVAL_REQUIRED_ACTIONS
    )

    return {
        "allowed": True,
        "requires_approval": requires_approval,
        "reason": "Requires human approval before execution." if requires_approval else "Action permitted.",
    }


def request_human_approval(action_type: str, details: Dict[str, Any]) -> str:
    """Flag an action for human review and return a message for the user.

    In a production system this would send a notification and block
    until approved.  Here we return a formatted approval request.
    """
    log_audit_event("approval_requested", {
        "action_type": action_type,
        "details": details,
    })

    return (
        f"⚠ HUMAN APPROVAL REQUIRED\n"
        f"Action: {action_type}\n"
        f"Details: {json.dumps(details, indent=2)}\n\n"
        f"Please confirm this action before proceeding (yes/no)."
    )


def check_safety_boundaries(response: str) -> Dict[str, Any]:
    """Check if an LLM response crosses safety boundaries.

    Scans for phrases that suggest the model is providing direct
    medical diagnoses or prescriptions.

    Returns:
        dict with 'safe' (bool) and optional 'flagged_phrases' list.
    """
    if not Config.ENABLE_SAFETY_LAYER:
        return {"safe": True, "flagged_phrases": []}

    response_lower = response.lower()
    flagged = [p for p in DIAGNOSIS_BOUNDARY_PHRASES if p in response_lower]

    if flagged:
        log_audit_event("safety_boundary_triggered", {
            "flagged_phrases": flagged,
            "response_preview": response[:200],  # type: ignore
        })

    return {
        "safe": len(flagged) == 0,
        "flagged_phrases": flagged,
    }


def sanitize_response(response: str) -> str:
    """If a response fails safety boundaries, add a disclaimer.

    Does NOT block the response — just adds a clear disclaimer.
    """
    check = check_safety_boundaries(response)
    if not check["safe"]:
        disclaimer = (
            "\n\n⚠ IMPORTANT DISCLAIMER: This information is for clinical decision "
            "support only and does NOT constitute a medical diagnosis or prescription. "
            "All clinical decisions must be made by a licensed healthcare provider."
        )
        return response + disclaimer
    return response


# ── Audit Logging ─────────────────────────────────────────────────────

def log_audit_event(
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: str = "system",
    reasoning_chain: Optional[str] = None,
) -> None:
    """Write an audit event to the audit log file.

    Each event is a JSON object appended to a JSON-lines file.
    This provides the foundation for HIPAA compliance audit trails.
    """
    if not Config.ENABLE_AUDIT_LOG:
        return

    # Redact PII from details if they contain strings
    safe_details = {}
    if details:
        for k, v in details.items():
            if isinstance(v, str):
                safe_details[k] = redact_pii(v)
            else:
                safe_details[k] = v

    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "details": safe_details,
    }

    if reasoning_chain:
        event["reasoning_chain"] = redact_pii(reasoning_chain)

    try:
        storage.append_json(Config.AUDIT_LOG_FILE, event)
    except Exception as e:
        print(f"Error writing audit log: {e}")


def get_recent_audit_events(count: int = 20) -> List[Dict[str, Any]]:
    """Read the most recent audit events from the log file."""
    events: List[Dict[str, Any]] = []
    if not os.path.exists(Config.AUDIT_LOG_FILE):
        return events

    try:
        data = storage.load_json(Config.AUDIT_LOG_FILE)
        if isinstance(data, list):
             return data[-int(count):]
    except Exception:
        pass

    return events
