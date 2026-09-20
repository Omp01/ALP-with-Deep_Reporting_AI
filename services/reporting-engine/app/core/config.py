"""
Reporting Engine configuration and settings.
"""
from pathlib import Path
from pydantic_settings import BaseSettings

_root_env = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Reporting Engine service configuration."""
    database_url: str = "postgresql+asyncpg://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"
    redis_url: str = "redis://127.0.0.1:6379/0"
    log_level: str = "INFO"

    # AI Provider settings
    ai_provider: str = "openai_compatible"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: int = 30

    # Gemini & Groq settings
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    model_config = {"env_file": (str(_root_env), ".env"), "case_sensitive": False, "extra": "ignore"}


settings = Settings()
