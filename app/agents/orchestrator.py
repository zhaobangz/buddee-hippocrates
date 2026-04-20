from typing import Dict, Any
import json
from openai import OpenAI
from app.core.config import settings
from app.agents.rag import rag_engine
from core.database import SessionLocal
from core.models import LlmRequest, LlmResponse
import logging

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        try:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        except Exception as e:
            self.client = None
            logger.warning("Failed to init OpenAI client.")

    def route_intent(self, message: str) -> Dict[str, Any]:
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

        if not self.client:
            return {"intent": "CLINICAL_CHAT", "requires_rag": False, "confidence": 1.0}

        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "You are a clinical intent router."},
                          {"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
             return {"intent": "CLINICAL_CHAT", "requires_rag": False, "confidence": 1.0}

    async def execute(self, message: str, patient_context: Dict[str, Any] = None) -> Dict[str, Any]:
        intent_info = self.route_intent(message)
        intent = intent_info.get("intent", "CLINICAL_CHAT")

        # SAFETY GATE
        if intent == "SAFETY_VIOLATION":
            return {
                "response": "As an AI clinical assistant, I cannot provide diagnoses or prescribe medications.",
                "intent_detected": intent,
                "confidence_score": 1.0
            }

        # RAG Grounding
        context_str = ""
        citations = []
        if intent_info.get("requires_rag"):
            search_results = rag_engine.retrieve(message)
            context_str = "\n".join([r["content"] for r in search_results])
            citations = [r.get("chunk_id", "doc") for r in search_results]

        full_prompt = f"""
        Role: Staff Physician Assistant.
        Context: {patient_context}
        Clinical Guidelines: {context_str}

        User Query: {message}

        Instruction: Provide a concise, clinically relevant response.
        """

        # Postgres Traceability
        db = SessionLocal()
        try:
            request_log = LlmRequest(
                model=getattr(settings, "LLM_MODEL", "gpt-4"),
                full_prompt=full_prompt
            )
            db.add(request_log)
            db.commit()
            db.refresh(request_log)

            final_resp = None
            if self.client:
                final_resp = self.client.chat.completions.create(
                    model=getattr(settings, "LLM_MODEL", "gpt-4"),
                    messages=[{"role": "user", "content": full_prompt}]
                )
                response_text = final_resp.choices[0].message.content

                response_log = LlmResponse(
                    llm_request_id=request_log.id,
                    raw_response=response_text,
                    tokens_used=final_resp.usage.total_tokens if final_resp.usage else 0
                )
                db.add(response_log)
                db.commit()
            else:
                response_text = "Mock LLM output due to missing API configurations."

            return {
                "response": response_text,
                "intent_detected": intent,
                "citations": citations,
                "confidence_score": intent_info.get("confidence", 1.0)
            }
        except Exception as e:
            logger.error(f"Orchestrator DB or Runtime failed: {e}")
            db.rollback()
            return {"response": "System error. Database transaction or LLM call failed.", "intent_detected": intent, "confidence_score": 0.0}
        finally:
            db.close()

orchestrator = Orchestrator()
