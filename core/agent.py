"""
Buddi Agent Orchestrator v3.2
Lean, intent-driven clinical logic with RAG and Tracing.
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

    def handle(self, user_input: str) -> str:
        """Single entry point for clinical reasoning."""
        with tracer.start_as_current_span("agent_handle") as span:
            span.set_attribute("user_input", user_input)
            
            # 1. Detect Intent
            intent = self._detect_intent(user_input)
            span.set_attribute("detected_intent", intent)
            
            # 2. Extract context
            ctx = self.memory.get_patient_context() if self.memory else {}
            
            # 3. Route & Execute
            try:
                if intent == "patient_brief":
                    return ehr_reader.generate_patient_brief(ctx)
                
                if intent == "prior_auth":
                    res = clinical_workflows.generate_prior_auth(ctx, "Requested Therapy")
                    return f"✅ Prior Auth Generated: {res['id']}\nJustification: {res['justification']}"
                    
                if intent == "schedule":
                    res = clinical_workflows.schedule_action(ctx.get('patient_id', 'AUTO'), "Clinic Visit")
                    return f"📅 Appointment Scheduled: {res['task_id']} for {res['scheduled_date']}"

                # 4. Clinical RAG + QA
                return self._clinical_qa_with_rag(user_input, ctx)
            except Exception as e:
                span.record_exception(e)
                return f"Internal Clinical Processing Error: {str(e)}"

    def _detect_intent(self, ui: str) -> str:
        with tracer.start_as_current_span("detect_intent"):
            prompt = f"Target: {ui}\nIntents: [patient_brief, prior_auth, schedule, medical_query]\nRespond with category only."
            return self.llm.ask_llm(prompt).strip().lower()

    def _clinical_qa_with_rag(self, ui: str, ctx: dict) -> str:
        with tracer.start_as_current_span("rag_qa") as span:
            # Search guidelines
            docs = self.rag.search(ui, top_k=2)
            span.set_attribute("rag_docs_found", len(docs))
            
            guideline_context = ""
            if docs:
                guideline_context = "\nRelevant Clinical Guidelines:\n" + "\n".join([f"- {d['text']} (Source: {d['source']})" for d in docs])

            system = "You are Buddi, a Clinical Decision Support assistant. Use the provided guidelines if relevant."
            if ctx: system += f" Active Patient: {ctx.get('name')} ({ctx.get('conditions')})"
            
            full_prompt = f"{system}\n{guideline_context}\n\nUser Query: {ui}"
            return self.llm.ask_llm(full_prompt)