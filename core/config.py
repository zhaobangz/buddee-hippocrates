# config.py
import os
import json
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Try to get API key from environment variable first
    DEEPSEEK_API_KEY = os.getenv("put a general api key here")
    
    # Fallback to credentials.json if environment variable not set
    if not DEEPSEEK_API_KEY and os.path.exists("credentials.json"):
        try:
            with open("credentials.json", "r") as f:
                credentials = json.load(f)
                DEEPSEEK_API_KEY = credentials.get("api_key")
        except:
            pass
            
    MAX_MEMORY_HISTORY = int(os.getenv("MAX_MEMORY_HISTORY", 10))
    ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Buddi")
    USE_VOICE = os.getenv("USE_VOICE", "False").lower() == "true"
    MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "True").lower() == "true"
