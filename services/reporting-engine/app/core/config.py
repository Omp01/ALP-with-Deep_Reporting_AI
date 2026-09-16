"""
Reporting Engine configuration and settings.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Reporting Engine service configuration."""
    database_url: str = "postgresql+asyncpg://adaptive_lms:adaptive_lms_dev_password@postgres:5432/adaptive_lms"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"

    # AI Provider settings
    ai_provider: str = "openai_compatible"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: int = 30

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
