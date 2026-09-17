"""
Pydantic schemas for Assignments and Submissions.
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


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
    assignment_id: UUID
    submission_text: Optional[str] = None
    submission_url: Optional[str] = None


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
