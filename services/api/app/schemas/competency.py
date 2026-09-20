"""
Pydantic schemas for Competencies, taxonomies, and mappings.
"""

from typing import Any, Dict, Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class CompetencyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    code: str = Field(..., max_length=100)
    description: Optional[str] = None
    taxonomy_level: str = Field("remember", description="remember, understand, apply, analyze, evaluate, create")
    parent_id: Optional[UUID] = None
    domain: Optional[str] = Field(None, max_length=100)
    difficulty: float = Field(0.5, ge=0.0, le=1.0, description="0 = easiest, 1 = hardest")
    competency_metadata: Dict[str, Any] = Field(default_factory=dict)


class CompetencyUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    taxonomy_level: Optional[str] = None
    parent_id: Optional[UUID] = None
    domain: Optional[str] = Field(None, max_length=100)
    difficulty: Optional[float] = Field(None, ge=0.0, le=1.0)
    competency_metadata: Optional[Dict[str, Any]] = None


class CompetencyResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    code: str
    description: Optional[str] = None
    taxonomy_level: str
    parent_id: Optional[UUID] = None
    domain: Optional[str] = None
    difficulty: float = 0.5
    competency_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Skill graph
# ---------------------------------------------------------------------------
class PrerequisiteCreate(BaseModel):
    prerequisite_id: UUID
    min_mastery: float = Field(0.6, ge=0.0, le=1.0, description="Mastery of the prerequisite that unblocks this competency")
    rationale: Optional[str] = Field(None, max_length=1000)


class PrerequisiteResponse(BaseModel):
    competency_id: UUID
    prerequisite_id: UUID
    min_mastery: float
    rationale: Optional[str] = None

    class Config:
        from_attributes = True


class SkillGraphNode(BaseModel):
    id: UUID
    code: str
    name: str
    domain: Optional[str] = None
    difficulty: float
    taxonomy_level: str
    level: int = Field(..., description="Depth in the graph; 0 = no prerequisites")
    prerequisite_ids: List[UUID]
    dependent_ids: List[UUID]


class SkillGraphResponse(BaseModel):
    nodes: List[SkillGraphNode]
    edges: List[PrerequisiteResponse]
    domains: List[str]
    max_level: int


class CourseCompetencyMapRequest(BaseModel):
    competency_id: UUID
    target_mastery: float = Field(0.8, ge=0.0, le=1.0)
    is_primary: bool = True


class ModuleCompetencyMapRequest(BaseModel):
    competency_id: UUID
    weight: float = Field(1.0, ge=0.1, le=10.0)


class LearnerCompetencyResponse(BaseModel):
    id: UUID
    competency_id: UUID
    name: str
    code: str
    description: Optional[str] = None
    taxonomy_level: str
    mastery_score: float
    confidence_score: float
    data_points_count: int
    status: str
    trend: str
    last_assessed_at: Optional[datetime] = None
    updated_at: datetime

    class Config:
        from_attributes = True

