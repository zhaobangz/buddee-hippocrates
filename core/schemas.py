"""Shared Pydantic schemas for Buddi core.

Includes minimal FHIR R4 Bundle validation (SEC-10) — we don't try to validate
every FHIR nuance, only the structural invariants we actually depend on, plus
a hard size limit to prevent DoS and prompt-injection payload bombs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── RCM response models ──────────────────────────────────────────────

class IdentifiedCode(BaseModel):
    code: str = Field(..., description="The exact ICD-10 or CPT code.")
    description: str = Field(..., description="Official code description.")
    justification: str = Field(..., description="Verbatim quote from the clinical note justifying this code.")
    est_value: float = Field(..., description="Estimated dollar value recovered based on RVU/weight.")


class ShadowModeResponse(BaseModel):
    recovered_revenue: float = Field(..., description="Sum of all est_value fields.")
    identified_codes: List[IdentifiedCode]
    summary: str = Field(..., description="Executive summary for the compliance officer.")


# ── FHIR ingest (SEC-10) ─────────────────────────────────────────────

#: Maximum raw size of a FHIR bundle we will accept in a single request.
#: 2 MiB is comfortably larger than any realistic encounter bundle and small
#: enough to prevent denial-of-service via oversized JSON.
MAX_FHIR_BUNDLE_BYTES = 2 * 1024 * 1024


class FHIRBundleEntry(BaseModel):
    """A single entry in a FHIR Bundle.

    We only require that each entry carries a ``resource`` object with a
    ``resourceType`` discriminator. Everything else is passed through.
    """

    resource: Dict[str, Any]

    @field_validator("resource")
    @classmethod
    def _require_resource_type(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("entry.resource must be an object")
        if "resourceType" not in v or not isinstance(v["resourceType"], str):
            raise ValueError("entry.resource.resourceType is required and must be a string")
        return v


class FHIRBundle(BaseModel):
    """Structural validator for an inbound FHIR Bundle.

    Mirrors FHIR R4 ``Bundle`` only enough to reject obvious abuse:
      * ``resourceType`` must literally be "Bundle".
      * ``type`` is required (collection, transaction, document, …).
      * ``entry`` is an optional list of entries, each with a resource.
    """

    resourceType: Literal["Bundle"]
    type: str = Field(..., min_length=1, max_length=64)
    entry: Optional[List[FHIRBundleEntry]] = None
    id: Optional[str] = Field(default=None, max_length=128)

    model_config = {"extra": "allow"}
