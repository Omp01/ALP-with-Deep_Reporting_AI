"""
Login check-in: an AI-written quiz on the learner's own course material and a short self-report, with the scores and report
that came out of it. See docs/CHECKIN.md.
"""

from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class Checkin(Base):
    """
    One check-in. The questions are stored with their answers and the passage each was drawn from, so a score can always be
    recomputed and every question can be traced to the material. The self-report belongs to the learner alone.
    """
    __tablename__ = "checkins"
    __table_args__ = (Index("ix_checkins_learner", "org_id", "learner_id", "created_at"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    learner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="generating")   # generating | ready | completed | skipped | failed
    quiz = Column(JSONB, nullable=False, default=list)                   # verified questions, with the correct answer and source passage
    psychometric = Column(JSONB, nullable=False, default=list)           # self-report statements: id, construct, text, reverse
    answers = Column(JSONB, nullable=False, default=dict)                # what the learner chose
    scores = Column(JSONB, nullable=False, default=dict)
    report = Column(JSONB, nullable=False, default=dict)
    provenance = Column(JSONB, nullable=False, default=dict)             # provider, model, rejected questions, passages used
    error_code = Column(String(40), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ready_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
