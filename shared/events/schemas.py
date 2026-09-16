"""
Learning event Pydantic schemas.

Used by:
- API Service: to validate incoming event creation requests
- Event Worker: to deserialize events from Redis Streams
- Reporting Engine: to query and structure event data
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from shared.events.types import EventType


class LearningEventCreate(BaseModel):
    """Schema for creating a new learning event via the API."""
    event_type: EventType
    course_id: Optional[UUID] = None
    module_id: Optional[UUID] = None
    content_id: Optional[UUID] = None
    competency_id: Optional[UUID] = None
    question_id: Optional[UUID] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)
    attempt_number: Optional[int] = Field(default=None, ge=1)
    correct: Optional[bool] = None
    error_type: Optional[str] = None
    difficulty: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class LearningEventResponse(BaseModel):
    """Schema for returning a learning event."""
    event_id: UUID
    tenant_id: UUID
    learner_id: UUID
    session_id: UUID
    event_type: EventType
    course_id: Optional[UUID] = None
    module_id: Optional[UUID] = None
    content_id: Optional[UUID] = None
    competency_id: Optional[UUID] = None
    question_id: Optional[UUID] = None
    timestamp: datetime
    duration_ms: Optional[int] = None
    attempt_number: Optional[int] = None
    correct: Optional[bool] = None
    error_type: Optional[str] = None
    difficulty: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class LearningEventStreamMessage(BaseModel):
    """
    Schema for events published to Redis Streams.
    Contains the full event data plus routing metadata.
    """
    event_id: str  # UUID serialized as string for Redis
    tenant_id: str
    learner_id: str
    session_id: str
    event_type: str
    competency_id: Optional[str] = None
    question_id: Optional[str] = None
    correct: Optional[bool] = None
    error_type: Optional[str] = None
    difficulty: Optional[str] = None
    duration_ms: Optional[int] = None
    attempt_number: Optional[int] = None
    timestamp: str  # ISO format
