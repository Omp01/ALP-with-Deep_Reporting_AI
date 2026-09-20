"""
Learning events, learning sessions and the event outbox.

`LearningEvent` rows are append-only: the database rejects UPDATE and DELETE (migration
006), and the application never issues either. Events are evidence.
"""

from datetime import datetime
import uuid

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Boolean, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class LearningSession(Base):
    """
    A period of learning by one learner, in one tenant, usually within one course.

    Sessions are state (they gain `last_activity_at` and `ended_at`); the events that
    reference them are not. A session that nobody ended is closed lazily, at the time of
    its last activity, the next time it is looked at (see app/events/sessions.py), so
    durations are never inflated by a forgotten tab.
    """
    __tablename__ = "learning_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    end_reason = Column(String(20), nullable=True)  # explicit | idle | superseded
    context = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "org_id", "user_id", name="uq_learning_sessions_id_org_user"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_learning_sessions_time_order"),
        CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="ck_learning_sessions_end_pair"),
    )


class LearningEvent(Base):
    """
    One thing that happened: a learner action or a system decision. Never modified.

    `timestamp` is when it happened (for events a browser reports, the browser's clock
    within sane bounds); `received_at` is when the server recorded it.
    """
    __tablename__ = "learning_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id"), nullable=True, index=True)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=True, index=True)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=True, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("quiz_questions.id"), nullable=True, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    payload = Column(JSONB, default=dict, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    idempotency_key = Column(String(128), nullable=True)
    # Deprecated: never updated (the table is append-only). Delivery state lives in `event_outbox`.
    processed = Column(Boolean, default=False, nullable=False, index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "org_id", "user_id"],
            ["learning_sessions.id", "learning_sessions.org_id", "learning_sessions.user_id"],
            name="fk_learning_events_session",
        ),
        Index(
            "uq_learning_events_org_idempotency", "org_id", "idempotency_key", unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class EventOutbox(Base):
    """
    Events that still have to be published to the stream (or have been, with the message id).

    Written in the same transaction as the event, so an event and its delivery obligation
    exist together or not at all; a dispatcher publishes committed rows and retries failures.
    """
    __tablename__ = "event_outbox"

    event_id = Column(UUID(as_uuid=True), ForeignKey("learning_events.id"), primary_key=True)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)
    stream_message_id = Column(String(64), nullable=True)
    last_error = Column(Text, nullable=True)
