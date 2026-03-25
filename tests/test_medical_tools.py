"""Tests for the healthcare medical tools."""

import json
import os
import tempfile
# Unused import removed

# Ensure tools can be imported
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.ehr_reader import parse_patient_record, generate_patient_brief
from tools.prior_auth import (
    generate_prior_auth_form,
    check_auth_status,
    get_required_fields,
    list_pending_auths,
    format_prior_auth_summary,
)
from tools.clinical_guidelines import (
    lookup_guideline,
    suggest_next_step,
    format_guideline_summary,
)
from tools.follow_up import (
    create_follow_up,
    check_follow_ups,
    process_follow_up_response,
    format_follow_up_summary,
)
from tools.scheduling import (
    schedule_lab,
    schedule_imaging,
    create_referral,
    get_pending_tasks,
    complete_task,
    format_task_summary,
)


# ── EHR Reader Tests ────────────────────────────────────────────────

class TestEHRReader:
    def test_parse_text_record(self, tmp_path):
        """Parse a plain-text patient record."""
        record = tmp_path / "patient.txt"
        record.write_text(
            "Patient Name: Jane Doe\n"
            "Patient ID: P-9876\n"
            "Conditions: Type 2 Diabetes, Hypertension\n"
            "Medications: Metformin 1000mg, Lisinopril 10mg\n"
            "Allergies: Penicillin, Sulfa\n"
        )
        result = parse_patient_record(str(record))
        assert result["patient_name"] == "Jane Doe"
        assert result["patient_id"] == "P-9876"
        assert "Type 2 Diabetes" in result["conditions"]
        assert "Metformin 1000mg" in result["medications"]
        assert "Penicillin" in result["allergies"]

    def test_parse_json_record(self, tmp_path):
        """Parse a JSON patient record."""
        record = tmp_path / "patient.json"
        data = {
            "patient_name": "John Smith",
            "patient_id": "P-1234",
            "conditions": ["Asthma"],
            "medications": ["Albuterol"],
            "allergies": [],
        }
        record.write_text(json.dumps(data))
        result = parse_patient_record(str(record))
        assert result["patient_name"] == "John Smith"
        assert result["patient_id"] == "P-1234"
        assert "Asthma" in result["conditions"]

    def test_parse_missing_file(self):
        """Return error for missing file."""
        result = parse_patient_record("/nonexistent/file.txt")
        assert "error" in result

    def test_generate_patient_brief(self):
        """Generate a patient brief from structured data."""
        data = {
            "patient_name": "Jane Doe",
            "patient_id": "P-9876",
            "conditions": ["Type 2 Diabetes", "Hypertension"],
            "medications": ["Metformin 1000mg", "Lisinopril 10mg", "Atorvastatin", "Aspirin", "Omeprazole"],
            "allergies": ["Penicillin"],
            "lab_results": [],
        }
        brief = generate_patient_brief(data)
        assert "Jane Doe" in brief
        assert "PATIENT BRIEF" in brief
        assert "Risk Flags" in brief
        assert "Polypharmacy" in brief  # 5 medications


# ── Prior Authorization Tests ────────────────────────────────────────

class TestPriorAuth:
    _orig_file: str = ""
    _tmp: tempfile._TemporaryFileWrapper = None  # type: ignore

    def setup_method(self):
        """Use a temp file for the PA store."""
        import tools.prior_auth as pa_mod
        self._orig_file = pa_mod._PRIOR_AUTH_STORE_FILE
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        pa_mod._PRIOR_AUTH_STORE_FILE = self._tmp.name

    def teardown_method(self):
        import tools.prior_auth as pa_mod
        pa_mod._PRIOR_AUTH_STORE_FILE = self._orig_file
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_get_required_fields(self):
        """Medicare has more fields than default."""
        default_fields = get_required_fields("default")
        medicare_fields = get_required_fields("medicare")
        assert len(medicare_fields) > len(default_fields)
        assert "medical_necessity_statement" in medicare_fields

    def test_generate_and_check(self):
        """Generate a PA form and check its status."""
        patient = {"patient_name": "Test Patient", "patient_id": "TP-001"}
        form = generate_prior_auth_form(patient, "MRI Brain", "R51 - Headache")
        assert form["auth_id"].startswith("PA-")
        assert form["status"] == "pending"
        assert form["treatment_requested"] == "MRI Brain"

        # Check status
        status = check_auth_status(form["auth_id"])
        assert status["status"] == "pending"

    def test_list_pending(self):
        """List pending PAs."""
        patient = {"patient_name": "P1", "patient_id": "001"}
        generate_prior_auth_form(patient, "Treatment A", "Dx A")
        generate_prior_auth_form(patient, "Treatment B", "Dx B")
        pending = list_pending_auths()
        assert len(pending) >= 2

    def test_format_summary(self):
        """Format a PA summary as readable text."""
        patient = {"patient_name": "Test", "patient_id": "T01"}
        form = generate_prior_auth_form(patient, "CT Scan", "S72.001A")
        summary = format_prior_auth_summary(form)
        assert "PRIOR AUTHORIZATION" in summary
        assert "CT Scan" in summary


# ── Clinical Guidelines Tests ────────────────────────────────────────

class TestClinicalGuidelines:
    def test_lookup_diabetes(self):
        """Look up diabetes guidelines."""
        result = lookup_guideline("diabetes")
        assert result["condition"] == "Type 2 Diabetes Mellitus"
        assert "ADA" in result["source"]
        assert "first_line" in result

    def test_lookup_alias(self):
        """Look up by alias (htn → hypertension)."""
        result = lookup_guideline("htn")
        assert result["condition"] == "Hypertension"

    def test_lookup_unknown(self):
        """Unknown condition returns error with available list."""
        result = lookup_guideline("xyzzy_disease")
        assert "error" in result
        assert "available_conditions" in result

    def test_suggest_next_step(self):
        """Suggest next step for diabetes on metformin."""
        suggestion = suggest_next_step("diabetes", "Metformin")
        assert "step" in suggestion.lower() or "second" in suggestion.lower() or "line" in suggestion.lower()

    def test_format_summary(self):
        """Format guideline as readable text."""
        result = lookup_guideline("asthma")
        summary = format_guideline_summary(result)
        assert "CLINICAL GUIDELINE" in summary
        assert "GINA" in summary

    def test_patient_contextualization(self):
        """Guidelines include patient-specific notes when context provided."""
        ctx = {
            "conditions": ["Type 2 Diabetes"],
            "medications": ["Metformin 1000mg"],
            "allergies": ["Sulfa"],
        }
        result = lookup_guideline("diabetes", patient_context=ctx)
        assert "patient_specific_notes" in result
        notes = result["patient_specific_notes"]
        assert any("metformin" in n.lower() for n in notes)


# ── Follow-Up Tests ──────────────────────────────────────────────────

class TestFollowUp:
    _orig_file: str = ""
    _tmp: tempfile._TemporaryFileWrapper = None  # type: ignore

    def setup_method(self):
        import tools.follow_up as fu_mod
        self._orig_file = fu_mod._FOLLOW_UP_STORE_FILE
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        fu_mod._FOLLOW_UP_STORE_FILE = self._tmp.name

    def teardown_method(self):
        import tools.follow_up as fu_mod
        fu_mod._FOLLOW_UP_STORE_FILE = self._orig_file
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_create_follow_up(self):
        """Create a symptom check follow-up."""
        record = create_follow_up("P-001", reason="symptom_check", patient_name="Jane")
        assert record["follow_up_id"].startswith("FU-")
        assert record["status"] == "pending"
        assert record["type"] == "symptom_check"

    def test_check_follow_ups(self):
        """List follow-ups for a patient."""
        create_follow_up("P-002", reason="medication_adherence")
        create_follow_up("P-002", reason="general")
        results = check_follow_ups(patient_id="P-002")
        assert len(results) >= 2

    def test_process_response_no_risk(self):
        """Process a normal response."""
        record = create_follow_up("P-003", reason="symptom_check")
        updated = process_follow_up_response(record["follow_up_id"], "Feeling much better!")
        assert updated["status"] == "completed"

    def test_process_response_with_risk(self):
        """Process a response with risk → escalation."""
        record = create_follow_up("P-004", reason="post_procedure")
        updated = process_follow_up_response(
            record["follow_up_id"], "Having severe chest pain", risk_detected=True
        )
        assert updated["status"] == "escalated"
        assert updated["escalated"] is True

    def test_format_summary(self):
        """Format follow-ups as readable text."""
        create_follow_up("P-005", reason="lab_results", patient_name="Bob")
        records = check_follow_ups(patient_id="P-005")
        summary = format_follow_up_summary(records)
        assert "FOLLOW-UP SUMMARY" in summary


# ── Scheduling Tests ─────────────────────────────────────────────────

class TestScheduling:
    _orig_file: str = ""
    _tmp: tempfile._TemporaryFileWrapper = None  # type: ignore

    def setup_method(self):
        import tools.scheduling as sched_mod
        self._orig_file = sched_mod._SCHEDULE_STORE_FILE
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        sched_mod._SCHEDULE_STORE_FILE = self._tmp.name

    def teardown_method(self):
        import tools.scheduling as sched_mod
        sched_mod._SCHEDULE_STORE_FILE = self._orig_file
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_schedule_lab(self):
        task = schedule_lab("P-001", "HbA1c", reason="Diabetes monitoring")
        assert task["task_id"].startswith("TASK-")
        assert task["type"] == "lab"
        assert "HbA1c" in task["description"]

    def test_schedule_imaging(self):
        task = schedule_imaging("P-001", "MRI", body_part="Brain")
        assert task["type"] == "imaging"

    def test_create_referral(self):
        task = create_referral("P-001", "Cardiology", reason="Chest pain", urgency="urgent")
        assert task["type"] == "referral"
        assert task["details"]["urgency"] == "urgent"

    def test_get_pending_tasks(self):
        schedule_lab("P-010", "CBC")
        schedule_imaging("P-010", "X-ray")
        tasks = get_pending_tasks(patient_id="P-010")
        assert len(tasks) >= 2

    def test_complete_task(self):
        task = schedule_lab("P-011", "CMP")
        result = complete_task(task["task_id"], notes="Results normal")
        assert result["status"] == "completed"

    def test_format_summary(self):
        schedule_lab("P-020", "Lipid Panel")
        tasks = get_pending_tasks(patient_id="P-020")
        summary = format_task_summary(tasks)
        assert "WORKFLOW TASKS" in summary
