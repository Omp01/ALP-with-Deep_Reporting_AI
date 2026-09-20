"""
Pydantic schemas for Quizzes, Questions, Options, Attempts, and Grading.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Options & Questions
# -----------------------------------------------------------------------------
class QuizOptionResponse(BaseModel):
    id: UUID
    question_id: UUID
    option_text: str
    order_index: int
    is_correct: Optional[bool] = None
    explanation: Optional[str] = None

    class Config:
        from_attributes = True


class QuizQuestionResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    competency_id: Optional[UUID] = None
    question_text: str
    question_type: str = "multiple_choice"
    points: int = 1
    order_index: int = 0
    explanation: Optional[str] = None
    # Written questions: what the answer is judged on. The expected answer is never sent to learners.
    rubric: Optional[List[dict]] = None
    options: List[QuizOptionResponse] = []

    class Config:
        from_attributes = True


# -----------------------------------------------------------------------------
# Quiz Metadata & Detail
# -----------------------------------------------------------------------------
class QuizResponse(BaseModel):
    id: UUID
    org_id: UUID
    course_id: UUID
    module_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    time_limit_mins: int = 30
    passing_score: float = 70.0
    max_attempts: int = 3
    is_adaptive: bool = False
    questions_count: int = 0
    total_points: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuizDetailResponse(QuizResponse):
    questions: List[QuizQuestionResponse] = []


# -----------------------------------------------------------------------------
# Submissions & Grading
# -----------------------------------------------------------------------------
class QuestionResponseInput(BaseModel):
    question_id: UUID
    selected_option_id: Optional[UUID] = None
    text_response: Optional[str] = None
    # Milliseconds on this question, measured by the player. Held to the attempt's real elapsed time by the server.
    response_time_ms: Optional[int] = Field(None, ge=0, le=3_600_000)


class QuizSubmitRequest(BaseModel):
    responses: List[QuestionResponseInput] = Field(..., min_length=1)


class QuestionGradedResponse(BaseModel):
    question_id: UUID
    selected_option_id: Optional[UUID] = None
    is_correct: bool
    points_awarded: float
    correct_option_id: Optional[UUID] = None
    explanation: Optional[str] = None
    # Written answers (Phase 5)
    question_type: str = "multiple_choice"
    grading_status: str = "graded"                 # graded | needs_review
    score_fraction: Optional[float] = None         # share of the points, 0..1
    graded_by: Optional[str] = None                # ai | human
    feedback: Optional[str] = None

    class Config:
        from_attributes = True


class QuizAttemptResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    user_id: UUID
    score: float
    passed: bool
    attempt_number: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    # needs_review: some written answers await a person; the score is provisional and the attempt is not yet passed
    grading_status: str = "graded"
    responses: List[QuestionGradedResponse] = []

    class Config:
        from_attributes = True


# -----------------------------------------------------------------------------
# Learner Quiz Summary / Assessments Dashboard
# -----------------------------------------------------------------------------
class LearnerQuizSummary(BaseModel):
    quiz_id: UUID
    content_item_id: Optional[UUID] = None  # the lesson item that opens this quiz in the player
    course_id: UUID
    course_title: str
    module_id: Optional[UUID] = None
    module_title: Optional[str] = None
    title: str
    passing_score: float
    time_limit_mins: int
    questions_count: int
    is_adaptive: bool
    attempts_count: int
    best_score: Optional[float] = None
    passed: bool
    last_attempt_at: Optional[datetime] = None
