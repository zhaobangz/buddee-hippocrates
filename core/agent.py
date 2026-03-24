# core/agent.py — Clinical Agent Orchestrator
# Routes user input to the appropriate healthcare workflow tool.

from core.llm_manager import LLMManager
from core.memory import Memory
from core.config import Config
from core.tracing import get_tracer
from core.safety import (
    validate_action,
    request_human_approval,
    sanitize_response,
    log_audit_event,
)
from tools import (
    ehr_reader,
    prior_auth,
    clinical_guidelines,
    follow_up,
    scheduling,
)
import os
from typing import Optional

# Initialize tracer
tracer = get_tracer(__name__)

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None


class Agent:
    def __init__(self):
        # Memory (persistent) if enabled
        self.memory = (
            Memory(
                max_history=Config.MAX_MEMORY_HISTORY,
                persist_file=Config.MEMORY_PERSIST_FILE,
            )
            if Config.MEMORY_ENABLED
            else None
        )

        # LLM manager — pass memory so the manager can include context
        self.llm_manager = LLMManager(self.memory)

        # Optional voice stack
        self.recognizer = (
            sr.Recognizer() if (Config.USE_VOICE and sr is not None) else None
        )
        self.tts_engine = (
            pyttsx3.init() if (Config.USE_VOICE and pyttsx3 is not None) else None
        )

        if Config.USE_VOICE and self.tts_engine:
            try:
                voices = self.tts_engine.getProperty("voices")
                if voices:
                    self.tts_engine.setProperty("voice", voices[0].id)
                self.tts_engine.setProperty("rate", 150)
            except Exception:
                pass

        # Pending approval for gated actions
        self._pending_approval = None

        log_audit_event("agent_initialized", {"assistant": Config.ASSISTANT_NAME})

    # ── Voice helpers ────────────────────────────────────────────────

    def listen(self):
        """Listen for voice input."""
        if not self.recognizer:
            return None
        try:
            with sr.Microphone() as source:
                print(f"{Config.ASSISTANT_NAME} is listening...")
                self.recognizer.adjust_for_ambient_noise(source)
                try:
                    audio = self.recognizer.listen(source, timeout=5)
                    text = self.recognizer.recognize_google(audio)
                    print(f"You said: {text}")
                    return text
                except sr.UnknownValueError:
                    return "Sorry, I did not catch that."
                except sr.RequestError:
                    return "Sorry, my speech service is down."
                except sr.WaitTimeoutError:
                    return None
        except Exception:
            return None

    def speak(self, text):
        """Convert text to speech."""
        if self.tts_engine:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()

    # ── Intent Detection ─────────────────────────────────────────────

    def detect_intent(self, ui: str) -> str:
        """Use LLM to classify user intent into a healthcare workflow."""
        with tracer.start_as_current_span("detect_intent") as span:
            span.set_attribute("input.length", len(ui))
            prompt = f"""
Analyze this user input and classify its intent: "{ui}"

You are a Clinical Agent System. Classify the intent into one of these categories:

- prior_auth: User wants to create, check, or manage prior authorization forms
- patient_brief: User wants to prepare a patient brief or review patient records
- follow_up: User wants to create, check, or manage patient follow-ups
- guidelines_lookup: User wants to look up clinical guidelines or treatment recommendations
- schedule_task: User wants to schedule labs, imaging, referrals, or other clinical tasks
- risk_check: User wants to check patient risk factors or review alerts
- patient_context: User wants to set or view current patient information
- general_clinical_query: User has a general clinical question or request

Respond with ONLY the intent name. If unsure, respond with "general_clinical_query".
"""
            intent = self.llm_manager.ask_llm(prompt).strip().lower()
            # Clean up LLM response to extract just the intent
            for valid_intent in (
                "prior_auth", "patient_brief", "follow_up",
                "guidelines_lookup", "schedule_task", "risk_check",
                "patient_context", "general_clinical_query",
            ):
                if valid_intent in intent:
                    intent = valid_intent
                    break
            else:
                intent = "general_clinical_query"

            span.set_attribute("detected_intent", intent)
            log_audit_event("intent_detected", {"input_preview": ui[:100], "intent": intent})
            return intent

    # ── Main Handler ─────────────────────────────────────────────────

    def handle(self, ui: str) -> str:
        """Process user input and route to the appropriate clinical workflow."""
        with tracer.start_as_current_span("handle") as span:
            span.set_attribute("input.length", len(ui) if ui else 0)

            if not ui or ui.strip() == "":
                return "I didn't hear anything. Please repeat it."

            # Handle pending approval flow
            if self._pending_approval is not None:
                lower = ui.strip().lower()
                if lower in ("yes", "y", "confirm", "ok", "sure", "approve"):
                    pending = self._pending_approval
                    self._pending_approval = None
                    log_audit_event("action_approved", pending)
                    return self._execute_approved_action(pending)
                else:
                    self._pending_approval = None
                    log_audit_event("action_denied", {"input": ui[:100]})
                    return "Action cancelled."

            # Detect intent
            intent = self.detect_intent(ui)
            lower = ui.lower()

            # ── Route to healthcare workflows ────────────────────────

            if intent == "prior_auth":
                return self._handle_prior_auth(ui, lower, span)

            elif intent == "patient_brief":
                return self._handle_patient_brief(ui, lower, span)

            elif intent == "follow_up":
                return self._handle_follow_up(ui, lower, span)

            elif intent == "guidelines_lookup":
                return self._handle_guidelines(ui, lower, span)

            elif intent == "schedule_task":
                return self._handle_scheduling(ui, lower, span)

            elif intent == "risk_check":
                return self._handle_risk_check(ui, span)

            elif intent == "patient_context":
                return self._handle_patient_context(ui, span)

            else:  # general_clinical_query
                return self._handle_general_query(ui, span)

    # ── Workflow Handlers ────────────────────────────────────────────

    def _handle_prior_auth(self, ui: str, lower: str, span) -> str:
        with tracer.start_as_current_span("prior_auth_workflow"):
            # Check for status queries
            if any(k in lower for k in ("status", "check", "pending", "list")):
                pending = prior_auth.list_pending_auths()
                if pending:
                    summaries = [prior_auth.format_prior_auth_summary(p) for p in pending]
                    return "\n\n".join(summaries)
                return "No pending prior authorization requests."

            # Generate new prior auth
            validation = validate_action("prior_auth_submit")
            if not validation["allowed"]:
                return validation["reason"]

            patient_ctx = self.memory.get_patient_context() if self.memory else {}
            if not patient_ctx:
                return (
                    "No patient context set. Please set the current patient first.\n"
                    "Example: 'Set patient John Smith, ID 12345, diabetes, on metformin'"
                )

            # Use LLM to extract treatment and diagnosis from the request
            extract_prompt = f"""
From this request, extract the treatment and diagnosis for a prior authorization.
Request: "{ui}"
Patient conditions: {patient_ctx.get('conditions', [])}

Respond in this exact format:
TREATMENT: [treatment requested]
DIAGNOSIS: [diagnosis/condition code]

If not clearly stated, use the patient's primary condition.
"""
            extraction = self.llm_manager.ask_llm(extract_prompt)
            treatment = "See clinical notes"
            diagnosis = "See clinical notes"
            for line in extraction.split("\n"):
                if line.strip().upper().startswith("TREATMENT:"):
                    treatment = line.split(":", 1)[1].strip()
                elif line.strip().upper().startswith("DIAGNOSIS:"):
                    diagnosis = line.split(":", 1)[1].strip()

            if validation.get("requires_approval"):
                self._pending_approval = {
                    "action": "prior_auth_submit",
                    "patient_data": patient_ctx,
                    "treatment": treatment,
                    "diagnosis": diagnosis,
                }
                return request_human_approval("prior_auth_submit", {
                    "patient": patient_ctx.get("name", "Unknown"),
                    "treatment": treatment,
                    "diagnosis": diagnosis,
                })

            form = prior_auth.generate_prior_auth_form(patient_ctx, treatment, diagnosis)
            return prior_auth.format_prior_auth_summary(form)

    def _handle_patient_brief(self, ui: str, lower: str, span) -> str:
        with tracer.start_as_current_span("patient_brief_workflow"):
            patient_ctx = self.memory.get_patient_context() if self.memory else {}
            if not patient_ctx:
                return (
                    "No patient context set. Please set the current patient first, "
                    "or upload a patient record file."
                )
            return ehr_reader.generate_patient_brief(patient_ctx)

    def _handle_follow_up(self, ui: str, lower: str, span) -> str:
        with tracer.start_as_current_span("follow_up_workflow"):
            # Check for listing
            if any(k in lower for k in ("list", "check", "pending", "status", "overdue")):
                patient_ctx = self.memory.get_patient_context() if self.memory else {}
                pid = patient_ctx.get("patient_id")

                if "overdue" in lower:
                    records = follow_up.get_overdue_follow_ups()
                else:
                    records = follow_up.check_follow_ups(patient_id=pid)

                return follow_up.format_follow_up_summary(records)

            # Create new follow-up
            patient_ctx = self.memory.get_patient_context() if self.memory else {}
            if not patient_ctx.get("patient_id"):
                return "No patient context set. Please set the current patient first."

            # Determine follow-up type from input
            fu_type = "general"
            if any(k in lower for k in ("symptom", "symptoms")):
                fu_type = "symptom_check"
            elif any(k in lower for k in ("medication", "med", "adherence")):
                fu_type = "medication_adherence"
            elif any(k in lower for k in ("lab", "labs", "results")):
                fu_type = "lab_results"
            elif any(k in lower for k in ("procedure", "surgery", "post-op")):
                fu_type = "post_procedure"

            record = follow_up.create_follow_up(
                patient_id=patient_ctx["patient_id"],
                reason=fu_type,
                patient_name=patient_ctx.get("name", ""),
            )
            return (
                f"✅ Follow-up created: {record['follow_up_id']}\n"
                f"Type: {record['type_label']}\n"
                f"Due: {record['due_date']}\n"
                f"Message: {record['message']}"
            )

    def _handle_guidelines(self, ui: str, lower: str, span) -> str:
        with tracer.start_as_current_span("guidelines_workflow"):
            patient_ctx = self.memory.get_patient_context() if self.memory else {}

            # Try to extract condition from the query
            extract_prompt = f"""
From this query, identify the medical condition the user is asking about:
"{ui}"

Respond with ONLY the condition name (e.g., "diabetes", "hypertension", "asthma").
If unclear, respond with "unknown".
"""
            condition = self.llm_manager.ask_llm(extract_prompt).strip().lower()
            condition = condition.strip('"').strip("'").strip(".")

            if condition == "unknown" and patient_ctx.get("conditions"):
                condition = patient_ctx["conditions"][0]

            if not condition or condition == "unknown":
                return (
                    "Please specify a condition to look up guidelines for.\n"
                    "Available: diabetes, hypertension, hyperlipidemia, asthma, depression"
                )

            guideline = clinical_guidelines.lookup_guideline(condition, patient_ctx)

            if "error" in guideline:
                return clinical_guidelines.format_guideline_summary(guideline)

            # Also provide next-step suggestion if patient context exists
            result = clinical_guidelines.format_guideline_summary(guideline)
            if patient_ctx.get("medications"):
                current_meds = ", ".join(patient_ctx["medications"])
                suggestion = clinical_guidelines.suggest_next_step(condition, current_meds)
                result += f"\n\n💡 Treatment Step Suggestion:\n{suggestion}"

            return sanitize_response(result)

    def _handle_scheduling(self, ui: str, lower: str, span) -> str:
        with tracer.start_as_current_span("scheduling_workflow"):
            # Check for listing tasks
            if any(k in lower for k in ("list", "pending", "status", "tasks")):
                patient_ctx = self.memory.get_patient_context() if self.memory else {}
                pid = patient_ctx.get("patient_id")
                tasks = scheduling.get_pending_tasks(patient_id=pid)
                return scheduling.format_task_summary(tasks)

            patient_ctx = self.memory.get_patient_context() if self.memory else {}
            if not patient_ctx.get("patient_id"):
                return "No patient context set. Please set the current patient first."

            pid = patient_ctx["patient_id"]
            pname = patient_ctx.get("name", "")

            # Determine task type
            if any(k in lower for k in ("lab", "blood", "a1c", "cbc", "cmp")):
                lab_type = "General Lab Panel"
                for lt in ("CBC", "CMP", "HbA1c", "Lipid Panel", "TSH", "BMP"):
                    if lt.lower() in lower:
                        lab_type = lt
                        break
                task = scheduling.schedule_lab(pid, lab_type, patient_name=pname)
                return f"🔬 Lab scheduled: {task['task_id']}\n{task['description']}\nDate: {task['scheduled_date']}"

            elif any(k in lower for k in ("imaging", "x-ray", "xray", "mri", "ct", "ultrasound")):
                img_type = "General Imaging"
                for it in ("X-ray", "MRI", "CT", "Ultrasound"):
                    if it.lower() in lower:
                        img_type = it
                        break
                task = scheduling.schedule_imaging(pid, img_type, patient_name=pname)
                return f"📷 Imaging scheduled: {task['task_id']}\n{task['description']}\nDate: {task['scheduled_date']}"

            elif any(k in lower for k in ("referral", "refer", "specialist")):
                validation = validate_action("referral_create")
                if validation.get("requires_approval"):
                    self._pending_approval = {
                        "action": "referral_create",
                        "patient_id": pid,
                        "patient_name": pname,
                        "input": ui,
                    }
                    return request_human_approval("referral_create", {
                        "patient": pname, "request": ui[:200],
                    })
                spec_type = "General Specialist"
                for s in ("Cardiology", "Endocrinology", "Neurology", "Orthopedics", "Dermatology", "Psychiatry"):
                    if s.lower() in lower:
                        spec_type = s
                        break
                task = scheduling.create_referral(pid, spec_type, patient_name=pname)
                return f"👨‍⚕️ Referral created: {task['task_id']}\n{task['description']}\nDate: {task['scheduled_date']}"

            return "Please specify: schedule a lab, imaging, or referral."

    def _handle_risk_check(self, ui: str, span) -> str:
        with tracer.start_as_current_span("risk_check"):
            patient_ctx = self.memory.get_patient_context() if self.memory else {}
            if not patient_ctx:
                return "No patient context set. Cannot assess risk without patient information."

            brief = ehr_reader.generate_patient_brief(patient_ctx)
            # Also check overdue follow-ups
            overdue = follow_up.get_overdue_follow_ups()
            if overdue:
                brief += f"\n\n🚨 OVERDUE FOLLOW-UPS: {len(overdue)}\n"
                brief += follow_up.format_follow_up_summary(overdue)
            return brief

    def _handle_patient_context(self, ui: str, span) -> str:
        with tracer.start_as_current_span("patient_context"):
            lower = ui.lower()

            if any(k in lower for k in ("view", "show", "current", "get", "who")):
                ctx = self.memory.get_patient_context() if self.memory else {}
                if not ctx:
                    return "No patient context is currently set."
                lines = [
                    "📋 Current Patient Context:",
                    f"  Name: {ctx.get('name', 'N/A')}",
                    f"  ID: {ctx.get('patient_id', 'N/A')}",
                    f"  Conditions: {', '.join(ctx.get('conditions', [])) or 'None'}",
                    f"  Medications: {', '.join(ctx.get('medications', [])) or 'None'}",
                    f"  Allergies: {', '.join(ctx.get('allergies', [])) or 'None'}",
                ]
                if ctx.get("notes"):
                    lines.append(f"  Notes: {ctx['notes']}")
                return "\n".join(lines)

            if any(k in lower for k in ("clear", "reset", "remove")):
                if self.memory:
                    self.memory.clear_patient_context()
                return "Patient context cleared."

            # Set patient context via LLM extraction
            if self.memory:
                extract_prompt = f"""
Extract patient information from this input:
"{ui}"

Respond in this exact format (use empty values if not mentioned):
NAME: [patient name]
ID: [patient id]
CONDITIONS: [comma-separated conditions]
MEDICATIONS: [comma-separated medications]
ALLERGIES: [comma-separated allergies]
NOTES: [any additional notes]
"""
                extraction = self.llm_manager.ask_llm(extract_prompt)
                name = pid = notes = ""
                conditions: list = []
                medications: list = []
                allergies: list = []

                for line in extraction.split("\n"):
                    line = line.strip()
                    if line.upper().startswith("NAME:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("ID:"):
                        pid = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("CONDITIONS:"):
                        raw = line.split(":", 1)[1].strip()
                        conditions = [c.strip() for c in raw.split(",") if c.strip()]
                    elif line.upper().startswith("MEDICATIONS:"):
                        raw = line.split(":", 1)[1].strip()
                        medications = [m.strip() for m in raw.split(",") if m.strip()]
                    elif line.upper().startswith("ALLERGIES:"):
                        raw = line.split(":", 1)[1].strip()
                        allergies = [a.strip() for a in raw.split(",") if a.strip()]
                    elif line.upper().startswith("NOTES:"):
                        notes = line.split(":", 1)[1].strip()

                self.memory.set_patient_context(
                    patient_id=pid or "AUTO",
                    name=name,
                    conditions=conditions,
                    medications=medications,
                    allergies=allergies,
                    notes=notes,
                )
                log_audit_event("patient_context_set", {"patient_id": pid, "name": name})
                return (
                    f"✅ Patient context set:\n"
                    f"  Name: {name}\n"
                    f"  ID: {pid or 'AUTO'}\n"
                    f"  Conditions: {', '.join(conditions) or 'None'}\n"
                    f"  Medications: {', '.join(medications) or 'None'}\n"
                    f"  Allergies: {', '.join(allergies) or 'None'}"
                )

            return "Memory is not enabled. Cannot set patient context."

    def _handle_general_query(self, ui: str, span) -> str:
        with tracer.start_as_current_span("general_clinical_query") as gen_span:
            # Build a clinical system prompt
            system_context = (
                "You are a clinical decision-support assistant. "
                "You help healthcare providers with clinical workflows, "
                "guideline references, and administrative tasks. "
                "You do NOT provide diagnoses or prescriptions. "
                "Always recommend consulting with the treating physician for clinical decisions."
            )

            patient_ctx = self.memory.get_patient_context() if self.memory else {}
            if patient_ctx:
                system_context += (
                    f"\n\nCurrent patient: {patient_ctx.get('name', 'Unknown')} "
                    f"(ID: {patient_ctx.get('patient_id', 'N/A')}). "
                    f"Conditions: {', '.join(patient_ctx.get('conditions', []))}. "
                    f"Medications: {', '.join(patient_ctx.get('medications', []))}."
                )

            full_prompt = f"[System: {system_context}]\n\nUser: {ui}"
            response = self.llm_manager.ask_llm(full_prompt)
            response = sanitize_response(response)

            gen_span.set_attribute("response.length", len(response))
            try:
                if self.memory:
                    self.memory.remember(ui, response)
            except Exception:
                pass
            return response

    def _execute_approved_action(self, pending: dict) -> str:
        """Execute an action that was previously approved by human review."""
        action = pending.get("action", "")

        if action == "prior_auth_submit":
            form = prior_auth.generate_prior_auth_form(
                pending["patient_data"],
                pending["treatment"],
                pending["diagnosis"],
            )
            return prior_auth.format_prior_auth_summary(form)

        elif action == "referral_create":
            task = scheduling.create_referral(
                pending["patient_id"],
                "General Specialist",
                patient_name=pending.get("patient_name", ""),
            )
            return f"👨‍⚕️ Referral created: {task['task_id']}\n{task['description']}"

        return "Approved action executed."

    # ── Perception helpers (optional) ────────────────────────────────

    def start_perception(self):
        """Start screen/audio perception if enabled in Config."""
        if not (Config.ENABLE_SCREEN_CAPTURE or Config.ENABLE_AUDIO):
            return None
        try:
            from ui.widget import Widget
        except Exception:
            return None

        self._perception_widget = Widget(
            image_callback=(self._on_image if Config.ENABLE_SCREEN_CAPTURE else None),
            audio_callback=(self._on_audio if Config.ENABLE_AUDIO else None),
            ocr_callback=(self._on_ocr if Config.ENABLE_OCR else None),
            image_interval=1.0,
            audio_interval=1.0,
            audio_duration=0.5,
        )
        try:
            self._perception_widget.start()
            return self._perception_widget
        except Exception:
            return None

    def stop_perception(self):
        try:
            if getattr(self, "_perception_widget", None):
                self._perception_widget.stop()
                self._perception_widget = None
        except Exception:
            pass

    def _on_image(self, img):
        try:
            if self.memory:
                self.memory.remember("screenshot", f"<image {img.size}>")
        except Exception:
            pass

    def _on_audio(self, data, sr):
        try:
            if self.memory:
                self.memory.remember("audio_snippet", f"<audio {len(data)} samples>")
        except Exception:
            pass

    def _on_ocr(self, text: str):
        try:
            if self.memory:
                self.memory.remember("ocr", text)
        except Exception:
            pass


agent = Agent()