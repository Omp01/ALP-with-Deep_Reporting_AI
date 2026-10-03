"""
Pydantic schemas for Psychometric Questions, In-Course Micro-Prompts,
Confidence-Performance Gap Calibration, Learning Evidence Index (LEI),
and Course Effectiveness Analytics.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class PsychometricQuestionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: Optional[UUID] = None
    module_id: Optional[UUID] = None
    content_item_id: Optional[UUID] = None
    topic: Optional[str] = None
    construct: str
    learning_stage: str
    question_text: str
    scale_type: str = "likert_5"
    scale_min: int = 1
    scale_max: int = 5
    scale_labels: List[str]
    higher_is_favorable: bool = True
    version: str = "1.0.0"
    order_index: int = 0


class PsychometricResponseSubmit(BaseModel):
    question_id: UUID
    course_id: Optional[UUID] = None
    content_item_id: Optional[UUID] = None
    topic: Optional[str] = None
    raw_response: float = Field(..., ge=1.0, le=10.0, description="Raw rating submitted by learner (e.g. 1..5)")
    context_metadata: Optional[Dict[str, Any]] = None


class PsychometricResponseReceipt(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_id: UUID
    construct: str
    learning_stage: str
    raw_response: float
    normalized_score: float
    calibration_gap: Optional[float] = None
    alignment_quadrant: Optional[str] = None
    feedback_message: Optional[str] = None
    methodology_version: str = "1.0.0"
    submitted_at: datetime


class TopicProgressionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    topic: str
    confidence_score: float
    performance_score: float
    first_attempt_acc: float
    gap: float
    alignment_quadrant: str
    feedback_recommendation: str
    recorded_at: datetime


class LearningEvidenceIndexDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lei_score: float = Field(..., ge=0.0, le=100.0)
    formula_id: str = "lei_multimodal_v1"
    formula_version: str = "1.0.0"
    components: Dict[str, float]
    weights_used: Dict[str, float]
    formula_expression: str
    explanation: str


class LearnerCalibrationReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    user_name: str
    overall_confidence: float
    overall_performance: float
    overall_gap: float
    calibration_quadrant: str
    lei_detail: LearningEvidenceIndexDetail
    topic_calibrations: List[Dict[str, Any]] = []
    progression_timeline: List[TopicProgressionItem] = []
    neutral_recommendations: List[str] = []


class CourseEffectivenessTopic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: Optional[UUID] = None
    course_title: str
    topic: str
    cohort_size: int = 0
    avg_difficulty: float = 0.0
    avg_confidence: float = 0.0
    avg_performance: float = 0.0
    content_friction_index: float = 0.0
    is_flagged_for_improvement: bool = False
    observation_note: str = ""
    recommended_action: str = ""


class ManagerPsychometricsEffectivenessReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_courses_evaluated: int = 0
    total_topics_evaluated: int = 0
    flagged_topics_count: int = 0
    cohort_calibration_distribution: Dict[str, int] = {}
    flagged_improvement_topics: List[CourseEffectivenessTopic] = []
    all_topic_evaluations: List[CourseEffectivenessTopic] = []
