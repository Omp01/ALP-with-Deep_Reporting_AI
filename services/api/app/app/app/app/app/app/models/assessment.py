"""
AssessmentItem model for adaptive question bank and AI-generated items.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class AssessmentItem(Base):
    """
    Assessment item with psychometric parameters (IRT / difficulty / discrimination / error classification).
    """
    __tablename__ = "assessment_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), default="multiple_choice", nullable=False)  # multiple_choice, multi_select, true_false, short_answer, open_ended
    options = Column(JSONB, default=list, nullable=False)  # List of choices with distractors and error tags
    correct_answer = Column(JSONB, nullable=False)  # Answer key / string or list
    explanation = Column(Text, nullable=True)
    error_type = Column(String(50), default="CONCEPTUAL", nullable=False)  # CONCEPTUAL, PROCEDURAL, APPLICATION, CALCULATION, CARELESS, UNKNOWN
    difficulty_score = Column(Float, default=0.5, nullable=False)  # 0.1 (easiest) to 1.0 (hardest)
    discrimination_index = Column(Float, default=1.0, nullable=False)  # Item discrimination factor
    is_ai_generated = Column(Boolean, default=False, nullable=False)
    quality_flag = Column(String(50), default="approved", nullable=False)  # approved, flagged, rejected
    item_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    module = relationship("Module", back_populates="assessment_items")
    competency = relationship("Competency")
