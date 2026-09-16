"""
Learning event type definitions.

These are the canonical event types that the Learning Event Store accepts.
All services reference these types for event creation, consumption, and reporting.
"""
from enum import Enum


class EventType(str, Enum):
    """
    All possible learning event types.
    Each represents a distinct learner action or system action.
    Events are immutable once created.
    """
    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"

    # Content interaction
    CONTENT_STARTED = "content_started"
    CONTENT_COMPLETED = "content_completed"
    CONTENT_SKIPPED = "content_skipped"
    CONTENT_RECOMMENDED = "content_recommended"

    # Question/assessment interaction
    QUESTION_VIEWED = "question_viewed"
    QUESTION_ANSWERED = "question_answered"
    ANSWER_RETRIED = "answer_retried"
    HINT_REQUESTED = "hint_requested"
    ASSESSMENT_STARTED = "assessment_started"
    ASSESSMENT_COMPLETED = "assessment_completed"


# Events that contribute to competency evidence
COMPETENCY_EVENTS = {
    EventType.QUESTION_ANSWERED,
    EventType.ANSWER_RETRIED,
    EventType.ASSESSMENT_COMPLETED,
    EventType.CONTENT_COMPLETED,
}

# Events that should trigger adaptive engine evaluation
ADAPTIVE_TRIGGER_EVENTS = {
    EventType.QUESTION_ANSWERED,
    EventType.ANSWER_RETRIED,
    EventType.CONTENT_COMPLETED,
    EventType.ASSESSMENT_COMPLETED,
}
