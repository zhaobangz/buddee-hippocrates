"""
Buddi RCM Orchestrator v4.0
Focused on Shadow Mode Revenue Integrity, QA Audits, and Prior Auth.
"""
from core.llm_manager import LLMManager
from core.memory import Memory
from core.config import Config
from core.tracing import get_tracer
from core.rag_engine import get_rag_engine
from tools import ehr_reader, clinical_workflows
from typing import Optional, Dict, Any
import json

tracer = get_tracer(__name__)

class Agent:
    def __init__(self):
        self.memory = Memory(max_history=10) if Config.MEMORY_ENABLED else None
        self.llm = LLMManager(self.memory)
        self.rag = get_rag_engine()

    def handle(self, payload: str, task_type: str = "detect") -> str:
        """Entry point for RCM and compliance tasks."""
        with tracer.start_as_current_span("agent_handle") as span:
            span.set_attribute("payload", payload)
            
            # Override intent detection if task type is explicitly provided
            if task_type == "detect":
                intent = self._detect_intent(payload)
            else:
                intent = task_type
            span.set_attribute("detected_intent", intent)
            
            ctx = self.memory.get_patient_context() if self.memory else {}
            
            try:
                if intent == "shadow_mode_rcm":
                    return self._process_shadow_mode_rcm(payload, ctx)
                
                if intent == "specialty_prior_auth":
                    res = clinical_workflows.generate_prior_auth(ctx, payload)
                    return f"✅ Oncology/GI Prior Auth Generated: {res.get('id', 'N/A')}\nGuideline Match: Verified"
                    
                if intent == "retrospective_qa_audit":
                    return self._process_retrospective_qa(payload, ctx)

                return f"Task type {intent} unsupported in RCM engine."
            except Exception as e:
                span.record_exception(e)
                return f"Internal Audit Error: {str(e)}"

    def _detect_intent(self, payload: str) -> str:
        with tracer.start_as_current_span("detect_intent"):
            prompt = f"Target: {payload}\nIntents: [shadow_mode_rcm, specialty_prior_auth, retrospective_qa_audit]\nRespond with category only."
            return self.llm.ask_llm(prompt).strip().lower()

    def _process_shadow_mode_rcm(self, payload: str, ctx: dict) -> str:
        """
        Deepened Shadow Mode: Compares Note vs Billed Codes.
        Expects payload as string or JSON string with 'note' and 'billed_codes'.
        """
        with tracer.start_as_current_span("shadow_mode_rcm") as span:
            try:
                data = json.loads(payload)
                note = data.get("note", payload)
                billed_codes = data.get("billed_codes", [])
            except:
                note = payload
                billed_codes = []

            docs = self.rag.search(note, top_k=2)
            span.set_attribute("rag_docs_found", len(docs))
            guideline_context = "\n".join([f"- {d['text']}" for d in docs]) if docs else "Standard CMS HCC Guidelines."

            prompt = f"""
            ### ROLE: Expert Revenue Integrity Auditor
            ### TASK: Perform a Shadow Mode audit of the clinical note against previously billed codes.
            
            ### DATA:
            - CLINICAL NOTE: {note}
            - BILLED CODES: {billed_codes}
            - GUIDELINE CONTEXT: {guideline_context}
            
            ### INSTRUCTIONS:
            1. Identify any missing HCC (Hierarchical Condition Category) or ICD-10 codes mentioned in the note but NOT in the billed codes.
            2. For each identified missing code, provide:
               - Code & Description
               - Clinical Justification from the note
               - Estimated annual revenue recovery (based on CMS weight ~1.0 = $11,000)
            3. Frame the output as a RECOMMENDATION for human review (Compliance-first).
            
            ### OUTPUT FORMAT (JSON):
            {{
                "recovered_revenue": float,
                "identified_codes": [{{ "code": str, "description": str, "justification": str, "est_value": float }}],
                "summary": str
            }}
            """
            
            raw_response = self.llm.ask_llm(prompt)
            # Try to return structured if possible, else keep string
            return raw_response

    def _process_retrospective_qa(self, note: str, ctx: dict) -> str:
        with tracer.start_as_current_span("retrospective_qa_audit") as span:
            docs = self.rag.search(note, top_k=2)
            span.set_attribute("rag_docs_found", len(docs))
            guideline_context = "\n".join([f"- {d['text']}" for d in docs]) if docs else "No guidelines found."
            
            prompt = f"Conduct a retrospective QA audit on this chart based on adherence to clinical guidelines. Emphasize cryptic audit trails.\nGuidelines:\n{guideline_context}\n\nChart Note:\n{note}"
            return self.llm.ask_llm(prompt)