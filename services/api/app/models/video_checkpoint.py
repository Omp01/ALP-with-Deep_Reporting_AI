"""
Video Checkpoints and Learner Checkpoint Progress models.

Supports interactive video learning:
- Video checkpoints generated from video transcripts.
- Anti-skipping enforcement and comprehension tracking.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class VideoCheckpoint(Base):
    """
    Checkpoints defined along a video's timeline requiring learner comprehension checks.
    """
    __tablename__ = "video_checkpoints"
    __table_args__ = (
        Index("ix_video_checkpoints_content_ts", "content_item_id", "timestamp_seconds"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp_seconds = Column(Float, nullable=False)
    timestamp_start_seconds = Column(Float, nullable=True)
    timestamp_end_seconds = Column(Float, nullable=True)
    topic = Column(String(255), nullable=True)
    transcript_segment = Column(Text, nullable=True)
    question = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)  # list of {"id": "A", "text": "..."}
    correct_option_id = Column(String(10), nullable=False)
    explanation = Column(Text, nullable=True)
    max_score = Column(Float, default=10.0, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    content_item = relationship("ContentItem", backref="video_checkpoints")
    competency = relationship("Competency")
    learner_responses = relationship("LearnerVideoCheckpoint", back_populates="checkpoint", cascade="all, delete-orphan")
    attempts = relationship("VideoCheckpointAttempt", back_populates="checkpoint", cascade="all, delete-orphan")


class LearnerVideoCheckpoint(Base):
    """
    Tracks each learner's progress, displayed state, and answer for a video checkpoint.
    """
    __tablename__ = "learner_video_checkpoints"
    __table_args__ = (
        Index("uq_learner_video_chk", "user_id", "checkpoint_id", unique=True),
        Index("ix_learner_video_user_content", "user_id", "content_item_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True)
    checkpoint_id = Column(UUID(as_uuid=True), ForeignKey("video_checkpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # pending, displayed, answered, correct, incorrect
    status = Column(String(30), default="pending", nullable=False, index=True)
    selected_option_id = Column(String(10), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    
    # Attempt-based scoring & audit
    score = Column(Float, default=0.0, nullable=False)
    max_score = Column(Float, default=10.0, nullable=False)
    attempt_factor = Column(Float, default=1.0, nullable=False)
    accuracy_factor = Column(Float, default=0.0, nullable=False)
    formula_id = Column(String(50), default="attempt_decay_v1", nullable=True)
    formula_version = Column(String(20), default="1.0.0", nullable=True)
    calculation_details = Column(JSONB, nullable=True)
    
    answered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    content_item = relationship("ContentItem")
    checkpoint = relationship("VideoCheckpoint", back_populates="learner_responses")


class VideoCheckpointAttempt(Base):
    """
    Immutable audit log of every individual submission for video checkpoints.
    Preserves calculation parameters, penalties, and formula version permanently.
    """
    __tablename__ = "video_checkpoint_attempts"
    __table_args__ = (
        Index("ix_chk_attempts_user_chk", "user_id", "checkpoint_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    checkpoint_id = Column(UUID(as_uuid=True), ForeignKey("video_checkpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, default=1, nullable=False)
    selected_option_id = Column(String(10), nullable=True)
    is_correct = Column(Boolean, default=False, nullable=False)
    score_awarded = Column(Float, default=0.0, nullable=False)
    max_score = Column(Float, default=10.0, nullable=False)
    formula_id = Column(String(50), default="attempt_decay_v1", nullable=False)
    formula_version = Column(String(20), default="1.0.0", nullable=False)
    calculation_snapshot = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    checkpoint = relationship("VideoCheckpoint", back_populates="attempts")

