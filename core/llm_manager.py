"""
Buddi LLM Manager — Lean v3
Simplified adapter for healthcare-grade LLMs.
"""
import requests
from core.config import Config

class LLMManager:
    def __init__(self, memory=None):
        self.memory = memory

    def ask_llm(self, prompt: str) -> str:
        """Simple API-based LLM call."""
        if not Config.LLM_API_KEY:
            return "Error: LLM API Key not configured."
            
        headers = {"Authorization": f"Bearer {Config.LLM_API_KEY}"}
        payload = {
            "model": Config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        
        try:
            r = requests.post(Config.LLM_API_URL, json=payload, headers=headers, timeout=10)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Clinical LLM Connection Error: {str(e)}"

    def ask_llm_structured(self, prompt: str, schema) -> any:
        """API-based LLM call enforcing structured output via Pydantic schema."""
        if not Config.LLM_API_KEY:
            raise ValueError("Error: LLM API Key not configured.")
            
        headers = {"Authorization": f"Bearer {Config.LLM_API_KEY}"}
        
        # Inject JSON schema instructions into prompt
        prompt_with_schema = prompt + f"\n\nCRITICAL: Return a valid JSON object EXACTLY adhering to this schema:\n{schema.model_json_schema()}"
        
        payload = {
            "model": Config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt_with_schema}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        try:
            r = requests.post(Config.LLM_API_URL, json=payload, headers=headers, timeout=15)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            # Validate and parse the string back into the Pydantic class map
            return schema.model_validate_json(content)
        except Exception as e:
            raise RuntimeError(f"Structured Parsing Error: {str(e)}")
