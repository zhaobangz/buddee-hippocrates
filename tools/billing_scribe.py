"""Billing Scribe — Clinical-to-Code Mapping.

Suggests ICD-10 (diagnosis) and CPT (procedure) codes based on 
patient briefs or visit notes to ensure accurate revenue cycle management.
"""

from typing import List, Dict, Any
import json
from core.llm_manager import LLMManager

llm = LLMManager()

def suggest_billing_codes(clinical_text: str) -> Dict[str, List[Dict[str, str]]]:
    """Suggest ICD-10 and CPT codes based on clinical documentation."""
    
    prompt = f"""
System: You are a medical billing and coding expert (CPC/CCS certified).
Task: Map the following clinical documentation to the most accurate ICD-10-CM and CPT codes.

Clinical Text:
"{clinical_text[:3000]}"

Respond in the following JSON format:
{{
    "icd_10": [
        {{"code": "...", "description": "...", "justification": "..."}}
    ],
    "cpt": [
        {{"code": "...", "description": "...", "justification": "..."}}
    ],
    "billing_tier": "99213" or "99214" etc (Evaluation and Management Level)
}}
Only respond with the JSON.
"""
    try:
        response = llm.ask_llm(prompt)
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        return json.loads(response)
    except Exception as e:
        return {
            "error": f"Failed to generate billing suggestions: {str(e)}",
            "icd_10": [],
            "cpt": []
        }

def format_billing_report(suggestions: Dict[str, Any]) -> str:
    """Format billing suggestions for the provider display."""
    if "error" in suggestions:
        return f"⚠ {suggestions['error']}"

    lines = [
        "=" * 50,
        "  BILLING & CODING SUGGESTIONS",
        "=" * 50,
        f"  Recommended E/M Level: {suggestions.get('billing_tier', 'N/A')}",
        "-" * 50,
        "\n🩺 ICD-10 (Diagnosis):"
    ]
    
    for item in suggestions.get("icd_10", []):
        lines.append(f"   • {item['code']} - {item['description']}")
        lines.append(f"     [Justification: {item.get('justification', 'Clinical finding')}]")

    lines.append("\n📋 CPT (Procedure):")
    for item in suggestions.get("cpt", []):
        lines.append(f"   • {item['code']} - {item['description']}")
        lines.append(f"     [Justification: {item.get('justification', 'Ordered procedure')}]")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)
