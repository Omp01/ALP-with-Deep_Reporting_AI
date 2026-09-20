"""Request and response shapes for the content administration API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------- requests
class IngestYouTubeRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    module_id: UUID
    title: Optional[str] = Field(None, max_length=255)
    allow_duplicate: bool = False


class ProcessRequest(BaseModel):
    force: bool = Field(False, description="Re-run AI analysis even if the content is unchanged")


class ContentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    module_id: Optional[UUID] = None

    @field_validator("title", mode="before")
    @classmethod
    def _tidy_title(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class TranscriptUpdate(BaseModel):
    text: str = Field(..., min_length=50, max_length=500_000)
    analyze: bool = True


class OptionIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=250)
    is_correct: bool = False

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, value):
        return " ".join(str(value or "").split())


def _check_options(options: List[OptionIn]) -> List[OptionIn]:
    if not 3 <= len(options) <= 5:
        raise ValueError("A question needs 3 to 5 options.")
    if sum(1 for o in options if o.is_correct) != 1:
        raise ValueError("Exactly one option must be marked correct.")
    if len({o.text.lower() for o in options}) != len(options):
        raise ValueError("Options must be different from each other.")
    return options


WRITTEN_TYPES = ("short_answer", "open_ended")


class RubricCriterion(BaseModel):
    """One thing a written answer is judged on. Learners see the criteria; they never see the expected answer."""
    criterion: str = Field(..., min_length=2, max_length=120)
    weight: float = Field(1.0, ge=0.0, le=1.0)
    description: Optional[str] = Field(None, max_length=300)

    @field_validator("criterion", "description", mode="before")
    @classmethod
    def _tidy(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


def _check_rubric(rubric: Optional[List[RubricCriterion]]) -> Optional[List[RubricCriterion]]:
    if rubric is None:
        return None
    if not 1 <= len(rubric) <= 8:
        raise ValueError("A rubric needs 1 to 8 criteria.")
    if len({c.criterion.lower() for c in rubric}) != len(rubric):
        raise ValueError("Rubric criteria must be different from each other.")
    return rubric


class CandidateCreate(BaseModel):
    question_text: str = Field(..., min_length=10, max_length=500)
    question_type: str = Field("multiple_choice", pattern=r"^(multiple_choice|short_answer|open_ended)$")
    options: List[OptionIn] = Field(default_factory=list)
    explanation: Optional[str] = Field(None, max_length=1000)
    difficulty: float = Field(0.5, ge=0.0, le=1.0)
    competency_id: Optional[UUID] = None
    competency_name: Optional[str] = Field(None, max_length=255)
    source_quote: Optional[str] = Field(None, max_length=2000)
    # Written questions only: what a good answer says, and what it is judged on
    expected_answer: Optional[str] = Field(None, max_length=3000)
    rubric: Optional[List[RubricCriterion]] = None

    @field_validator("options")
    @classmethod
    def _options(cls, value):
        return _check_options(value) if value else value

    @field_validator("rubric")
    @classmethod
    def _rubric(cls, value):
        return _check_rubric(value)

    @model_validator(mode="after")
    def _by_type(self):
        if self.question_type in WRITTEN_TYPES:
            if self.options:
                raise ValueError("A written question has no options.")
            if not (self.expected_answer or "").strip() and not self.rubric:
                raise ValueError("A written question needs an expected answer or a rubric to be graded against.")
            if self.competency_id is None and not (self.competency_name or "").strip():
                raise ValueError("A written question must test a competency: its answers are graded as evidence for it.")
        else:
            _check_options(self.options)      # 3 to 5 options, exactly one correct
            if self.expected_answer or self.rubric:
                raise ValueError("Only written questions have an expected answer or a rubric.")
        return self


class CandidateUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=10, max_length=500)
    options: Optional[List[OptionIn]] = None
    explanation: Optional[str] = Field(None, max_length=1000)
    difficulty: Optional[float] = Field(None, ge=0.0, le=1.0)
    competency_id: Optional[UUID] = None
    competency_name: Optional[str] = Field(None, max_length=255)
    expected_answer: Optional[str] = Field(None, max_length=3000)
    rubric: Optional[List[RubricCriterion]] = None

    @field_validator("options")
    @classmethod
    def _options(cls, value):
        return _check_options(value) if value is not None else value

    @field_validator("rubric")
    @classmethod
    def _rubric(cls, value):
        return _check_rubric(value)


class CandidateStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(pending|approved|rejected)$")


class BulkCandidateStatus(BaseModel):
    ids: List[UUID] = Field(..., min_length=1, max_length=100)
    status: str = Field(..., pattern=r"^(pending|approved|rejected)$")


class CompetencyDecision(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field("", max_length=500)
    domain: Optional[str] = Field(None, max_length=60)
    bloom_level: str = Field("understand", pattern=r"^(remember|understand|apply|analyze|evaluate|create)$")
    difficulty: float = Field(0.5, ge=0.0, le=1.0)
    action: str = Field(..., pattern=r"^(link|create|skip)$")
    competency_id: Optional[UUID] = None
    code: Optional[str] = Field(None, max_length=100)

    @model_validator(mode="after")
    def _link_needs_target(self):
        if self.action == "link" and not self.competency_id:
            raise ValueError("Linking to an existing competency needs competency_id.")
        return self


class AnalysisUpdate(BaseModel):
    summary: Optional[str] = Field(None, max_length=1000)
    level: Optional[str] = Field(None, pattern=r"^(beginner|intermediate|advanced)$")
    objectives: Optional[List[str]] = Field(None, max_length=15)
    competencies: Optional[List[CompetencyDecision]] = Field(None, max_length=10)

    @field_validator("objectives")
    @classmethod
    def _objectives(cls, value):
        if value is None:
            return value
        cleaned = [" ".join(v.split()) for v in value if v and v.strip()]
        if any(len(v) > 300 for v in cleaned):
            raise ValueError("An objective is limited to 300 characters.")
        return cleaned


# --------------------------------------------------------------------------- responses
class IngestResponse(BaseModel):
    content_id: UUID
    job_id: UUID
    status: str


class StageOut(BaseModel):
    name: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    detail: Optional[str] = None
    error: Optional[Dict[str, Any]] = None


class JobOut(BaseModel):
    id: UUID
    content_item_id: Optional[UUID] = None
    source_type: str
    file_name: str
    status: str
    stage: Optional[str] = None
    stages: List[StageOut]
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    attempts: int
    created_at: datetime
    updated_at: datetime


class CandidateOut(BaseModel):
    id: UUID
    question_text: str
    question_type: str = "multiple_choice"
    options: List[Dict[str, Any]]
    explanation: Optional[str] = None
    expected_answer: Optional[str] = None
    rubric: Optional[List[Dict[str, Any]]] = None
    difficulty: float
    competency_id: Optional[UUID] = None
    competency_name: Optional[str] = None
    source_quote: Optional[str] = None
    origin: str
    status: str
    edited: bool
    created_at: datetime


class ContentListItem(BaseModel):
    id: UUID
    title: str
    content_type: str
    source_type: str
    status: str
    course_id: Optional[UUID] = None
    course_title: Optional[str] = None
    module_id: UUID
    module_title: Optional[str] = None
    duration_seconds: int
    job_status: Optional[str] = None
    pending_questions: int = 0
    approved_questions: int = 0
    created_at: datetime
    updated_at: datetime


class ContentListResponse(BaseModel):
    items: List[ContentListItem]
    total: int


class Readiness(BaseModel):
    can_publish: bool
    blockers: List[str]
    warnings: List[str]


class ContentDetail(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    content_type: str
    source_type: str
    source_url: Optional[str] = None
    original_filename: Optional[str] = None
    status: str
    course_id: Optional[UUID] = None
    course_title: Optional[str] = None
    module_id: UUID
    module_title: Optional[str] = None
    duration_seconds: int
    metadata: Dict[str, Any]
    text_preview: Optional[str] = None
    text_length: int = 0
    has_transcript: bool = False
    analysis: Optional[Dict[str, Any]] = None
    job: Optional[JobOut] = None
    candidates: List[CandidateOut]
    readiness: Readiness
    created_at: datetime
    updated_at: datetime


class PublishResponse(BaseModel):
    content_id: UUID
    status: str
    competencies_created: int
    competencies_linked: int
    questions_published: int
    quiz_content_id: Optional[UUID] = None


class Capabilities(BaseModel):
    file_types: List[str]
    max_upload_mb: int
    youtube: bool = True
    ai_configured: bool
    ai_provider: str
    ai_model: str
    ai_detail: str
    transcription_available: bool
    embeddings_enabled: bool
