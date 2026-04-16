"""
EHR Reader — Intelligence Module
Parses patient records and identifies clinical focus areas.
"""
from typing import Dict, List, Any

def parse_patient_record(raw_data: str) -> Dict[str, Any]:
    """Placeholder for complex EHR parsing logic."""
    return {
        "name": "Extracted Patient",
        "conditions": ["Sample Condition"],
        "medications": ["Sample Med"]
    }

def generate_patient_brief(ctx: Dict[str, Any]) -> str:
    """Generates a high-density intelligence brief for clinicians."""
    if not ctx:
        return "No patient context available."
        
    name = ctx.get("name", "Unknown")
    conditions = ctx.get("conditions", [])
    meds = ctx.get("medications", [])
    
    brief = [
        f"🏥 CLINICAL INTELLIGENCE BRIEF: {name.upper()}",
        f"Status: Active Case | Patient ID: {ctx.get('patient_id', 'AUTO')}",
        "-" * 40,
        "🩺 ACTIVE DIAGNOSES:",
    ]
    
    if conditions:
        brief.extend([f"  - {c}" for c in conditions])
    else:
        brief.append("  - None reported")
        
    brief.append("")
    brief.append("💊 ACTIVE REGIMEN:")
    
    if meds:
        brief.extend([f"  - {m}" for m in meds])
    else:
        brief.append("  - No medications on file")
        
    brief.append("")
    brief.append("⚠️ AI-DETECTED FOCUS AREAS:")
    brief.extend(_identify_risks(conditions, meds))
    
    brief.extend([
        "-" * 40,
        "💡 SUGGESTED CLINICAL QUESTIONS:",
        "  1. Assess adherence to current regimen.",
        "  2. Review recent A1C/BP trends.",
        "  3. Screen for secondary complications related to current diagnoses."
    ])
    
    return "\n".join(brief)

def _identify_risks(conditions: List[str], meds: List[str]) -> List[str]:
    """Internal logic to identify severity/risk patterns."""
    risks = []
    lower_conds = [c.lower() for c in conditions]
    lower_meds = [m.lower() for m in meds]
    
    if "diabetes" in lower_conds:
        risks.append("  - [HIGH] Glycemic Control: Requires A1C review (Target <7.0%)")
        if not any("metformin" in m for m in lower_meds):
            risks.append("  - [MED] Protocol Variance: Metformin not found in active regimen.")
            
    if "hypertension" in lower_conds:
        risks.append("  - [MED] BP Surveillance: Monitor for Stage 2 escalation.")
        
    if not risks:
        risks.append("  - Low acute risk detected. Maintain standard follow-up.")
        
    return risks
