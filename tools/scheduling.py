"""Scheduling & Workflow Orchestrator tool.

Coordinates labs, imaging, referrals, and other clinical tasks.
Acts as the "Medical Workflow Orchestrator" — a system-level agent
that tracks and closes loops across care activities.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

_SCHEDULE_STORE_FILE = "schedule_store.json"


def _load_store() -> Dict[str, Any]:
    if os.path.exists(_SCHEDULE_STORE_FILE):
        try:
            with open(_SCHEDULE_STORE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_store(store: Dict[str, Any]) -> None:
    try:
        with open(_SCHEDULE_STORE_FILE, "w") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"Error saving schedule store: {e}")


def _create_task(
    patient_id: str,
    task_type: str,
    description: str,
    details: Optional[Dict[str, Any]] = None,
    patient_name: str = "",
    provider_name: str = "",
    days_out: int = 7,
) -> Dict[str, Any]:
    """Internal helper to create a scheduled task."""
    task_id = f"TASK-{str(uuid.uuid4()).split('-')[0].upper()}"
    now = datetime.now()
    scheduled_date = (now + timedelta(days=days_out)).isoformat()

    task = {
        "task_id": task_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "provider_name": provider_name,
        "type": task_type,
        "description": description,
        "details": details or {},
        "status": "scheduled",
        "created_at": now.isoformat(),
        "scheduled_date": scheduled_date,
    }

    store = _load_store()
    store[task_id] = task
    _save_store(store)
    return task


def schedule_lab(
    patient_id: str,
    lab_type: str,
    reason: str = "",
    patient_name: str = "",
    provider_name: str = "",
    days_out: int = 3,
) -> Dict[str, Any]:
    """Schedule a lab test for a patient.

    Args:
        patient_id: Patient identifier.
        lab_type: Type of lab (e.g., 'CBC', 'CMP', 'HbA1c', 'Lipid Panel').
        reason: Clinical reason for the lab order.
        days_out: Days from now to schedule.
    """
    description = f"Lab Order: {lab_type}"
    if reason:
        description += f" — {reason}"
    return _create_task(
        patient_id, "lab", description,
        details={"lab_type": lab_type, "reason": reason},
        patient_name=patient_name, provider_name=provider_name,
        days_out=days_out,
    )


def schedule_imaging(
    patient_id: str,
    imaging_type: str,
    body_part: str = "",
    reason: str = "",
    patient_name: str = "",
    provider_name: str = "",
    days_out: int = 7,
) -> Dict[str, Any]:
    """Schedule an imaging study.

    Args:
        imaging_type: Type of imaging (e.g., 'X-ray', 'MRI', 'CT', 'Ultrasound').
        body_part: Body part being imaged.
    """
    description = f"Imaging: {imaging_type}"
    if body_part:
        description += f" — {body_part}"
    if reason:
        description += f" ({reason})"
    return _create_task(
        patient_id, "imaging", description,
        details={"imaging_type": imaging_type, "body_part": body_part, "reason": reason},
        patient_name=patient_name, provider_name=provider_name,
        days_out=days_out,
    )


def create_referral(
    patient_id: str,
    specialist_type: str,
    reason: str = "",
    urgency: str = "routine",
    patient_name: str = "",
    provider_name: str = "",
    days_out: int = 14,
) -> Dict[str, Any]:
    """Create a referral to a specialist.

    Args:
        specialist_type: Type of specialist (e.g., 'Cardiology', 'Endocrinology').
        urgency: 'routine', 'urgent', or 'emergent'.
    """
    description = f"Referral to {specialist_type}"
    if reason:
        description += f" — {reason}"
    return _create_task(
        patient_id, "referral", description,
        details={"specialist_type": specialist_type, "reason": reason, "urgency": urgency},
        patient_name=patient_name, provider_name=provider_name,
        days_out=days_out,
    )


def get_pending_tasks(patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all pending/scheduled tasks, optionally filtered by patient.

    Returns tasks sorted by scheduled date (soonest first).
    """
    store = _load_store()
    results = list(store.values())
    if patient_id:
        results = [r for r in results if r.get("patient_id") == patient_id]
    results = [r for r in results if r.get("status") in ("scheduled", "in_progress")]
    return sorted(results, key=lambda r: r.get("scheduled_date", ""))


def complete_task(task_id: str, notes: str = "") -> Dict[str, Any]:
    """Mark a task as completed.

    Args:
        task_id: The task identifier.
        notes: Optional completion notes.
    """
    store = _load_store()
    if task_id not in store:
        return {"error": f"Task ID '{task_id}' not found."}
    store[task_id]["status"] = "completed"
    store[task_id]["completed_at"] = datetime.now().isoformat()
    if notes:
        store[task_id]["completion_notes"] = notes
    _save_store(store)
    return store[task_id]


def format_task_summary(tasks: List[Dict[str, Any]]) -> str:
    """Format a list of tasks as a human-readable summary."""
    if not tasks:
        return "No pending tasks."

    lines = [
        "=" * 50,
        f"  WORKFLOW TASKS ({len(tasks)} pending)",
        "=" * 50,
    ]
    type_icons = {
        "lab": "🔬",
        "imaging": "📷",
        "referral": "👨‍⚕️",
    }
    for t in tasks:
        icon = type_icons.get(t.get("type", ""), "📋")
        lines.append(f"\n  {icon} {t.get('task_id')} — {t.get('description', 'Task')}")
        lines.append(f"     Patient: {t.get('patient_name', t.get('patient_id', 'N/A'))}")
        lines.append(f"     Scheduled: {t.get('scheduled_date', 'N/A')}")
        lines.append(f"     Status: {t.get('status', 'unknown')}")
        if t.get("type") == "referral":
            urgency = t.get("details", {}).get("urgency", "routine")
            if urgency != "routine":
                lines.append(f"     ⚠ Urgency: {urgency.upper()}")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)
