"""Patient Follow-Up Automation tool.

Creates, tracks, and processes patient follow-ups.  Supports automated
adherence checks, symptom follow-ups, and escalation when risk is detected.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

_FOLLOW_UP_STORE_FILE = "follow_up_store.json"


def _load_store() -> Dict[str, Any]:
    if os.path.exists(_FOLLOW_UP_STORE_FILE):
        try:
            with open(_FOLLOW_UP_STORE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_store(store: Dict[str, Any]) -> None:
    try:
        with open(_FOLLOW_UP_STORE_FILE, "w") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"Error saving follow-up store: {e}")


# ── Follow-Up Types ───────────────────────────────────────────────────

FOLLOW_UP_TYPES = {
    "symptom_check": {
        "label": "Symptom Check",
        "default_message": "How are your symptoms? Have they improved, stayed the same, or worsened?",
        "default_days": 3,
    },
    "medication_adherence": {
        "label": "Medication Adherence",
        "default_message": "Are you taking your medications as prescribed? Any side effects?",
        "default_days": 7,
    },
    "lab_results": {
        "label": "Lab Results Review",
        "default_message": "Your lab results are ready for review. Please schedule a follow-up appointment.",
        "default_days": 5,
    },
    "post_procedure": {
        "label": "Post-Procedure Check",
        "default_message": "How are you feeling after your procedure? Any pain, swelling, or unusual symptoms?",
        "default_days": 1,
    },
    "general": {
        "label": "General Follow-Up",
        "default_message": "This is a follow-up from your recent visit. How are you doing?",
        "default_days": 14,
    },
}


def create_follow_up(
    patient_id: str,
    reason: str = "general",
    custom_message: str = "",
    days_until_due: Optional[int] = None,
    patient_name: str = "",
    provider_name: str = "",
) -> Dict[str, Any]:
    """Create a new follow-up task for a patient.

    Args:
        patient_id: Patient identifier.
        reason: Follow-up type (see FOLLOW_UP_TYPES).
        custom_message: Override the default follow-up message.
        days_until_due: Days from now until follow-up is due.
        patient_name: Patient name for display.
        provider_name: Ordering provider name.

    Returns:
        The created follow-up record.
    """
    fu_type = FOLLOW_UP_TYPES.get(reason, FOLLOW_UP_TYPES["general"])
    fu_id = f"FU-{str(uuid.uuid4()).split('-')[0].upper()}"
    now = datetime.now()
    days = days_until_due if days_until_due is not None else fu_type["default_days"]
    due_date = (now + timedelta(days=float(days))).isoformat()

    record = {
        "follow_up_id": fu_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "provider_name": provider_name,
        "type": reason,
        "type_label": fu_type["label"],
        "message": custom_message or fu_type["default_message"],
        "status": "pending",
        "created_at": now.isoformat(),
        "due_date": due_date,
        "responses": [],
        "escalated": False,
    }

    store = _load_store()
    store[fu_id] = record
    _save_store(store)
    return record


def check_follow_ups(patient_id: Optional[str] = None, status: str = "all") -> List[Dict[str, Any]]:
    """List follow-ups, optionally filtered by patient and/or status.

    Args:
        patient_id: If provided, filter to this patient only.
        status: 'pending', 'completed', 'escalated', or 'all'.
    """
    store = _load_store()
    results = list(store.values())

    if patient_id:
        results = [r for r in results if r.get("patient_id") == patient_id]
    if status != "all":
        results = [r for r in results if r.get("status") == status]

    return sorted(results, key=lambda r: r.get("due_date", ""), reverse=True)


def process_follow_up_response(
    follow_up_id: str,
    response: str,
    risk_detected: bool = False,
) -> Dict[str, Any]:
    """Process a patient's response to a follow-up.

    Args:
        follow_up_id: The follow-up identifier.
        response: The patient's response text.
        risk_detected: If True, escalate the follow-up.

    Returns:
        Updated follow-up record.
    """
    store = _load_store()
    if follow_up_id not in store:
        return {"error": f"Follow-up ID '{follow_up_id}' not found."}

    record = store[follow_up_id]
    record["responses"].append({
        "text": response,
        "timestamp": datetime.now().isoformat(),
        "risk_detected": risk_detected,
    })

    if risk_detected:
        record["status"] = "escalated"
        record["escalated"] = True
        record["escalation_reason"] = f"Risk detected in patient response: {response[:100]}"  # type: ignore
    else:
        record["status"] = "completed"

    record["updated_at"] = datetime.now().isoformat()
    store[follow_up_id] = record
    _save_store(store)
    return record


def get_overdue_follow_ups() -> List[Dict[str, Any]]:
    """Return all pending follow-ups that are past their due date."""
    store = _load_store()
    now = datetime.now().isoformat()
    return [
        r for r in store.values()
        if r.get("status") == "pending" and r.get("due_date", "9999") < now
    ]


def format_follow_up_summary(records: List[Dict[str, Any]]) -> str:
    """Format a list of follow-up records as a human-readable summary."""
    if not records:
        return "No follow-ups found."

    lines = [
        "=" * 50,
        f"  FOLLOW-UP SUMMARY ({len(records)} records)",
        "=" * 50,
    ]
    for r in records:
        status_icon = {"pending": "⏳", "completed": "✅", "escalated": "🚨"}.get(r.get("status", ""), "❓")
        lines.append(f"\n  {status_icon} {r.get('follow_up_id')} — {r.get('type_label', 'Follow-Up')}")
        lines.append(f"     Patient: {r.get('patient_name', r.get('patient_id', 'N/A'))}")
        lines.append(f"     Due: {r.get('due_date', 'N/A')}")
        lines.append(f"     Status: {r.get('status', 'unknown')}")
        if r.get("escalated"):
            lines.append(f"     ⚠ ESCALATED: {r.get('escalation_reason', '')}")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)
