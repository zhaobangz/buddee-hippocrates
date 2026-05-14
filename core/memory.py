"""
Buddi Memory — Lean v3
Volatile and simple context management.
"""
# TODO(human): Memory is volatile and per-request. For multi-turn clinical
# conversations, replace with a Redis-backed session store keyed on
# (tenant_id, session_id). Current behaviour: every HTTP request sees an
# empty history.
from typing import Any, Dict, List, Optional
import json
import os

class Memory:
    def __init__(self, max_history: int = 10):
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history
        self.patient_context: Dict[str, Any] = {}

    def remember(self, ui: str, bot: str):
        self.history.append({"user": ui, "bot": bot})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def recall(self, num_interactions: int = 5) -> List[Dict[str, str]]:
        return self.history[-num_interactions:]

    def set_patient_context(self, **data):
        self.patient_context.update(data)

    def get_patient_context(self) -> Dict[str, Any]:
        return self.patient_context

    def clear_patient_context(self):
        self.patient_context = {}
        self.history = []
