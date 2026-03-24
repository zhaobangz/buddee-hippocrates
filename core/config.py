# core/config.py
import os
import json
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration for the clinical agent and optional features.

    Values are read from environment variables first, then from a
    credentials.json file in the repo root (if present). Reasonable defaults
    are provided for local development.
    """

    # LLM provider configuration
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v3-chat-standard")

    # Try fallback to credentials.json if API key not set
    if not LLM_API_KEY and os.path.exists("config/credentials.json"):
        try:
            with open("config/credentials.json", "r") as f:
                credentials = json.load(f)
                LLM_API_KEY = credentials.get("api_key") or credentials.get("llm_api_key")
        except Exception:
            LLM_API_KEY = None

    # Memory and assistant identity
    MAX_MEMORY_HISTORY = int(os.getenv("MAX_MEMORY_HISTORY", 50))
    ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Buddi Clinical Agent")
    MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "True").lower() == "true"

    # Perception features
    ENABLE_SCREEN_CAPTURE = os.getenv("ENABLE_SCREEN_CAPTURE", "False").lower() == "true"
    ENABLE_OCR = os.getenv("ENABLE_OCR", "False").lower() == "true"
    ENABLE_AUDIO = os.getenv("ENABLE_AUDIO", "False").lower() == "true"

    # Healthcare medical tools
    ENABLE_EHR_READER = os.getenv("ENABLE_EHR_READER", "True").lower() == "true"
    ENABLE_PRIOR_AUTH = os.getenv("ENABLE_PRIOR_AUTH", "True").lower() == "true"
    ENABLE_CLINICAL_GUIDELINES = os.getenv("ENABLE_CLINICAL_GUIDELINES", "True").lower() == "true"
    ENABLE_FOLLOW_UP = os.getenv("ENABLE_FOLLOW_UP", "True").lower() == "true"
    ENABLE_SCHEDULING = os.getenv("ENABLE_SCHEDULING", "True").lower() == "true"

    # Safety and compliance
    ENABLE_SAFETY_LAYER = os.getenv("ENABLE_SAFETY_LAYER", "True").lower() == "true"
    ENABLE_AUDIT_LOG = os.getenv("ENABLE_AUDIT_LOG", "True").lower() == "true"
    REQUIRE_HUMAN_APPROVAL = os.getenv("REQUIRE_HUMAN_APPROVAL", "True").lower() == "true"
    AUDIT_LOG_FILE = os.getenv("AUDIT_LOG_FILE", "audit_log.json")

    # Local persistence paths
    MEMORY_PERSIST_FILE = os.getenv("MEMORY_PERSIST_FILE", "memory.json")

    # Convenience flags
    USE_VOICE = os.getenv("USE_VOICE", "False").lower() == "true"
    # Device preferences
    # Set FORCE_CPU=True to prevent GPU usage even when available
    FORCE_CPU = os.getenv("FORCE_CPU", "False").lower() == "true"
    # PREFERRED_DEVICE can be 'auto', 'cuda', 'mps', or 'cpu'
    PREFERRED_DEVICE = os.getenv("PREFERRED_DEVICE", "auto").lower()
