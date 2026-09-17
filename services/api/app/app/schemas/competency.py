"""
Pydantic schemas for Competencies, taxonomies, and mappings.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class CompetencyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    code: str = Field(..., max_length=100)
    description: Optional[str] = None
    taxonomy_level: str = Field("remember", description="remember, understand, apply, analyze, evaluate, create")
    parent_id: Optional[UUID] = None


class CompetencyUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    taxonomy_level: Optional[str] = None
    parent_id: Optional[UUID] = None


class CompetencyResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    code: str
    description: Optional[str] = None
    taxonomy_level: str
    parent_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CourseCompetencyMapRequest(BaseModel):
    competency_id: UUID
    target_mastery: float = Field(0.8, ge=0.0, le=1.0)
    is_primary: bool = True


class ModuleCompetencyMapRequest(BaseModel):
    competency_id: UUID
    weight: float = Field(1.0, ge=0.1, le=10.0)
