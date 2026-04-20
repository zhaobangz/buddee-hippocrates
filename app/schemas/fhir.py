from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any

class FHIRResource(BaseModel):
    model_config = ConfigDict(extra='allow')
    resourceType: str
    id: Optional[str] = None

class FHIRBundleEntry(BaseModel):
    model_config = ConfigDict(extra='allow')
    resource: Dict[str, Any]

class FHIRBundle(BaseModel):
    model_config = ConfigDict(extra='allow')
    resourceType: str = "Bundle"
    type: str = "transaction"
    entry: List[FHIRBundleEntry]
