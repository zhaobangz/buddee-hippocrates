"""Clinical Guidelines Engine — Clinical Decision Co-Pilot.

Maps patient conditions to the latest clinical guidelines and suggests
next treatment steps.  NOT a diagnosis tool — this is a reference and
decision-support layer.

Starts with a built-in guideline database; designed for future integration
with live guideline APIs (UpToDate, DynaMed, etc.).
"""

from typing import Any, Dict, List, Optional
import json

from core.rag_engine import get_rag_engine
from core.llm_manager import LLMManager
from core.safety import log_audit_event, redact_pii

llm = LLMManager()
rag = get_rag_engine()


# ── Built-in Guideline Database ──────────────────────────────────────

GUIDELINES_DB: Dict[str, Dict[str, Any]] = {
    "type_2_diabetes": {
        "condition": "Type 2 Diabetes Mellitus",
        "source": "ADA Standards of Care 2024",
        "first_line": "Metformin + lifestyle modifications",
        "second_line": "Add GLP-1 receptor agonist or SGLT2 inhibitor",
        "third_line": "Add insulin therapy if A1C remains above target",
        "monitoring": ["HbA1c every 3-6 months", "Renal function annually", "Eye exam annually", "Foot exam each visit"],
        "targets": {"a1c": "< 7.0%", "fasting_glucose": "80-130 mg/dL", "bp": "< 130/80 mmHg"},
        "key_considerations": [
            "Individualize A1C target based on patient factors",
            "Consider cardiovascular benefit of GLP-1 RA or SGLT2i",
            "Screen for diabetic kidney disease annually",
        ],
    },
    "hypertension": {
        "condition": "Hypertension",
        "source": "ACC/AHA 2017 Guidelines",
        "first_line": "Thiazide diuretic, ACE inhibitor, ARB, or CCB",
        "second_line": "Combination therapy from different classes",
        "third_line": "Add spironolactone or additional agent for resistant HTN",
        "monitoring": ["BP check every 3-6 months", "Renal function and electrolytes", "Lipid panel annually"],
        "targets": {"bp": "< 130/80 mmHg (general)", "bp_elderly": "< 130/80 mmHg"},
        "key_considerations": [
            "ACE/ARB preferred if diabetes or CKD present",
            "Avoid ACE + ARB combination",
            "Assess for secondary causes if resistant",
        ],
    },
    "hyperlipidemia": {
        "condition": "Hyperlipidemia",
        "source": "ACC/AHA 2018 Cholesterol Guidelines",
        "first_line": "High-intensity statin (atorvastatin 40-80mg or rosuvastatin 20-40mg)",
        "second_line": "Add ezetimibe if LDL remains elevated",
        "third_line": "Add PCSK9 inhibitor for very high-risk patients",
        "monitoring": ["Lipid panel 4-12 weeks after starting/changing therapy", "then every 3-12 months"],
        "targets": {"ldl_high_risk": "< 70 mg/dL", "ldl_moderate_risk": "< 100 mg/dL"},
        "key_considerations": [
            "Risk-enhance shared decision-making for borderline risk",
            "Monitor for statin side effects (myalgia)",
            "Check liver function at baseline",
        ],
    },
    "asthma": {
        "condition": "Asthma",
        "source": "GINA 2024 Guidelines",
        "first_line": "Low-dose ICS-formoterol as needed (or daily low-dose ICS + SABA)",
        "second_line": "Medium-dose ICS or low-dose ICS-LABA",
        "third_line": "High-dose ICS-LABA, consider add-on (tiotropium, biologic)",
        "monitoring": ["Symptom control assessment each visit", "Lung function (FEV1) periodically", "Inhaler technique review"],
        "targets": {"symptom_control": "Well-controlled (symptoms ≤ 2x/week)"},
        "key_considerations": [
            "Step up if not controlled, step down if stable 3+ months",
            "Address modifiable risk factors (smoking, allergens)",
            "Annual flu vaccine recommended",
        ],
    },
    "depression": {
        "condition": "Major Depressive Disorder",
        "source": "APA Practice Guidelines 2023",
        "first_line": "SSRI or SNRI + psychotherapy",
        "second_line": "Switch antidepressant class or augment (bupropion, aripiprazole)",
        "third_line": "TMS, esketamine, or ECT for treatment-resistant depression",
        "monitoring": ["PHQ-9 every 2-4 weeks initially", "Monthly after stabilization", "Suicidality screening"],
        "targets": {"phq9": "< 5 (remission)"},
        "key_considerations": [
            "Allow 4-6 weeks for adequate trial",
            "Monitor for suicidality especially in young adults",
            "Assess for bipolar before starting antidepressant",
        ],
    },
}

# ── RAG Seeding ───────────────────────────────────────────────────────

def seed_rag_if_empty():
    """Seed the RAG engine with the built-in guidelines if empty."""
    if not rag.metadata:
        docs = []
        for key, g in GUIDELINES_DB.items():
            text = (
                f"Condition: {g['condition']}\n"
                f"Source: {g['source']}\n"
                f"First Line: {g['first_line']}\n"
                f"Second Line: {g['second_line']}\n"
                f"Third Line: {g['third_line']}\n"
                f"Targets: {json.dumps(g['targets'])}\n"
                f"Monitoring: {', '.join(g['monitoring'])}\n"
                f"Considerations: {', '.join(g['key_considerations'])}"
            )
            docs.append({
                "text": text,
                "domain": "clinical_guideline",
                "condition": g["condition"],
                "key": key
            })
        rag.add_documents(docs)

# Initialize RAG with static data
seed_rag_if_empty()


def lookup_guideline(condition: str, patient_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Look up clinical guidelines for a given condition using RAG.

    Args:
        condition: Condition name or search term.
        patient_context: Optional patient data to contextualize the lookup.

    Returns:
        dict with guideline fields or an search results.
    """
    # Search RAG
    results = rag.search(condition, top_k=1)
    
    if not results:
        return {
            "error": f"No guideline found for '{condition}'.",
            "tip": "Try searching for a specific condition like 'diabetes' or 'hypertension'.",
        }

    guideline = results[0]
    
    # Add patient-specific notes if context provided
    if patient_context:
        guideline["patient_specific_notes"] = _contextualize(guideline.get("condition", ""), patient_context)

    return guideline


def reconcile_multi_morbidity(patient_context: Dict[str, Any]) -> str:
    """Implement logic for 'multi-morbid' patients.
    
    Resolves potential medication contraindications across multiple guidelines.
    """
    conditions = patient_context.get("conditions", [])
    if len(conditions) < 2:
        return "Not enough conditions for multi-morbidity mapping."

    # Fetch guidelines for all conditions
    all_guidelines = []
    for cond in conditions:
        res = rag.search(cond, top_k=1)
        if res:
            all_guidelines.append(res[0])

    if not all_guidelines:
        return "Could not retrieve guidelines for the patient's conditions."

    # Use LLM to reconcile
    prompt = f"""
System: You are an expert clinical pharmacologist.
Task: Reconcile clinical guidelines for a multi-morbid patient.
Patient Context: {json.dumps(patient_context)}
Guidelines to Reconcile: {json.dumps(all_guidelines)}

Identify potential contraindications, medication interactions, or necessary adjustments (e.g., Metformin in CKD, ACE/ARB in renal failure).
Provide a "Combined Clinical Strategy".
"""
    
    reconciliation = llm.ask_llm(prompt)
    
    log_audit_event("multi_morbidity_reconciliation", {
        "conditions": conditions,
        "reconciliation_preview": reconciliation[:200]
    })
    
    return reconciliation


def suggest_next_step(condition: str, current_treatment: str = "") -> str:
    """Suggest the next treatment step based on current therapy.

    Returns a plain-text recommendation string.
    """
    key = condition.lower().strip()
    key = _CONDITION_ALIASES.get(key, key)

    if key not in GUIDELINES_DB:
        return f"No guidelines available for '{condition}'. Cannot suggest next step."

    g = GUIDELINES_DB[key]
    current_lower = current_treatment.lower()

    if not current_treatment:
        return (
            f"For {g['condition']} ({g['source']}):\n"
            f"→ Recommended first-line: {g['first_line']}"
        )

    # Simple step logic
    if any(word in current_lower for word in ("metformin", "thiazide", "ace", "arb", "ccb", "ssri", "ics")):
        return (
            f"Patient currently on first-line therapy ({current_treatment}).\n"
            f"If targets not met, consider stepping up to:\n"
            f"→ {g['second_line']}\n\n"
            f"Source: {g['source']}"
        )

    return (
        f"Current treatment: {current_treatment}\n"
        f"Guideline ({g['source']}) step-up options:\n"
        f"  1st line: {g['first_line']}\n"
        f"  2nd line: {g['second_line']}\n"
        f"  3rd line: {g['third_line']}"
    )


def format_guideline_summary(guideline: Dict[str, Any]) -> str:
    """Format a guideline lookup result as a human-readable string."""
    if "error" in guideline:
        return f"⚠ {guideline['error']}"

    lines = [
        "=" * 50,
        f"  CLINICAL GUIDELINE: {guideline.get('condition', '')}",
        f"  Source: {guideline.get('source', '')}",
        "=" * 50,
        f"\n  1st Line: {guideline.get('first_line', 'N/A')}",
        f"  2nd Line: {guideline.get('second_line', 'N/A')}",
        f"  3rd Line: {guideline.get('third_line', 'N/A')}",
    ]

    targets = guideline.get("targets", {})
    if targets:
        lines.append("\n  📊 Targets:")
        for k, v in targets.items():
            lines.append(f"     {k}: {v}")

    monitoring = guideline.get("monitoring", [])
    if monitoring:
        lines.append("\n  🔍 Monitoring:")
        for m in monitoring:
            lines.append(f"     • {m}")

    considerations = guideline.get("key_considerations", [])
    if considerations:
        lines.append("\n  💡 Key Considerations:")
        for c in considerations:
            lines.append(f"     • {c}")

    notes = guideline.get("patient_specific_notes", [])
    if notes:
        lines.append("\n  🏥 Patient-Specific Notes:")
        for n in notes:
            lines.append(f"     ⚡ {n}")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)


def _contextualize(condition_key: str, patient_context: Dict[str, Any]) -> List[str]:
    """Add patient-specific notes to a guideline lookup."""
    notes: List[str] = []
    meds = [m.lower() for m in patient_context.get("medications", [])]
    allergies = [a.lower() for a in patient_context.get("allergies", [])]

    if condition_key == "type_2_diabetes":
        if any("metformin" in m for m in meds):
            notes.append("Patient is already on metformin — consider step-up if A1C above target")
        if any("sulfa" in a for a in allergies):
            notes.append("Sulfa allergy noted — avoid sulfonylureas")

    if condition_key == "hypertension":
        if any("ace" in m or "lisinopril" in m or "enalapril" in m for m in meds):
            notes.append("Already on ACE inhibitor — assess for cough side effect")
        if "diabetes" in " ".join(patient_context.get("conditions", [])).lower():
            notes.append("Diabetic patient — ACE/ARB preferred per co-morbidity guidelines")

    return notes
