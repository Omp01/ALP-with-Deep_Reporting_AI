"""
API Service configuration.

All settings are loaded from environment variables.
Secrets are never hard-coded.
"""
from pathlib import Path
from pydantic_settings import BaseSettings

_root_env = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    """API Service configuration loaded from environment."""

    # Database
    database_url: str = "postgresql+asyncpg://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"
    database_url_sync: str = "postgresql://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"

    # Redis
    redis_url: str = "redis://127.0.0.1:6379/0"

    # MinIO
    minio_endpoint: str = "127.0.0.1:9000"
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

    # Task-specific model overrides (empty = use ai_model). Lets a cheap model do extraction
    # while a stronger one writes questions, or the reverse.
    ai_model_analysis: str = ""
    ai_model_questions: str = ""
    # Local model server (Ollama). Used when ai_provider == "ollama"; no API key is needed.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1"
    # Embeddings are optional. Set a model name to enable the stage.
    ai_embedding_model: str = ""

    # Gemini & Groq settings
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Internal services
    adaptive_engine_url: str = "http://127.0.0.1:8001"
    reporting_engine_url: str = "http://127.0.0.1:8002"
    ingestion_service_url: str = "http://127.0.0.1:8003"

    # Browser origins allowed to call the API (comma-separated).
    cors_origins: str = "http://localhost:3000,http://frontend:3000"

    # Logging
    log_level: str = "INFO"

    # Upload limits
    max_upload_size_mb: int = 100
    allowed_file_types: str = "pdf,docx,pptx,txt,md,mp4,webm,mov,mp3,wav,m4a"

    # Content ingestion pipeline
    ingestion_run_inline: bool = False        # run the pipeline inside the request (used by tests)
    ingestion_max_analysis_chars: int = 12000  # how much of a document the model sees per call
    ingestion_question_count: int = 6          # questions requested per item
    ingestion_min_text_chars: int = 200        # less text than this is not analysable
    ingestion_stale_minutes: int = 15          # a "processing" job older than this is marked interrupted
    whisper_model: str = "base"                # faster-whisper model used if that package is installed

    # Object storage authentication (see services/s3-storage). Defaults to the MinIO secret.
    storage_token: str = ""

    # Redis streams
    event_stream_name: str = "learning_events"

    # Competency engine (docs/COMPETENCY_ENGINE.md). Every constant of the mastery update is here and is stored with each update.
    mastery_prior: float = 0.20
    mastery_learn: float = 0.15
    mastery_slip: float = 0.10
    mastery_guess: float = 0.20
    mastery_retry_weight: float = 0.60
    mastery_confidence_k: float = 3.0
    mastery_trend_window: int = 5
    mastery_trend_min_updates: int = 3
    mastery_trend_threshold: float = 0.05

    # Written-answer grading (docs/GRADING_AGENT.md)
    ai_model_grading: str = ""                    # empty = the provider's default model
    grading_timeout_seconds: int = 90             # per written answer; on timeout the answer goes to a person
    grading_min_confidence: float = 0.60          # below this a grade is not used as evidence until a person confirms it
    grading_correct_threshold: float = 0.70       # signal at or above this shows as "correct" (partial credit is still given)
    grading_max_answer_chars: int = 6000

    # Reporting AI (docs/REPORTING_AI.md)
    ai_model_reporting: str = ""                  # empty = the provider's default model
    reporting_timeout_seconds: int = 120
    reporting_period_days: int = 30
    reporting_cache_minutes: int = 30             # an identical evidence package within this window reuses the stored report
    reporting_min_responses_per_question: int = 5 # fewer answers than this never make a question a 'stuck point'
    reporting_min_learners_for_content: int = 3   # fewer learners than this never make a content-effectiveness claim
    report_scheduler_enabled: bool = False        # run due scheduled reports in the background
    report_scheduler_interval_seconds: int = 300

    # Learning events and sessions
    session_idle_minutes: int = 30              # a session with no activity for this long is closed at its last activity
    event_dispatcher_enabled: bool = True       # publish committed events to the stream in the background
    event_dispatch_interval_seconds: float = 2.0
    event_max_client_batch: int = 50
    event_client_clock_skew_seconds: int = 120  # a browser timestamp this far ahead of the server is not believed
    event_client_max_age_hours: int = 24        # ... nor one older than this

    model_config = {"env_file": (str(_root_env), ".env"), "case_sensitive": False, "extra": "ignore"}


settings = Settings()
