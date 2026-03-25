"""EHR Reader — Pre-Visit Intelligence tool.

Reads patient data from uploaded files (PDF / text) and generates
structured patient briefs.  Designed as a clean abstraction ready for
future EHR API integration (Epic, Cerner, etc.).
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict, List

# Optional PDF support — gracefully degrade to text-only
try:
    import PyPDF2  # type: ignore
    _HAS_PDF = True
except ImportError:
    _HAS_PDF = False


def parse_patient_record(file_path: str) -> Dict[str, Any]:
    """Extract patient information from a PDF or plain-text upload.

    Returns a structured dict with keys:
        raw_text, patient_name, patient_id, conditions, medications,
        allergies, lab_results, notes
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    ext = os.path.splitext(file_path)[1].lower()

    raw_text = ""
    if ext == ".pdf" and _HAS_PDF:
        try:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    raw_text += page.extract_text() or ""
        except Exception as e:
            return {"error": f"Failed to read PDF: {e}"}
    elif ext == ".json":
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {
                    "raw_text": json.dumps(data),
                    "patient_name": data.get("patient_name", "Unknown"),
                    "patient_id": data.get("patient_id", "N/A"),
                    "conditions": data.get("conditions", []),
                    "medications": data.get("medications", []),
                    "allergies": data.get("allergies", []),
                    "lab_results": data.get("lab_results", []),
                    "notes": data.get("notes", ""),
                }
        except Exception as e:
            return {"error": f"Failed to parse JSON: {e}"}
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}

    # Basic extraction from raw text
    return _extract_from_text(raw_text)


def _extract_from_text(text: str) -> Dict[str, Any]:
    """Attempt lightweight keyword extraction from raw clinical text."""
    result: Dict[str, Any] = {
        "raw_text": text,
        "patient_name": "Unknown",
        "patient_id": "N/A",
        "conditions": [],
        "medications": [],
        "allergies": [],
        "lab_results": [],
        "notes": "",
    }

    lines = text.split("\n")
    for line in lines:
        lower = line.lower().strip()
        if lower.startswith("patient name:") or lower.startswith("name:"):
            result["patient_name"] = line.split(":", 1)[1].strip()
        elif lower.startswith("patient id:") or lower.startswith("id:"):
            result["patient_id"] = line.split(":", 1)[1].strip()
        elif lower.startswith("conditions:") or lower.startswith("diagnoses:"):
            result["conditions"] = [c.strip() for c in line.split(":", 1)[1].split(",")]
        elif lower.startswith("medications:") or lower.startswith("meds:"):
            result["medications"] = [m.strip() for m in line.split(":", 1)[1].split(",")]
        elif lower.startswith("allergies:"):
            result["allergies"] = [a.strip() for a in line.split(":", 1)[1].split(",")]

    return result


def generate_patient_brief(patient_data: Dict[str, Any]) -> str:
    """Generate a structured patient brief from parsed patient data.

    Returns a human-readable brief summarizing key risks, missing labs,
    and suggested questions for the provider.
    """
    name = patient_data.get("patient_name", "Unknown")
    pid = patient_data.get("patient_id", "N/A")
    conditions = patient_data.get("conditions", [])
    medications = patient_data.get("medications", [])
    allergies = patient_data.get("allergies", [])
    lab_results = patient_data.get("lab_results", [])
    notes = patient_data.get("notes", "")

    brief_lines = [
        "=" * 50,
        "  PATIENT BRIEF — Pre-Visit Intelligence",
        "=" * 50,
        f"  Patient: {name}  (ID: {pid})",
        "-" * 50,
    ]

    # Conditions
    brief_lines.append("\n📋 Active Conditions:")
    if conditions:
        for c in conditions:
            brief_lines.append(f"   • {c}")
    else:
        brief_lines.append("   ⚠ No conditions on file")

    # Medications
    brief_lines.append("\n💊 Current Medications:")
    if medications:
        for m in medications:
            brief_lines.append(f"   • {m}")
    else:
        brief_lines.append("   ⚠ No medications listed")

    # Allergies
    brief_lines.append("\n🚨 Allergies:")
    if allergies:
        for a in allergies:
            brief_lines.append(f"   • {a}")
    else:
        brief_lines.append("   None reported")

    # Risk flags
    brief_lines.append("\n⚠ Risk Flags:")
    risks = _identify_risks(conditions, medications, allergies)
    if risks:
        for r in risks:
            brief_lines.append(f"   🔴 {r}")
    else:
        brief_lines.append("   No elevated risks detected")

    # Missing labs
    brief_lines.append("\n🔬 Suggested Missing Labs:")
    missing = _suggest_missing_labs(conditions, lab_results)
    if missing:
        for lab in missing:
            brief_lines.append(f"   ➜ {lab}")
    else:
        brief_lines.append("   Labs appear up to date")

    # Suggested questions
    brief_lines.append("\n❓ Suggested Questions for Visit:")
    questions = _suggest_questions(conditions, medications)
    for q in questions:
        brief_lines.append(f"   • {q}")

    if notes:
        brief_lines.append(f"\n📝 Notes: {notes}")

    brief_lines.append("\n" + "=" * 50)
    return "\n".join(brief_lines)


def _identify_risks(
    conditions: List[str], medications: List[str], allergies: List[str]
) -> List[str]:
    """Identify potential risk flags from patient data."""
    risks = []
    cond_lower = [c.lower() for c in conditions]
    med_lower = [m.lower() for m in medications]

    if "diabetes" in " ".join(cond_lower):
        risks.append("Diabetic patient — monitor A1C and renal function")
    if "hypertension" in " ".join(cond_lower):
        risks.append("Hypertension — review BP medication adherence")
    if any("warfarin" in m or "blood thinner" in m for m in med_lower):
        risks.append("On anticoagulant therapy — bleeding risk")
    if len(medications) >= 5:
        risks.append(f"Polypharmacy risk — patient on {len(medications)} medications")
    if allergies:
        risks.append(f"Known allergies: {', '.join(allergies)}")
    return risks


def _suggest_missing_labs(
    conditions: List[str], lab_results: List[Any]
) -> List[str]:
    """Suggest labs that may be missing based on conditions."""
    suggestions = []
    cond_lower = " ".join(c.lower() for c in conditions)
    existing = {str(l).lower() for l in lab_results} if lab_results else set()

    if "diabetes" in cond_lower and "a1c" not in " ".join(existing):
        suggestions.append("HbA1c (diabetes monitoring)")
    if "diabetes" in cond_lower and "creatinine" not in " ".join(existing):
        suggestions.append("Serum Creatinine / eGFR (renal function)")
    if "hypertension" in cond_lower and "lipid" not in " ".join(existing):
        suggestions.append("Lipid Panel (cardiovascular risk)")
    if not lab_results:
        suggestions.append("Complete Blood Count (CBC) — routine baseline")
        suggestions.append("Comprehensive Metabolic Panel (CMP)")
    return suggestions


def _suggest_questions(
    conditions: List[str], medications: List[str]
) -> List[str]:
    """Suggest clinical questions for the visit."""
    questions = ["How have you been feeling since your last visit?"]
    cond_lower = " ".join(c.lower() for c in conditions)

    if "diabetes" in cond_lower:
        questions.append("Have you been monitoring your blood sugar regularly?")
        questions.append("Any episodes of low blood sugar (hypoglycemia)?")
    if "hypertension" in cond_lower:
        questions.append("Have you been checking your blood pressure at home?")
    if medications:
        questions.append("Are you experiencing any side effects from your medications?")
        questions.append("Have you missed any doses recently?")
    questions.append("Any new symptoms or concerns since our last visit?")
    return questions
