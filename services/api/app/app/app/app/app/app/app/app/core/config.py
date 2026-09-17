"""
API Service configuration.

All settings are loaded from environment variables.
Secrets are never hard-coded.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """API Service configuration loaded from environment."""

    # Database
    database_url: str = "postgresql+asyncpg://adaptive_lms:adaptive_lms_dev_password@postgres:5432/adaptive_lms"
    database_url_sync: str = "postgresql://adaptive_lms:adaptive_lms_dev_password@postgres:5432/adaptive_lms"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin_secret"
    minio_bucket: str = "adaptive-lms-content"
    minio_use_ssl: bool = False

    # JWT
    jwt_secret: str = "change-this-to-a-random-64-char-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # AI
    ai_provider: str = "openai_compatible"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: int = 30
    ai_max_retries: int = 3

    # Internal services
    adaptive_engine_url: str = "http://adaptive-engine:8001"
    reporting_engine_url: str = "http://reporting-engine:8002"
    ingestion_service_url: str = "http://ingestion:8003"

    # Logging
    log_level: str = "INFO"

    # Upload limits
    max_upload_size_mb: int = 100
    allowed_file_types: str = "pdf,pptx,ppt,docx,doc,mp3,mp4"

    # Redis streams
    event_stream_name: str = "learning_events"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
