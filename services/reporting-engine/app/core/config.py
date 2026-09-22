"""
Reporting Engine configuration and settings.
"""
from pathlib import Path
from pydantic_settings import BaseSettings

def _find_env_file() -> Path:
    cur = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = cur / ".env"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(".env")


_root_env = _find_env_file()


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
