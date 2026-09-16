"""
Database models export.
All 25+ domain models for the Adaptive LMS.
"""

from app.core.database import Base

from app.models.organization import Organization, AuditLog
from app.models.user import User, Team, UserTeam
from app.models.course import Course, Module, ContentItem, ContentChunk
from app.models.competency import (
    Competency,
    CourseCompetency,
    ModuleCompetency,
    LearnerCompetency,
    CompetencyHistory,
    SkillGap,
)
from app.models.assessment import AssessmentItem
from app.models.enrollment import Enrollment, AdaptiveSession, SessionSequenceStep
from app.models.events import LearningEvent
from app.models.risk import LearnerRisk
from app.models.reporting import AIInsight, ScheduledReport, ReportDigest
from app.models.ingestion import IngestionJob

__all__ = [
    "Base",
    "Organization",
    "AuditLog",
    "User",
    "Team",
    "UserTeam",
    "Course",
    "Module",
    "ContentItem",
    "ContentChunk",
    "Competency",
    "CourseCompetency",
    "ModuleCompetency",
    "LearnerCompetency",
    "CompetencyHistory",
    "SkillGap",
    "AssessmentItem",
    "Enrollment",
    "AdaptiveSession",
    "SessionSequenceStep",
    "LearningEvent",
    "LearnerRisk",
    "AIInsight",
    "ScheduledReport",
    "ReportDigest",
    "IngestionJob",
]
