"""FHIR Client — Clinical Data Integration.

Standardized client for interacting with FHIR (Fast Healthcare Interoperability Resources) 
APIs to retrieve structured patient records and lab results.
"""

import os
from urllib.parse import urlparse

import httpx
from typing import Dict, List, Any, Optional
from core.safety import log_audit_event

MAX_FHIR_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_FHIR_HOSTS: frozenset[str] = frozenset(
    h.strip()
    for h in os.getenv("ALLOWED_FHIR_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
)


def _validate_fhir_url(url: str) -> str:
    parsed = urlparse(url)
    # Security: restrict outbound FHIR calls to an explicit host allowlist to prevent SSRF.
    if parsed.hostname not in _ALLOWED_FHIR_HOSTS:
        raise ValueError(
            f"FHIR base URL host '{parsed.hostname}' is not in ALLOWED_FHIR_HOSTS. "
            "Set ALLOWED_FHIR_HOSTS to include the FHIR server hostname."
        )
    return url


def _check_response_size(response: httpx.Response) -> None:
    # Security: reject oversized FHIR payloads before parsing JSON into memory-heavy objects.
    if int(response.headers.get("content-length", 0)) > MAX_FHIR_RESPONSE_BYTES:
        raise ValueError("FHIR response exceeds size limit")

class FHIRClient:
    """Client for fetching data from a FHIR-compliant API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8001/fhir"):
        self.base_url = _validate_fhir_url(base_url).rstrip('/')

    async def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Fetch Patient resource by ID."""
        url = f"{self.base_url}/Patient/{patient_id}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
            _check_response_size(response)
            if response.status_code == 200:
                log_audit_event("fhir_query_success", {"resource": "Patient", "id": patient_id})
                return response.json()
        except Exception as e:
            log_audit_event("fhir_query_error", {"resource": "Patient", "error": str(e)})
        return None

    async def get_observations(self, patient_id: str) -> List[Dict[str, Any]]:
        """Fetch Observation resources for a patient."""
        url = f"{self.base_url}/Observation?patient=Patient/{patient_id}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
            _check_response_size(response)
            if response.status_code == 200:
                log_audit_event("fhir_query_success", {"resource": "Observation", "pid": patient_id})
                return response.json()
        except Exception as e:
            log_audit_event("fhir_query_error", {"resource": "Observation", "error": str(e)})
        return []

    async def get_medications(self, patient_id: str) -> List[Dict[str, Any]]:
        """Fetch MedicationStatement resources for a patient."""
        url = f"{self.base_url}/MedicationStatement?patient=Patient/{patient_id}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
            _check_response_size(response)
            if response.status_code == 200:
                log_audit_event("fhir_query_success", {"resource": "MedicationStatement", "pid": patient_id})
                return response.json()
        except Exception as e:
            log_audit_event("fhir_query_error", {"resource": "MedicationStatement", "error": str(e)})
        return []

def get_fhir_client(base_url: Optional[str] = None) -> FHIRClient:
    return FHIRClient(base_url or "http://127.0.0.1:8001/fhir")
