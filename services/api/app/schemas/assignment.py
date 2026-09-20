"""
Pydantic schemas for Assignments and Submissions.
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class AssignmentCreate(BaseModel):
    course_id: UUID
    module_id: UUID
    competency_id: Optional[UUID] = None
    title: str = Field(..., max_length=255)
    instructions: str
    difficulty: str = "intermediate"
    max_score: float = 100.0
    rubric: Dict[str, Any] = Field(default_factory=dict)
    status: str = "published"


class AssignmentResponse(BaseModel):
    id: UUID
    org_id: UUID
    course_id: UUID
    module_id: UUID
    competency_id: Optional[UUID] = None
    title: str
    instructions: str
    difficulty: str
    max_score: float
    rubric: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssignmentSubmissionCreate(BaseModel):
    # The path parameter is authoritative; a body value, if sent, must match it.
    assignment_id: Optional[UUID] = None
    submission_text: Optional[str] = Field(None, max_length=50_000)
    submission_url: Optional[str] = Field(None, max_length=1024)

    @model_validator(mode="after")
    def _require_content(self):
        if not (self.submission_text and self.submission_text.strip()) and not self.submission_url:
            raise ValueError("A submission needs text or a URL")
        return self


class AssignmentGradeRequest(BaseModel):
    score: float
    feedback: str
    rubric_scores: Dict[str, Any] = Field(default_factory=dict)
    is_ai_graded: bool = False


class AssignmentSubmissionResponse(BaseModel):
    id: UUID
    org_id: UUID
    assignment_id: UUID
    learner_id: UUID
    submission_text: Optional[str] = None
    submission_url: Optional[str] = None
    status: str
    score: Optional[float] = None
    feedback: Optional[str] = None
    rubric_scores: Dict[str, Any]
    is_ai_graded: bool
    graded_by_id: Optional[UUID] = None
    submitted_at: datetime
    graded_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
