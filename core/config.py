# core/config.py
import os
import json
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration for the agent and optional features.

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
    ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Buddi")
    MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "True").lower() == "true"

    # Perception features
    ENABLE_SCREEN_CAPTURE = os.getenv("ENABLE_SCREEN_CAPTURE", "False").lower() == "true"
    ENABLE_OCR = os.getenv("ENABLE_OCR", "False").lower() == "true"
    ENABLE_AUDIO = os.getenv("ENABLE_AUDIO", "False").lower() == "true"

    # Tools and extensibility
    ENABLE_WEB_BROWSING = os.getenv("ENABLE_WEB_BROWSING", "True").lower() == "true"
    ENABLE_FILE_MANAGER = os.getenv("ENABLE_FILE_MANAGER", "True").lower() == "true"
    ENABLE_SYSTEM_SEARCH = os.getenv("ENABLE_SYSTEM_SEARCH", "True").lower() == "true"

    # Local persistence paths
    MEMORY_PERSIST_FILE = os.getenv("MEMORY_PERSIST_FILE", "memory.json")

    # Convenience flags
    USE_VOICE = os.getenv("USE_VOICE", "False").lower() == "true"

