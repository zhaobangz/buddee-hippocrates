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
