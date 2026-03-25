"""Prior Authorization Automation tool — the MVP wedge.

Generates prior authorization forms, tracks approval status, and provides
insurance-specific field requirements.  This is a mock/structured
implementation designed for future integration with real insurance APIs.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

# In-memory store for prior auth requests (persisted to disk)
_PRIOR_AUTH_STORE_FILE = "prior_auth_store.json"


def _load_store() -> Dict[str, Any]:
    if os.path.exists(_PRIOR_AUTH_STORE_FILE):
        try:
            with open(_PRIOR_AUTH_STORE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_store(store: Dict[str, Any]) -> None:
    try:
        with open(_PRIOR_AUTH_STORE_FILE, "w") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"Error saving prior auth store: {e}")


# ── Insurance field requirements ──────────────────────────────────────

INSURANCE_FIELDS: Dict[str, List[str]] = {
    "default": [
        "patient_name",
        "patient_id",
        "date_of_birth",
        "insurance_id",
        "diagnosis_code",
        "treatment_requested",
        "treating_physician",
        "physician_npi",
        "clinical_justification",
    ],
    "medicare": [
        "patient_name",
        "patient_id",
        "date_of_birth",
        "medicare_id",
        "diagnosis_code",
        "treatment_requested",
        "treating_physician",
        "physician_npi",
        "clinical_justification",
        "medical_necessity_statement",
        "prior_treatments_tried",
    ],
    "medicaid": [
        "patient_name",
        "patient_id",
        "date_of_birth",
        "medicaid_id",
        "diagnosis_code",
        "treatment_requested",
        "treating_physician",
        "physician_npi",
        "clinical_justification",
        "service_location",
    ],
    "commercial": [
        "patient_name",
        "patient_id",
        "date_of_birth",
        "insurance_id",
        "group_number",
        "diagnosis_code",
        "treatment_requested",
        "treating_physician",
        "physician_npi",
        "clinical_justification",
        "estimated_cost",
    ],
}


def get_required_fields(insurance_type: str = "default") -> List[str]:
    """Return the list of fields required for a prior auth form.

    Args:
        insurance_type: One of 'default', 'medicare', 'medicaid', 'commercial'.
    """
    return INSURANCE_FIELDS.get(insurance_type.lower(), INSURANCE_FIELDS["default"])


def generate_prior_auth_form(
    patient_data: Dict[str, Any],
    treatment: str,
    diagnosis: str,
    insurance_type: str = "default",
    physician_name: str = "",
    physician_npi: str = "",
    clinical_justification: str = "",
) -> Dict[str, Any]:
    """Generate a completed prior authorization form.

    Returns a dict representing the filled form and stores it for tracking.
    """
    auth_id = f"PA-{str(uuid.uuid4()).split('-')[0].upper()}"
    now = datetime.now().isoformat()

    form = {
        "auth_id": auth_id,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "insurance_type": insurance_type,
        "patient_name": patient_data.get("patient_name", "Unknown"),
        "patient_id": patient_data.get("patient_id", "N/A"),
        "date_of_birth": patient_data.get("date_of_birth", "N/A"),
        "insurance_id": patient_data.get("insurance_id", "N/A"),
        "diagnosis_code": diagnosis,
        "treatment_requested": treatment,
        "treating_physician": physician_name,
        "physician_npi": physician_npi,
        "clinical_justification": clinical_justification or _auto_justification(diagnosis, treatment),
        "required_fields": get_required_fields(insurance_type),
    }

    # Add insurance-specific fields
    if insurance_type.lower() == "medicare":
        form["medical_necessity_statement"] = (
            f"Patient requires {treatment} for management of {diagnosis}. "
            "Prior conservative treatments have been insufficient."
        )
        form["prior_treatments_tried"] = patient_data.get("prior_treatments", "See clinical notes")

    # Persist
    store = _load_store()
    store[auth_id] = form
    _save_store(store)

    return form


def check_auth_status(auth_id: str) -> Dict[str, Any]:
    """Check the status of a prior authorization request.

    Returns the full form dict with current status.
    """
    store = _load_store()
    if auth_id in store:
        return store[auth_id]
    return {"error": f"Prior auth ID '{auth_id}' not found."}


def list_pending_auths() -> List[Dict[str, Any]]:
    """List all pending prior authorization requests."""
    store = _load_store()
    return [v for v in store.values() if v.get("status") == "pending"]


def update_auth_status(auth_id: str, new_status: str, notes: str = "") -> Dict[str, Any]:
    """Update the status of a prior auth request.

    Args:
        auth_id: The PA identifier.
        new_status: One of 'approved', 'denied', 'pending', 'info_requested'.
        notes: Optional notes about the status change.
    """
    store = _load_store()
    if auth_id not in store:
        return {"error": f"Prior auth ID '{auth_id}' not found."}

    store[auth_id]["status"] = new_status
    store[auth_id]["updated_at"] = datetime.now().isoformat()
    if notes:
        store[auth_id]["status_notes"] = notes
    _save_store(store)
    return store[auth_id]


def format_prior_auth_summary(form: Dict[str, Any]) -> str:
    """Return a human-readable summary of a prior auth form."""
    lines = [
        "=" * 50,
        "  PRIOR AUTHORIZATION FORM",
        "=" * 50,
        f"  Auth ID:     {form.get('auth_id', 'N/A')}",
        f"  Status:      {form.get('status', 'unknown').upper()}",
        f"  Created:     {form.get('created_at', 'N/A')}",
        "-" * 50,
        f"  Patient:     {form.get('patient_name', 'N/A')} (ID: {form.get('patient_id', 'N/A')})",
        f"  Insurance:   {form.get('insurance_type', 'N/A').title()} — {form.get('insurance_id', 'N/A')}",
        f"  Diagnosis:   {form.get('diagnosis_code', 'N/A')}",
        f"  Treatment:   {form.get('treatment_requested', 'N/A')}",
        f"  Physician:   {form.get('treating_physician', 'N/A')} (NPI: {form.get('physician_npi', 'N/A')})",
        "-" * 50,
        f"  Justification: {form.get('clinical_justification', 'N/A')}",
        "=" * 50,
    ]
    return "\n".join(lines)


def _auto_justification(diagnosis: str, treatment: str) -> str:
    """Generate a basic clinical justification string."""
    return (
        f"Patient presents with {diagnosis}. "
        f"Requesting authorization for {treatment} based on current clinical guidelines. "
        "Conservative management options have been considered."
    )
