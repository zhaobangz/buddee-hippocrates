from typing import Dict, Any
import json
from openai import OpenAI
from app.core.config import settings
from app.agents.rag import rag_engine

class Orchestrator:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def route_intent(self, message: str) -> Dict[str, Any]:
        """Detect intent and route to appropriate tool."""
        prompt = f"""
        Analyze the clinical query and determine the intent.
        Available intents: 
        - CLINICAL_CHAT: General medical questions or patient context discussion.
        - RISK_ANALYSIS: Questions about patient stability, scores, or labs.
        - WORKFLOW_AUTO: Prior auth, scheduling, or documentation tasks.
        - SAFETY_VIOLATION: Diagnosis or prescription requests (to be blocked).

        Query: {message}
        
        Return JSON format: {{"intent": "INTENT_NAME", "confidence": 0.9, "requires_rag": true}}
        """
        
        # In production, use structured output or a cheaper model for routing
        response = self.client.chat.completions.create(
            model="gpt-3.5-turbo", # Small fast model for routing
            messages=[{"role": "system", "content": "You are a clinical intent router."},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        
        return json.loads(response.choices[0].message.content)

    async def execute(self, message: str, patient_context: Dict[str, Any] = None) -> Dict[str, Any]:
        intent_info = self.route_intent(message)
        intent = intent_info["intent"]
        
        # SAFETY GATE
        if intent == "SAFETY_VIOLATION":
            return {
                "response": "As an AI clinical assistant, I cannot provide diagnoses or prescribe medications. Please consult the attending physician.",
                "intent_detected": intent,
                "confidence_score": 1.0
            }

        # RAG Grounding
        context_str = ""
        citations = []
        if intent_info.get("requires_rag"):
            search_results = rag_engine.retrieve(message)
            context_str = "\n".join([r["content"] for r in search_results])
            citations = [r["content"][:100] + "..." for r in search_results]

        # Final LLM Execution
        full_prompt = f"""
        Role: Staff Physician Assistant.
        Context: {patient_context}
        Clinical Guidelines: {context_str}
        
        User Query: {message}
        
        Instruction: Provide a concise, clinically relevant response. Cite guidelines where possible.
        """
        
        final_resp = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": full_prompt}]
        )
        
        return {
            "response": final_resp.choices[0].message.content,
            "intent_detected": intent,
            "citations": citations,
            "confidence_score": intent_info["confidence"]
        }

orchestrator = Orchestrator()
