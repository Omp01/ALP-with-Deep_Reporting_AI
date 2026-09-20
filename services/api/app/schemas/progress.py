"""
Pydantic schemas for ContentProgress and CourseProgress.
"""

from typing import Optional, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class ContentProgressUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(not_started|in_progress|completed)$")
    progress_percent: float = Field(0.0, ge=0.0, le=100.0)
    # Seconds of learning since the previous report. The server clamps this to real elapsed time.
    time_spent_seconds: int = Field(0, ge=0, le=3600)
    position_seconds: Optional[int] = Field(None, ge=0, description="Resume point in a video")


class ContentProgressResponse(BaseModel):
    id: UUID
    user_id: UUID
    content_item_id: UUID
    status: str
    progress_percent: float
    time_spent_seconds: int
    position_seconds: int = 0
    last_accessed_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CourseProgressSummary(BaseModel):
    course_id: UUID
    total_items: int
    completed_items: int
    progress_percent: float
    items_progress: Dict[str, ContentProgressResponse] = {}
