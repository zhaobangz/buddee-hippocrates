from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Buddi Clinical Agent"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = "super-secret-key-for-jwt-change-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # LLM Settings
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4-turbo-preview"
    
    # Vector DB
    VECTOR_DB_PATH: str = "./data/chroma"
    
    # Clinical Safety
    SAFETY_LOG_PATH: str = "./logs/audit.json"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
