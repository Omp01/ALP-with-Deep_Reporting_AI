"""
Learning event type definitions.

These are the canonical event types that the Learning Event Store accepts.
All services reference these types for event creation, consumption, and reporting.

Who may create which type, which references and payload fields each one needs, and how
they are validated is defined next to the API (`services/api/app/events/vocabulary.py`);
this module is only the shared list of names.

Events are immutable once created.
"""
from enum import Enum


class EventType(str, Enum):
    """
    Every event type. Each is a distinct learner action or system action.
    """
    # ---- session lifecycle (server)
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"

    # ---- content interaction
    LESSON_OPENED = "lesson_opened"              # any lesson item opened in the player (learner)
    CONTENT_STARTED = "content_started"          # first progress on an item (server)
    CONTENT_COMPLETED = "content_completed"      # item completed, all kinds (server): the fact competency logic counts
    CONTENT_SKIPPED = "content_skipped"
    CONTENT_RECOMMENDED = "content_recommended"

    VIDEO_STARTED = "video_started"              # (learner)
    VIDEO_PAUSED = "video_paused"                # (learner)
    VIDEO_RESUMED = "video_resumed"              # (learner)
    VIDEO_PROGRESS = "video_progress"            # (learner) periodic position report
    VIDEO_COMPLETED = "video_completed"          # (server) the video-specific view of a content_completed
    ARTICLE_OPENED = "article_opened"            # (learner)
    ARTICLE_COMPLETED = "article_completed"      # (server) the article-specific view of a content_completed

    # ---- assessment
    ASSESSMENT_STARTED = "assessment_started"    # (server) an attempt began
    RETRY_STARTED = "retry_started"              # (server) an attempt beyond the first began
    QUESTION_SHOWN = "question_shown"            # (learner) a question was displayed
    HINT_REQUESTED = "hint_requested"            # (learner)
    ANSWER_SUBMITTED = "answer_submitted"        # (server) reserved: asynchronous grading, Phase 5
    ANSWER_GRADED = "answer_graded"              # (server) reserved: grading agent output, Phase 5
    QUESTION_ANSWERED = "question_answered"      # (server) the graded answer: the primary evidence event
    ASSESSMENT_COMPLETED = "assessment_completed"  # (server)

    # ---- assignments
    ASSIGNMENT_OPENED = "assignment_opened"      # (learner)
    ASSIGNMENT_SUBMITTED = "assignment_submitted"  # (server)
    ASSIGNMENT_GRADED = "assignment_graded"      # (server)

    # ---- system decisions (server; produced by later phases)
    ADAPTIVE_DECISION_MADE = "adaptive_decision_made"
    COMPETENCY_UPDATED = "competency_updated"
    RECOMMENDATION_GENERATED = "recommendation_generated"
    CHECKIN_COMPLETED = "checkin_completed"      # (server) a login check-in was submitted and scored

    # ---- legacy names. Old rows may carry them; new events use the names above.
    QUESTION_VIEWED = "question_viewed"          # now question_shown
    ANSWER_RETRIED = "answer_retried"            # now retry_started
    VIDEO_PLAYED = "video_played"                # now video_started / video_resumed
    ARTICLE_READ = "article_read"                # now article_completed


# Old names accepted on ingest and stored under their current name.
LEGACY_ALIASES = {
    EventType.QUESTION_VIEWED.value: EventType.QUESTION_SHOWN.value,
    EventType.ANSWER_RETRIED.value: EventType.RETRY_STARTED.value,
    EventType.VIDEO_PLAYED.value: EventType.VIDEO_RESUMED.value,
}


# Events that contribute to competency evidence
COMPETENCY_EVENTS = {
    EventType.QUESTION_ANSWERED,
    EventType.ANSWER_RETRIED,
    EventType.ASSESSMENT_COMPLETED,
    EventType.CONTENT_COMPLETED,
    EventType.ARTICLE_READ,
    EventType.ASSIGNMENT_SUBMITTED,
}

# Events that should trigger adaptive engine evaluation
ADAPTIVE_TRIGGER_EVENTS = {
    EventType.QUESTION_ANSWERED,
    EventType.ANSWER_RETRIED,
    EventType.CONTENT_COMPLETED,
    EventType.ASSESSMENT_COMPLETED,
    EventType.ASSIGNMENT_SUBMITTED,
}
