"""
Common Pydantic base schemas used across all services.
These schemas define shared types and base classes to ensure consistency.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class UserRole(str, Enum):
    """User roles for RBAC."""
    LEARNER = "learner"
    MANAGER = "manager"
    ADMIN = "admin"


class Difficulty(str, Enum):
    """Content/question difficulty levels."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ContentType(str, Enum):
    """Types of learning content."""
    TEXT = "text"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    INTERACTIVE = "interactive"


class ContentStatus(str, Enum):
    """Content processing status."""
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class CourseStatus(str, Enum):
    """Course lifecycle status."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CompetencyTrend(str, Enum):
    """Direction of competency mastery change."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class RiskLevel(str, Enum):
    """Learner risk classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AdaptiveDecisionType(str, Enum):
    """Types of adaptive decisions the engine can make."""
    REMEDIATE = "remediate"
    CONTINUE = "continue"
    ADVANCE = "advance"
    SKIP = "skip"
    CHANGE_MODALITY = "change_modality"
    REVISIT = "revisit"


class InsightScopeType(str, Enum):
    """Scope levels for insight generation."""
    LEARNER = "learner"
    TEAM = "team"
    COHORT = "cohort"
    COURSE = "course"
    MODULE = "module"
    ORGANIZATION = "organization"
    PROGRAM = "program"


class InsightStatus(str, Enum):
    """Lifecycle of a generated insight."""
    GENERATED = "generated"
    VALIDATED = "validated"
    REJECTED = "rejected"


class ReportType(str, Enum):
    """Types of generated reports."""
    LEARNER = "learner"
    TEAM = "team"
    ORGANIZATION = "organization"
    DIGEST = "digest"
    CUSTOM = "custom"


class AssessmentType(str, Enum):
    """Assessment purpose classification."""
    FORMATIVE = "formative"
    SUMMATIVE = "summative"


class QuestionType(str, Enum):
    """Question format types."""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


# =============================================================================
# Base Schemas
# =============================================================================

class BaseResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool = True
    message: Optional[str] = None


class PaginatedRequest(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    """Paginated list response."""
    items: list[Any] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class ErrorDetail(BaseModel):
    """Structured error response."""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error envelope."""
    error: ErrorDetail


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    service: str
    version: str = "1.0.0"
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Readiness check response with dependency status."""
    status: str = "ready"
    service: str
    dependencies: dict[str, str] = {}
    timestamp: datetime


# =============================================================================
# Tenant Context
# =============================================================================

class TenantContext(BaseModel):
    """
    Resolved tenant context for the current request.
    Populated by the tenant middleware and available via dependency injection.
    """
    tenant_id: UUID
    user_id: UUID
    role: UserRole
    email: str
