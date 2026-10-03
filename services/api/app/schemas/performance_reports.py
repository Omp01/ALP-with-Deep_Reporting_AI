"""
Pydantic schemas for Learner & Manager Performance Reports,
Score Transparency, and Remediation Traceability.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.video_checkpoint import CheckpointRemediation


class ScoreTransparencyInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    formula_id: str = "attempt_decay_v1"
    formula_version: str = "1.0.0"
    max_marks: float = 10.0
    attempt_number: int = 1
    penalty_p: float = 0.25
    attempt_factor: float = 1.0
    accuracy_factor: float = 1.0
    formula_expression: str = ""
    marks_awarded: float = 10.0
    reason: str = ""


class QuestionAttemptItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    assessment_type: str = Field(..., description="flashcard | quiz | assignment")
    topic: Optional[str] = None
    attempts: int = 1
    first_attempt_correct: bool = True
    score: float = 0.0
    max_score: float = 10.0
    status: str = "completed"
    answered_at: Optional[datetime] = None
    calculation_details: Optional[Dict[str, Any]] = None
    remediation: Optional[CheckpointRemediation] = None


class TopicMasteryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic: str
    mastery_percent: float = Field(..., ge=0.0, le=100.0)
    total_questions: int = 0
    correct_count: int = 0
    average_attempts: float = 1.0
    status: str = Field("developing", description="strong | developing | weak")


from app.schemas.psychometrics import LearningEvidenceIndexDetail


class LearnerPerformanceReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    user_name: str
    user_email: Optional[str] = None
    course_id: Optional[UUID] = None
    course_title: Optional[str] = None
    
    # Composite scores
    overall_score: float = Field(..., ge=0.0, le=100.0)
    quiz_score: Optional[float] = None
    assignment_score: Optional[float] = None
    flashcard_score: Optional[float] = None
    weights_used: Dict[str, float] = {}

    # Learning Evidence Index & Metacognitive Calibration
    lei_score: Optional[float] = None
    lei_detail: Optional[LearningEvidenceIndexDetail] = None
    confidence_score: Optional[float] = None
    confidence_gap: Optional[float] = None
    calibration_quadrant: Optional[str] = "calibrated_mastery"
    neutral_recommendation: Optional[str] = None

    # Attempt & accuracy metrics
    first_attempt_accuracy: float = Field(..., ge=0.0, le=100.0)
    average_attempts: float = 1.0
    total_items_attempted: int = 0
    questions_requiring_retries: int = 0

    # Topic breakdown
    topic_mastery: List[TopicMasteryItem] = []
    strong_topics: List[str] = []
    weak_topics: List[str] = []
    improvement_trend: str = Field("stable", description="improving | stable | declining")

    # Full drill-down history with explainable calculation snapshots
    attempt_history: List[QuestionAttemptItem] = []


class ManagerCohortLearnerSummary(BaseModel):
    user_id: UUID
    user_name: str
    user_email: Optional[str] = None
    overall_score: float = 0.0
    first_attempt_accuracy: float = 0.0
    average_attempts: float = 1.0
    items_completed: int = 0
    status: str = "on_track"  # on_track | at_risk | needs_review


class CohortWeakTopic(BaseModel):
    topic: str
    struggling_learner_count: int = 0
    avg_attempts: float = 1.0
    avg_accuracy: float = 0.0


class ManagerCohortPerformanceReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cohort_size: int = 0
    avg_overall_score: float = 0.0
    avg_first_attempt_accuracy: float = 0.0
    avg_attempts_per_item: float = 1.0
    cohort_calibration_distribution: Dict[str, int] = {}
    flagged_topics_count: int = 0
    
    learners_requiring_attention: List[ManagerCohortLearnerSummary] = []
    cohort_weak_topics: List[CohortWeakTopic] = []
    learner_roster: List[ManagerCohortLearnerSummary] = []

