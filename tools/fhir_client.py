"""FHIR Client — Clinical Data Integration.

Standardized client for interacting with FHIR (Fast Healthcare Interoperability Resources) 
APIs to retrieve structured patient records and lab results.
"""

import requests
from typing import Dict, List, Any, Optional
from core.safety import log_audit_event

class FHIRClient:
    """Client for fetching data from a FHIR-compliant API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8001/fhir"):
        self.base_url = base_url.rstrip('/')

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Fetch Patient resource by ID."""
        url = f"{self.base_url}/Patient/{patient_id}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                log_audit_event("fhir_query_success", {"resource": "Patient", "id": patient_id})
                return response.json()
        except Exception as e:
            log_audit_event("fhir_query_error", {"resource": "Patient", "error": str(e)})
        return None

    def get_observations(self, patient_id: str) -> List[Dict[str, Any]]:
        """Fetch Observation resources for a patient."""
        url = f"{self.base_url}/Observation?patient=Patient/{patient_id}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                log_audit_event("fhir_query_success", {"resource": "Observation", "pid": patient_id})
                return response.json()
        except Exception as e:
            log_audit_event("fhir_query_error", {"resource": "Observation", "error": str(e)})
        return []

    def get_medications(self, patient_id: str) -> List[Dict[str, Any]]:
        """Fetch MedicationStatement resources for a patient."""
        url = f"{self.base_url}/MedicationStatement?patient=Patient/{patient_id}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                log_audit_event("fhir_query_success", {"resource": "MedicationStatement", "pid": patient_id})
                return response.json()
        except Exception as e:
            log_audit_event("fhir_query_error", {"resource": "MedicationStatement", "error": str(e)})
        return []

def get_fhir_client(base_url: Optional[str] = None) -> FHIRClient:
    return FHIRClient(base_url or "http://127.0.0.1:8001/fhir")
