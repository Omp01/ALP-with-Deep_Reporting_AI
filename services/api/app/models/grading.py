"""
Grading results for written answers.

The grading agent (app/grading/) turns a written answer into a SIGNAL: how much evidence of the skill the answer shows,
how sure the grader is, what kind of error, and a quote from the answer that supports it. It never produces mastery;
the deterministic engine (app/competency/) does that from the signal. A row here is one grading act, by a model or a
person, and is never changed: a later grading is a new row.
"""

from datetime import datetime
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class GradingResult(Base):
    __tablename__ = "grading_results"
    __table_args__ = (
        CheckConstraint("correctness_signal >= 0 AND correctness_signal <= 1", name="ck_grading_signal"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_grading_confidence"),
        CheckConstraint("source IN ('ai', 'human')", name="ck_grading_source"),
        CheckConstraint("status IN ('accepted', 'needs_review')", name="ck_grading_status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    response_id = Column(UUID(as_uuid=True), ForeignKey("question_responses.id"), nullable=False, index=True)
    source = Column(String(10), nullable=False)          # ai | human
    status = Column(String(20), nullable=False)          # accepted (used as evidence) | needs_review (not used)
    provider = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    prompt_version = Column(String(30), nullable=True)
    correctness_signal = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    error_type = Column(String(40), nullable=True)
    evidence_quote = Column(Text, nullable=True)
    quote_verified = Column(Boolean, nullable=False, default=False)   # the quote really is in the learner's answer
    rubric_scores = Column(JSONB, nullable=False, default=dict)
    feedback = Column(Text, nullable=True)               # what the learner is shown
    note = Column(Text, nullable=True)                   # for reviewers: why the answer needs review
    graded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    attempts = Column(Integer, nullable=False, default=1)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
