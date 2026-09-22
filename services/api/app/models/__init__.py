"""
Database models export.
All 27+ domain models for the Adaptive LMS.
"""

from app.core.database import Base

from app.models.organization import Organization, AuditLog
from app.models.user import User, Team, UserTeam
from app.models.rbac import RoleDefinition, UserRole
from app.models.course import Course, Module, ContentItem, ContentChunk
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.competency import (
    Competency,
    CompetencyPrerequisite,
    CourseCompetency,
    ModuleCompetency,
    LearnerCompetency,
    CompetencyHistory,
    CompetencyStateUpdate,
    EvidenceRecord,
    SkillGap,
)
from app.models.assessment import AssessmentItem
from app.models.enrollment import Enrollment, AdaptiveSession, SessionSequenceStep
from app.models.events import EventOutbox, LearningEvent, LearningSession
from app.models.risk import LearnerRisk
from app.models.grading import GradingResult
from app.models.reporting import AIInsight, ScheduledReport, ReportDigest, Report
from app.models.checkin import Checkin
from app.models.ingestion import IngestionJob, QuestionCandidate
from app.models.quiz import Quiz, QuizQuestion, QuizOption, QuizAttempt, QuestionResponse
from app.models.progress import ContentProgress, ContentCompetency, AdaptiveDecision
from app.models.video_checkpoint import VideoCheckpoint, LearnerVideoCheckpoint

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
    "Assignment",
    "AssignmentSubmission",
    "Competency",
    "CompetencyPrerequisite",
    "RoleDefinition",
    "UserRole",
    "CourseCompetency",
    "ModuleCompetency",
    "LearnerCompetency",
    "CompetencyHistory",
    "CompetencyStateUpdate",
    "EvidenceRecord",
    "GradingResult",
    "Report",
    "Checkin",
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
    "QuestionCandidate",
    "Quiz",
    "QuizQuestion",
    "QuizOption",
    "QuizAttempt",
    "QuestionResponse",
    "ContentProgress",
    "ContentCompetency",
    "AdaptiveDecision",
    "VideoCheckpoint",
    "LearnerVideoCheckpoint",
]
