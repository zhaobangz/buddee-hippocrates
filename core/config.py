"""
Buddi System Configuration v3
Minimal footprint.
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Identity ---
    ASSISTANT_NAME = "Buddi Clinical Agent"
    VERSION = "3.0.0"

    # --- LLM ---
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
    LLM_API_URL = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4-turbo")

    # --- Storage ---
    MEMORY_ENABLED = True
    MAX_MEMORY_HISTORY = 10
    STORAGE_DIR = "data"
    
    # --- Infrastructure ---
    BACKEND_PORT = 8001
    FRONTEND_PORT = 5173

    # --- Safety & Audit ---
    ENABLE_AUDIT_LOG = True
    AUDIT_LOG_FILE = "audit_log.json"
    ENABLE_SAFETY_LAYER = True
    REQUIRE_HUMAN_APPROVAL = True
