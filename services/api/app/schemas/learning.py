"""
Response shapes for the learner experience: course overview, player, and home.

Everything here is assembled from stored data. Nothing is a placeholder; a value
that cannot be known is None (or an empty list), and the UI shows an honest empty
state for it.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Course overview (course detail page and player outline)
# ---------------------------------------------------------------------------
class ItemSummary(BaseModel):
    id: UUID
    module_id: UUID
    title: str
    content_type: str
    kind: str = Field(..., description="lesson | assessment | assignment")
    source_type: str
    duration_seconds: int = 0
    order_index: int
    publication_status: str
    progress_status: str = Field("not_started", description="not_started | in_progress | completed")
    progress_percent: float = 0.0
    quiz_id: Optional[UUID] = None
    assignment_id: Optional[UUID] = None


class ModuleOverview(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    sequence_order: int
    lessons: int
    assessments: int
    total_items: int
    completed_items: int
    known_duration_seconds: int = Field(0, description="Sum of items with a recorded length; may undercount")
    items: List[ItemSummary]


class CompetencyDeveloped(BaseModel):
    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    difficulty: float
    target_mastery: float
    mastery: Optional[float] = Field(None, description="The learner's current mastery, None when there is no evidence yet")
    confidence: Optional[float] = None


class PrerequisiteRequirement(BaseModel):
    competency_id: UUID
    code: str
    name: str
    required_for: List[str] = Field(..., description="Names of this course's competencies that need it")
    min_mastery: float
    mastery: Optional[float] = None
    met: Optional[bool] = Field(None, description="None when the learner has no evidence for it")


class ProgressOverview(BaseModel):
    total_items: int
    completed_items: int
    percent: float
    time_spent_seconds: int
    resume_item_id: Optional[UUID] = None
    resume_item_title: Optional[str] = None


class CourseHeader(BaseModel):
    id: UUID
    title: str
    code: str
    description: Optional[str] = None
    status: str
    category: str
    difficulty: str
    thumbnail_url: Optional[str] = None
    instructor_name: Optional[str] = None
    rating: Optional[float] = None
    duration_minutes: Optional[int] = None
    enrollment_count: int = 0
    module_count: int = 0
    item_count: int = 0


class CourseOverview(BaseModel):
    course: CourseHeader
    is_enrolled: bool
    enrollment_status: Optional[str] = None
    is_preview: bool = Field(False, description="Viewed by an author: unpublished content is included")
    objectives: List[str]
    objectives_source: str = Field(..., description="content_analysis | competency_descriptions | none")
    competencies: List[CompetencyDeveloped]
    prerequisites: List[PrerequisiteRequirement]
    modules: List[ModuleOverview]
    progress: ProgressOverview


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
class MediaInfo(BaseModel):
    provider: str
    video_id: Optional[str] = None
    url: Optional[str] = None
    mime_type: Optional[str] = None


class PlayerProgress(BaseModel):
    status: str = "not_started"
    progress_percent: float = 0.0
    position_seconds: int = 0
    time_spent_seconds: int = 0


class AssignmentInfo(BaseModel):
    id: UUID
    instructions: str
    difficulty: str
    max_score: float
    rubric: dict
    submission_status: Optional[str] = None
    submission_text: Optional[str] = None
    submission_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    score: Optional[float] = None
    feedback: Optional[str] = None


class PlayerItem(BaseModel):
    id: UUID
    course_id: UUID
    module_id: UUID
    title: str
    description: Optional[str] = None
    content_type: str
    kind: str
    source_type: str
    duration_seconds: int = 0
    text_content: Optional[str] = None
    transcript: Optional[str] = None
    media: Optional[MediaInfo] = None
    quiz_id: Optional[UUID] = None
    assignment: Optional[AssignmentInfo] = None
    competency_names: List[str] = []


class PlayerPayload(BaseModel):
    item: PlayerItem
    progress: PlayerProgress
    course_title: str
    module_title: str
    position: int = Field(..., description="1-based position among the course's visible items")
    total: int
    previous_id: Optional[UUID] = None
    next_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Learner home
# ---------------------------------------------------------------------------
class ContinueLearning(BaseModel):
    course_id: UUID
    course_title: str
    module_title: Optional[str] = None
    item_id: Optional[UUID] = None
    item_title: Optional[str] = None
    item_type: Optional[str] = None
    progress_percent: float
    last_activity_at: Optional[datetime] = None


class InProgressCourse(BaseModel):
    course_id: UUID
    title: str
    category: str
    difficulty: str
    thumbnail_url: Optional[str] = None
    progress_percent: float
    completed_items: int
    total_items: int


class Recommendation(BaseModel):
    kind: str = Field(..., description="content | course")
    reason_type: str = Field(..., description="weak_competency | popular_in_org | available")
    reason: str
    course_id: UUID
    course_title: str
    content_id: Optional[UUID] = None
    content_title: Optional[str] = None
    content_type: Optional[str] = None
    competency_id: Optional[UUID] = None
    competency_name: Optional[str] = None
    mastery: Optional[float] = None


class HomeCompetency(BaseModel):
    id: UUID
    name: str
    domain: Optional[str] = None
    mastery: float
    confidence: float
    evidence_count: int
    updated_at: datetime


class ActivityItem(BaseModel):
    event_type: str
    label: str
    course_title: Optional[str] = None
    timestamp: datetime


class HomeInsight(BaseModel):
    id: UUID
    narrative: str
    created_at: datetime
    model_used: str


class HomeStats(BaseModel):
    enrolled_courses: int
    completed_courses: int
    completed_items: int
    time_spent_seconds: int


class LearnerHome(BaseModel):
    continue_learning: Optional[ContinueLearning] = None
    in_progress: List[InProgressCourse]
    recommendations: List[Recommendation]
    competencies: List[HomeCompetency]
    recent_activity: List[ActivityItem]
    insight: Optional[HomeInsight] = None
    stats: HomeStats
