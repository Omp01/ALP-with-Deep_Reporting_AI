"""
Pydantic schemas for Course Enrollments and Progress.
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class EnrollmentCreate(BaseModel):
    course_id: UUID
    user_id: Optional[UUID] = None  # If not provided, enrolls current authenticated user


class EnrollmentProgressUpdate(BaseModel):
    # Deprecated and ignored: progress is derived from completed lesson items and cannot be set.
    progress_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    status: Optional[str] = Field(None, pattern=r"^(active|dropped)$", description="active or dropped")


class EnrollmentResponse(BaseModel):
    id: UUID
    org_id: UUID
    user_id: UUID
    course_id: UUID
    status: str
    progress_pct: float
    enrolled_at: datetime
    completed_at: Optional[datetime] = None
    last_activity_at: datetime

    class Config:
        from_attributes = True
