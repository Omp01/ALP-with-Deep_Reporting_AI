"""
Video Checkpoints and Learner Checkpoint Progress models.

Supports interactive video learning:
- Video checkpoints generated from video transcripts.
- Anti-skipping enforcement and comprehension tracking.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index, Text
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
    timestamp_seconds = Column(Float, nullable=False)
    transcript_segment = Column(Text, nullable=True)
    question = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)  # list of {"id": "A", "text": "..."}
    correct_option_id = Column(String(10), nullable=False)
    explanation = Column(Text, nullable=True)
    order_index = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    content_item = relationship("ContentItem", backref="video_checkpoints")
    learner_responses = relationship("LearnerVideoCheckpoint", back_populates="checkpoint", cascade="all, delete-orphan")


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
    answered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    content_item = relationship("ContentItem")
    checkpoint = relationship("VideoCheckpoint", back_populates="learner_responses")
