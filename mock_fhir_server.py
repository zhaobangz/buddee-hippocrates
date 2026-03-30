"""Mock FHIR Server — Standardized Clinical Data Exchange.

FastAPI-powered mock server providing FHIR (Fast Healthcare Interoperability Resources) 
resources for testing Epic/Cerner-style integrations.
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, List, Any
import uvicorn
import uuid
from datetime import datetime

app = FastAPI(title="Buddi Mock FHIR Server", version="4.0.1")

# ── Mock Data ────────────────────────────────────────────────────────

MOCK_PATIENTS = {
    "12345": {
        "resourceType": "Patient",
        "id": "12345",
        "name": [{"use": "official", "family": "Smith", "given": ["John"]}],
        "gender": "male",
        "birthDate": "1978-05-12",
        "telecom": [{"system": "phone", "value": "555-1212", "use": "home"}],
    }
}

MOCK_OBSERVATIONS = {
    "12345": [
        {
            "resourceType": "Observation",
            "id": "lab1",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "HbA1c"}]},
            "subject": {"reference": "Patient/12345"},
            "effectiveDateTime": "2026-01-15T09:00:00Z",
            "valueQuantity": {"value": 7.2, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"}
        },
        {
            "resourceType": "Observation",
            "id": "lab2",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "HbA1c"}]},
            "subject": {"reference": "Patient/12345"},
            "effectiveDateTime": "2026-03-20T10:00:00Z",
            "valueQuantity": {"value": 7.7, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"}
        }
    ]
}

MOCK_MEDICATIONS = {
    "12345": [
        {
            "resourceType": "MedicationStatement",
            "id": "med1",
            "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "860975", "display": "Metformin 1000mg"}]},
            "subject": {"reference": "Patient/12345"},
            "dateAsserted": "2025-12-01T12:00:00Z"
        }
    ]
}

# ── Endpoints ────────────────────────────────────────────────────────

@app.get("/fhir/Patient/{patient_id}")
async def get_patient(patient_id: str):
    if patient_id not in MOCK_PATIENTS:
        raise HTTPException(status_code=404, detail="Patient not found")
    return MOCK_PATIENTS[patient_id]

@app.get("/fhir/Observation")
async def list_observations(patient: str):
    pid = patient.split("/")[-1]
    return MOCK_OBSERVATIONS.get(pid, [])

@app.get("/fhir/MedicationStatement")
async def list_medications(patient: str):
    pid = patient.split("/")[-1]
    return MOCK_MEDICATIONS.get(pid, [])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
