from pydantic import BaseModel, Field
from typing import List

class IdentifiedCode(BaseModel):
    code: str = Field(..., description="The exact ICD-10 or CPT code.")
    description: str = Field(..., description="Official code description.")
    justification: str = Field(..., description="Verbatim quote from the clinical note justifying this code.")
    est_value: float = Field(..., description="Estimated dollar value recovered based on RVU/weight.")

class ShadowModeResponse(BaseModel):
    recovered_revenue: float = Field(..., description="Sum of all est_value fields.")
    identified_codes: List[IdentifiedCode]
    summary: str = Field(..., description="Executive summary for the compliance officer.")
