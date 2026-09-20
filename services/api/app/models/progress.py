"""
ContentProgress, ContentCompetency, and AdaptiveDecision models.
Learner content tracking, content-competency knowledge graph associations, and adaptive engine decision audit log.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class ContentProgress(Base):
    """
    Granular learner tracking per content item (video, text, article, quiz).
    """
    __tablename__ = "content_progress"
    __table_args__ = (
        # One progress row per learner per lesson item.
        Index("uq_content_progress_user_item", "user_id", "content_item_id", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="not_started", nullable=False, index=True)  # not_started, in_progress, completed
    progress_percent = Column(Float, default=0.0, nullable=False)
    time_spent_seconds = Column(Integer, default=0, nullable=False)
    position_seconds = Column(Integer, default=0, nullable=False, server_default="0")  # resume point in a video
    last_accessed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    content_item = relationship("ContentItem", back_populates="progress_records")


class ContentCompetency(Base):
    """
    Mapping between Content Items and target Competencies with knowledge contribution weight.
    """
    __tablename__ = "content_competencies"

    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), primary_key=True)
    weight = Column(Float, default=1.0, nullable=False)

    # Relationships
    content_item = relationship("ContentItem", back_populates="competency_mappings")
    competency = relationship("Competency")


class AdaptiveDecision(Base):
    """
    Audit log of adaptive engine branching, remediation, advancement, and scaffolding recommendations.
    """
    __tablename__ = "adaptive_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("adaptive_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True, index=True)
    decision_type = Column(String(50), nullable=False, index=True)  # remediation, advancement, hint, review, scaffold
    reason = Column(Text, nullable=False)
    rule_applied = Column(String(100), nullable=True)
    decision_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User")
    session = relationship("AdaptiveSession")
    competency = relationship("Competency")
