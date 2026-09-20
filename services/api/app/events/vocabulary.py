"""
The event vocabulary: which events exist, who may create them, and what each must carry.

Two sources of events, and the difference is the point:

  * SERVER events describe facts only the server can establish: a graded answer, a
    completed assessment, a completed lesson, a submission, a grade, a decision. The
    browser cannot create these, so a learner cannot forge evidence about themselves.
  * LEARNER events describe interaction the server cannot see: a lesson opened, a video
    played or paused, a question displayed. The browser reports them, and the server
    checks every reference (the item must exist in the caller's tenant) and derives the
    rest (course, module, competency) itself.

Payloads are validated per type. Unknown fields are rejected for learner events, so the
event store is not a place to smuggle arbitrary data.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Tuple, Type
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shared.events.types import LEGACY_ALIASES, EventType

MAX_PAYLOAD_BYTES = 8 * 1024

LEARNER = "learner"
SERVER = "server"


class VocabularyError(ValueError):
    """An event that the vocabulary rejects. `code` is stable and machine-readable."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- payload models
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class LessonOpened(_Strict):
    source: Literal["outline", "resume", "next", "recommendation", "direct"] = "direct"


class MediaPosition(_Strict):
    position_seconds: int = Field(ge=0, le=86_400)
    duration_seconds: Optional[int] = Field(None, ge=0, le=86_400)


class VideoProgress(MediaPosition):
    percent: float = Field(ge=0, le=100)


class Empty(_Strict):
    pass


class QuestionShown(_Strict):
    attempt_id: UUID
    position: Optional[int] = Field(None, ge=0, le=1000)


class HintRequested(_Strict):
    attempt_id: UUID
    hint_index: Optional[int] = Field(None, ge=0, le=20)


class AssignmentOpened(_Strict):
    assignment_id: UUID


class SessionStarted(_Loose):
    source: str = "explicit"


class SessionCompleted(_Loose):
    reason: str
    duration_seconds: int = Field(ge=0)


class ContentEvent(_Loose):
    content_type: str


class DerivedCompletion(_Loose):
    derived_from: UUID  # the content_completed event this is the typed view of


class AttemptEvent(_Loose):
    attempt_id: UUID
    attempt_number: int = Field(ge=1)


class QuestionAnswered(_Loose):
    attempt_id: UUID
    attempt_number: int = Field(ge=1)
    is_correct: bool
    points_awarded: float
    answered: bool
    selected_option_id: Optional[UUID] = None
    question_type: str
    difficulty: Optional[float] = Field(None, ge=0, le=1)
    response_time_ms: Optional[int] = Field(None, ge=0)
    response_time_source: Optional[str] = None
    error_type: Optional[str] = None


class AssessmentCompleted(_Loose):
    attempt_id: UUID
    attempt_number: int = Field(ge=1)
    score: float
    passed: bool
    earned_points: float
    total_points: float


class AssignmentEvent(_Loose):
    assignment_id: UUID
    submission_id: UUID


# ----------------------------------------------------------------------------- the policy
@dataclass(frozen=True)
class EventSpec:
    source: str                                   # LEARNER or SERVER
    requires: Tuple[str, ...] = ()                # reference columns that must be present
    model: Optional[Type[BaseModel]] = None       # payload validation; None = free-form (bounded)
    needs_course: bool = False                    # belongs to a course (gets a learning session)


E = EventType
SPECS: Dict[str, EventSpec] = {
    # ---- learner-reported interaction
    E.LESSON_OPENED.value: EventSpec(LEARNER, ("content_id",), LessonOpened, True),
    E.VIDEO_STARTED.value: EventSpec(LEARNER, ("content_id",), MediaPosition, True),
    E.VIDEO_PAUSED.value: EventSpec(LEARNER, ("content_id",), MediaPosition, True),
    E.VIDEO_RESUMED.value: EventSpec(LEARNER, ("content_id",), MediaPosition, True),
    E.VIDEO_PROGRESS.value: EventSpec(LEARNER, ("content_id",), VideoProgress, True),
    E.ARTICLE_OPENED.value: EventSpec(LEARNER, ("content_id",), Empty, True),
    E.QUESTION_SHOWN.value: EventSpec(LEARNER, ("question_id",), QuestionShown, True),
    E.HINT_REQUESTED.value: EventSpec(LEARNER, ("question_id",), HintRequested, True),
    E.ASSIGNMENT_OPENED.value: EventSpec(LEARNER, (), AssignmentOpened, True),
    # ---- server-established facts
    E.SESSION_STARTED.value: EventSpec(SERVER, (), SessionStarted),
    E.SESSION_COMPLETED.value: EventSpec(SERVER, (), SessionCompleted),
    E.CONTENT_STARTED.value: EventSpec(SERVER, ("content_id",), ContentEvent, True),
    E.CONTENT_COMPLETED.value: EventSpec(SERVER, ("content_id",), ContentEvent, True),
    E.VIDEO_COMPLETED.value: EventSpec(SERVER, ("content_id",), DerivedCompletion, True),
    E.ARTICLE_COMPLETED.value: EventSpec(SERVER, ("content_id",), DerivedCompletion, True),
    E.ASSESSMENT_STARTED.value: EventSpec(SERVER, ("assessment_id",), AttemptEvent, True),
    E.RETRY_STARTED.value: EventSpec(SERVER, ("assessment_id",), AttemptEvent, True),
    E.QUESTION_ANSWERED.value: EventSpec(SERVER, ("assessment_id", "question_id"), QuestionAnswered, True),
    E.ASSESSMENT_COMPLETED.value: EventSpec(SERVER, ("assessment_id",), AssessmentCompleted, True),
    E.ASSIGNMENT_SUBMITTED.value: EventSpec(SERVER, (), AssignmentEvent, True),
    E.ASSIGNMENT_GRADED.value: EventSpec(SERVER, (), AssignmentEvent, True),
    # ---- reserved for later phases (server only, free-form payload for now)
    E.ANSWER_SUBMITTED.value: EventSpec(SERVER, ("question_id",), None, True),
    E.ANSWER_GRADED.value: EventSpec(SERVER, ("question_id",), None, True),
    E.ADAPTIVE_DECISION_MADE.value: EventSpec(SERVER, (), None, True),
    E.COMPETENCY_UPDATED.value: EventSpec(SERVER, ("competency_id",), None),
    E.RECOMMENDATION_GENERATED.value: EventSpec(SERVER, (), None),
    E.CHECKIN_COMPLETED.value: EventSpec(SERVER, (), None),
    E.CONTENT_SKIPPED.value: EventSpec(SERVER, ("content_id",), None, True),
    E.CONTENT_RECOMMENDED.value: EventSpec(SERVER, ("content_id",), None, True),
}

# Types that appear in old rows but are never created any more.
DEPRECATED = {E.QUESTION_VIEWED.value, E.ANSWER_RETRIED.value, E.VIDEO_PLAYED.value, E.ARTICLE_READ.value}

# Events published to the stream. Two are held back from the legacy mastery handler
# (workers/event-worker -> adaptive-engine): it reads a `correct` key that these events do not
# carry (audit C1: every answer counted as correct) and assigns competency-less evidence to the
# organisation's first competency (C2). They are still stored, queryable and evidence; the Phase 5
# competency engine consumes them from the store, not through that handler.
HELD_FROM_LEGACY_ENGINE = {E.QUESTION_ANSWERED.value, E.ASSIGNMENT_SUBMITTED.value}


def all_types() -> Tuple[str, ...]:
    return tuple(SPECS)


def learner_types() -> Tuple[str, ...]:
    return tuple(t for t, s in SPECS.items() if s.source == LEARNER)


def published_to_stream(event_type: str) -> bool:
    return event_type in SPECS and event_type not in HELD_FROM_LEGACY_ENGINE


def normalise(event_type: str) -> str:
    """Current name for a type, accepting the legacy aliases."""
    cleaned = (event_type or "").strip().lower()
    return LEGACY_ALIASES.get(cleaned, cleaned)


def spec_for(event_type: str) -> EventSpec:
    spec = SPECS.get(event_type)
    if spec is None:
        code = "deprecated_event_type" if event_type in DEPRECATED else "unknown_event_type"
        raise VocabularyError(f"'{event_type}' is not an event type this platform records.", code)
    return spec


def validate_payload(event_type: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The payload as it will be stored (JSON-safe), or a VocabularyError."""
    spec = spec_for(event_type)
    data = payload or {}
    if not isinstance(data, dict):
        raise VocabularyError("The payload must be an object.", "invalid_payload")
    if spec.model is not None:
        try:
            data = json.loads(spec.model.model_validate(data).model_dump_json(exclude_none=False))
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"]) or "payload"
            raise VocabularyError(f"{event_type}: {where}: {first['msg']}", "invalid_payload") from exc
    else:
        data = json.loads(json.dumps(data, default=str))
    if len(json.dumps(data)) > MAX_PAYLOAD_BYTES:
        raise VocabularyError(f"The payload is larger than {MAX_PAYLOAD_BYTES} bytes.", "payload_too_large")
    return data


def check_references(event_type: str, refs: Dict[str, Optional[UUID]]) -> None:
    missing = [name for name in spec_for(event_type).requires if not refs.get(name)]
    if missing:
        raise VocabularyError(f"{event_type} needs {', '.join(missing)}.", "missing_reference")
