"""
Pydantic schemas for Courses, Modules, and Content Items.
Avoids reserved 'metadata' attribute collisions with SQLAlchemy MetaData.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Content Items
# -----------------------------------------------------------------------------
class ContentItemCreate(BaseModel):
    title: str = Field(..., max_length=255)
    content_type: str = Field(..., description="text, video, audio, slide, document, external_link")
    content_url: Optional[str] = None
    raw_text: Optional[str] = None
    transcript: Optional[str] = None
    item_metadata: Dict[str, Any] = Field(default_factory=dict)


class ContentItemResponse(BaseModel):
    id: UUID
    org_id: UUID
    module_id: UUID
    title: str
    content_type: str
    content_url: Optional[str] = None
    raw_text: Optional[str] = None
    transcript: Optional[str] = None
    chunk_count: int = 0
    item_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -----------------------------------------------------------------------------
# Modules
# -----------------------------------------------------------------------------
class ModuleCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration_mins: int = 30


class ModuleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    sequence_order: Optional[int] = None
    estimated_duration_mins: Optional[int] = None


class ModuleResponse(BaseModel):
    id: UUID
    org_id: UUID
    course_id: UUID
    title: str
    description: Optional[str] = None
    sequence_order: int
    estimated_duration_mins: int
    created_at: datetime
    updated_at: datetime
    content_items: List[ContentItemResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


# -----------------------------------------------------------------------------
# Courses
# -----------------------------------------------------------------------------
class CourseCreate(BaseModel):
    title: str = Field(..., max_length=255)
    code: str = Field(..., max_length=50)
    description: Optional[str] = None
    status: str = "draft"
    course_metadata: Dict[str, Any] = Field(default_factory=dict)


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    course_metadata: Optional[Dict[str, Any]] = None


class CourseResponse(BaseModel):
    id: UUID
    org_id: UUID
    title: str
    code: str
    description: Optional[str] = None
    status: str
    created_by_id: Optional[UUID] = None
    course_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    modules: List[ModuleResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True
