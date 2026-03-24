# core/memory.py
# Keeps history of interactions plus patient and provider context.
# Provides context to the LLM for better clinical responses.

import json
import os
from typing import Any, Dict, List, Optional


class Memory:
    def __init__(self, max_history: int = 10, persist_file: str = "memory.json"):
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history
        self.persist_file = persist_file

        # Patient context — current patient being discussed / worked on
        self.patient_context: Dict[str, Any] = {}

        # Provider context — doctor preferences, clinic workflows
        self.provider_context: Dict[str, Any] = {}

        self.load_memory()

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def remember(self, ui: str, response: str) -> None:
        self.history.append({"user": ui, "assistant": response})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self.save_memory()

    def recall(self, num_interactions: int = 5) -> List[Dict[str, str]]:
        return self.history[-num_interactions:] if self.history else []

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.history = []
        self.save_memory()

    # ------------------------------------------------------------------
    # Patient context
    # ------------------------------------------------------------------

    def set_patient_context(
        self,
        patient_id: str,
        name: str = "",
        conditions: Optional[List[str]] = None,
        medications: Optional[List[str]] = None,
        allergies: Optional[List[str]] = None,
        notes: str = "",
        **extra: Any,
    ) -> None:
        """Set the current patient context for the session."""
        self.patient_context = {
            "patient_id": patient_id,
            "name": name,
            "conditions": conditions or [],
            "medications": medications or [],
            "allergies": allergies or [],
            "notes": notes,
            **extra,
        }
        self.save_memory()

    def get_patient_context(self) -> Dict[str, Any]:
        return self.patient_context

    def clear_patient_context(self) -> None:
        self.patient_context = {}
        self.save_memory()

    # ------------------------------------------------------------------
    # Provider context
    # ------------------------------------------------------------------

    def set_provider_context(
        self,
        provider_id: str,
        name: str = "",
        specialty: str = "",
        clinic: str = "",
        preferences: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> None:
        """Set the provider (doctor/clinic) context for the session."""
        self.provider_context = {
            "provider_id": provider_id,
            "name": name,
            "specialty": specialty,
            "clinic": clinic,
            "preferences": preferences or {},
            **extra,
        }
        self.save_memory()

    def get_provider_context(self) -> Dict[str, Any]:
        return self.provider_context

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_memory(self) -> None:
        try:
            data = {
                "history": self.history,
                "patient_context": self.patient_context,
                "provider_context": self.provider_context,
            }
            with open(self.persist_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error Saving Memory to Disk: {e}")

    def load_memory(self) -> None:
        if os.path.exists(self.persist_file):
            try:
                with open(self.persist_file, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # Legacy format: plain history list
                    self.history = data
                elif isinstance(data, dict):
                    self.history = data.get("history", [])
                    self.patient_context = data.get("patient_context", {})
                    self.provider_context = data.get("provider_context", {})
            except Exception as e:
                print(f"Error Loading Memory: {e}")
                self.history = []


memory = Memory()