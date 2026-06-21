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
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Model confidence 0–1.")
    review_status: str = Field(default="human_review_required")


class ShadowModeResponse(BaseModel):
    recovered_revenue: float = Field(..., description="Sum of all est_value fields.")
    identified_codes: List[IdentifiedCode]
    summary: str = Field(..., description="Executive summary for the compliance officer.")
    audit_hash: Optional[str] = None
    citations: List[str] = Field(default_factory=list, description="Guideline chunk IDs or source labels used in this audit.")


# ── LLM-as-judge verdict (manual §7.2 Risk #2 mitigation #4) ─────────
#
# A second, independent LLM call adjudicates each first-pass HCC suggestion
# whose confidence sits in the "uncertain band" (>= floor, < judge threshold).
# Only a "yes" survives — a hallucinated code that a hurried coder might
# approve is dropped before it ever reaches the operator UI. Verdicts are
# recorded in the audit chain so the abstain/rejection rate is queryable
# per tenant (manual §6.2 Quality signal).

class JudgeVerdict(BaseModel):
    code: str = Field(..., description="The candidate ICD-10 / HCC code under review.")
    verdict: Literal["yes", "no", "abstain"] = Field(
        ...,
        description=(
            "'yes' only if the clinical note clearly documents the condition "
            "and the cited evidence quote supports the code per ICD-10/HCC "
            "documentation standards; 'no' if unsupported; 'abstain' if the "
            "evidence is too ambiguous to decide."
        ),
    )
    rationale: str = Field(
        default="",
        description="One-sentence justification for the verdict (no PHI beyond the evidence already cited).",
    )


# ── Prior-authorization draft (deliverable 4.5) ──────────────────────

class EvidenceSnippet(BaseModel):
    quote: str = Field(..., description="Verbatim short quote from the clinical context that supports medical necessity.")
    source: str = Field(default="clinical_note", description="Where this evidence came from: clinical_note, guideline, lab, etc.")


class PriorAuthDraft(BaseModel):
    """Structured prior-authorization draft returned by the agent.

    The ``draft_letter`` is a payer-ready free-text artifact a human reviewer
    can copy/paste; the structured fields exist so the operator UI can render
    a checklist + evidence trail next to it without re-parsing prose.
    """

    draft_letter: str = Field(..., description="Full draft prior-auth letter ready for human review.")
    supporting_codes: List[str] = Field(default_factory=list, description="ICD-10 / CPT codes that justify medical necessity.")
    payer_rationale: str = Field(..., description="Plain-language summary of why this should be approved under the payer's policy.")
    evidence_snippets: List[EvidenceSnippet] = Field(default_factory=list, description="Quotes from the clinical record supporting necessity.")
    missing_information: List[str] = Field(default_factory=list, description="Items a clinician must add before submission.")



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
