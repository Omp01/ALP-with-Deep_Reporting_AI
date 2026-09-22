"""
Adaptive Engine configuration and hyperparameter settings.
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
    """Adaptive Engine service settings."""
    database_url: str = "postgresql+asyncpg://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"
    redis_url: str = "redis://127.0.0.1:6379/0"
    log_level: str = "INFO"
    event_stream_name: str = "learning_events"

    # Competency Mastery Hyperparameters
    w_correct: float = 0.40
    w_diff: float = 0.15
    w_recency: float = 0.15
    w_error: float = 0.15
    w_consist: float = 0.15
    required_evidence_count: int = 10

    # Policy Thresholds
    remediation_threshold: float = 0.45
    advancement_mastery_threshold: float = 0.80
    advancement_confidence_threshold: float = 0.70
    skip_mastery_threshold: float = 0.75
    skip_consecutive_correct: int = 3

    model_config = {"env_file": (str(_root_env), ".env"), "case_sensitive": False, "extra": "ignore"}


settings = Settings()
