"""
Service contracts — define the data shapes exchanged between services.

The API Service uses these contracts to communicate with internal services.
Each service validates inbound data against these contracts.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from shared.schemas.common import (
    AdaptiveDecisionType,
    CompetencyTrend,
    Difficulty,
    InsightScopeType,
    InsightStatus,
    RiskLevel,
)


# =============================================================================
# Adaptive Engine Contracts
# =============================================================================

class CompetencyStateContract(BaseModel):
    """Competency state for a single learner-competency pair."""
    competency_id: UUID
    learner_id: UUID
    mastery: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = 0
    recent_accuracy: Optional[float] = None
    avg_response_time_ms: Optional[float] = None
    retry_rate: Optional[float] = None
    error_distribution: Optional[dict[str, int]] = None
    trend: CompetencyTrend = CompetencyTrend.STABLE
    last_updated: datetime


class AdaptiveNextRequest(BaseModel):
    """Request for next content recommendation."""
    learner_id: UUID
    session_id: UUID
    course_id: UUID
    current_module_id: Optional[UUID] = None
    current_competency_id: Optional[UUID] = None


class AdaptiveNextResponse(BaseModel):
    """Adaptive engine recommendation."""
    decision: AdaptiveDecisionType
    reason: str
    competency_id: Optional[UUID] = None
    competency_name: Optional[str] = None
    mastery: Optional[float] = None
    confidence: Optional[float] = None
    recommended_content_id: Optional[UUID] = None
    recommended_content_title: Optional[str] = None
    recommended_difficulty: Optional[Difficulty] = None
    adaptation_type: str = ""


# =============================================================================
# Reporting Engine Contracts
# =============================================================================

class InsightGenerateRequest(BaseModel):
    """Request to generate an AI-grounded insight."""
    scope_type: InsightScopeType
    scope_id: UUID
    question: str


class InsightClaim(BaseModel):
    """A single claim within a generated insight."""
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = []
    supported: bool = True


class InsightResponse(BaseModel):
    """Generated insight with grounded claims."""
    insight_id: UUID
    scope_type: InsightScopeType
    scope_id: UUID
    question: str
    claims: list[InsightClaim] = []
    summary: str = ""
    recommendations: list[str] = []
    status: InsightStatus = InsightStatus.GENERATED
    prompt_version: str = ""
    model_used: str = ""
    generation_time_ms: int = 0
    created_at: datetime


class RiskScoreContract(BaseModel):
    """Risk assessment for a learner."""
    learner_id: UUID
    risk_level: RiskLevel
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_reasons: list[str] = []
    detected_at: datetime


# =============================================================================
# Ingestion Contracts
# =============================================================================

class IngestionJobContract(BaseModel):
    """Status of a content ingestion job."""
    job_id: UUID
    content_id: UUID
    status: str  # processing, completed, error
    progress: float = 0.0  # 0.0 to 1.0
    competencies_extracted: int = 0
    questions_generated: int = 0
    error_message: Optional[str] = None
