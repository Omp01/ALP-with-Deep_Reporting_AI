"""
LearnerRisk model for dropout, disengagement, and failure risk detection.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class LearnerRisk(Base):
    """
    At-risk assessment record computed by Risk Worker / Adaptive Engine.
    """
    __tablename__ = "learner_risks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_level = Column(String(50), default="low", nullable=False, index=True)  # low, medium, high, critical
    risk_score = Column(Float, default=0.0, nullable=False)  # 0.0 to 1.0
    risk_factors = Column(JSONB, default=list, nullable=False)  # Reasons: inactivity, declining scores, stalled progress
    recommended_actions = Column(JSONB, default=list, nullable=False)  # Recommended interventions
    # Structured reasons: [{"code", "description", "value", "points", "evidence_ids"}]; risk_factors is their text.
    risk_details = Column(JSONB, default=list, nullable=False, server_default="[]")
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="risk_records")
    course = relationship("Course")
