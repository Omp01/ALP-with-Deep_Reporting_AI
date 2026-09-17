"""
Enrollment, AdaptiveSession, and SessionSequenceStep models.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Enrollment(Base):
    """
    Learner enrollment in a course.
    """
    __tablename__ = "enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="active", nullable=False)  # active, completed, dropped
    progress_pct = Column(Float, default=0.0, nullable=False)  # 0.0 to 100.0
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")


class AdaptiveSession(Base):
    """
    Active or historical adaptive learning session.
    """
    __tablename__ = "adaptive_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    current_module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="SET NULL"), nullable=True)
    state = Column(String(50), default="active", nullable=False)  # active, paused, completed
    current_difficulty = Column(Float, default=0.5, nullable=False)
    recommended_next_action = Column(String(100), nullable=True)
    session_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="adaptive_sessions")
    course = relationship("Course", back_populates="adaptive_sessions")
    current_module = relationship("Module")
    steps = relationship("SessionSequenceStep", back_populates="session", cascade="all, delete-orphan", order_by="SessionSequenceStep.step_order")


class SessionSequenceStep(Base):
    """
    Step dynamically sequenced by the Adaptive Engine.
    """
    __tablename__ = "session_sequence_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("adaptive_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order = Column(Integer, default=0, nullable=False)
    item_type = Column(String(50), nullable=False)  # content, assessment, remediation
    item_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(String(50), default="pending", nullable=False)  # pending, in_progress, completed, skipped
    result_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("AdaptiveSession", back_populates="steps")
