"""
IngestionJob and QuestionCandidate models for the content ingestion pipeline.
"""

from datetime import datetime
import uuid
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base

JOB_STATUSES = ("pending", "processing", "ready_for_review", "needs_attention", "failed", "completed")
CANDIDATE_STATUSES = ("pending", "approved", "rejected", "published")


class IngestionJob(Base):
    """
    Tracks one run of the ingestion pipeline for one piece of content.

    status:
      pending           accepted, not started
      processing        a stage is running
      ready_for_review  every stage finished; an administrator can review and publish
      needs_attention   the content exists but a stage (usually AI analysis, or a missing
                        transcript) did not complete; the administrator can retry or fill it in
      failed            the content could not be processed at all (e.g. extraction failed)
      completed         reviewed and published
    """
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in JOB_STATUSES) + ")",
            name="ck_ingestion_jobs_status",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="SET NULL"), nullable=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True, index=True)
    source_type = Column(String(20), default="upload", nullable=False)  # upload | youtube
    source_url = Column(String(2048), nullable=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, pptx, txt, md, mp4, mp3, youtube ...
    file_size = Column(Integer, default=0, nullable=False)
    storage_path = Column(String(1024), nullable=True)
    status = Column(String(50), default="pending", nullable=False, index=True)
    stage = Column(String(40), nullable=True)
    # [{"name": "extract", "status": "done", "started_at": ..., "finished_at": ..., "detail": ..., "error": ...}]
    stages = Column(JSONB, default=list, nullable=False)
    error_code = Column(String(60), nullable=True)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    result_summary = Column(JSONB, default=dict, nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    organization = relationship("Organization")
    creator = relationship("User")
    module = relationship("Module")


class QuestionCandidate(Base):
    """
    A question awaiting administrator review.

    Candidates are invisible to learners. Approving one marks it publishable; publishing
    the content turns approved candidates into real quiz questions.
    """
    __tablename__ = "question_candidates"
    __table_args__ = (
        CheckConstraint("difficulty >= 0 AND difficulty <= 1", name="ck_question_candidates_difficulty"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in CANDIDATE_STATUSES) + ")",
            name="ck_question_candidates_status",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True)
    question_type = Column(String(30), default="multiple_choice", nullable=False)
    question_text = Column(Text, nullable=False)
    # [{"id": "a", "text": "...", "is_correct": false}, ...]
    options = Column(JSONB, default=list, nullable=False)
    explanation = Column(Text, nullable=True)
    expected_answer = Column(Text, nullable=True)   # short_answer / open_ended only
    rubric = Column(JSONB, nullable=True)           # short_answer / open_ended only
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True)
    competency_name = Column(String(255), nullable=True)  # name of a proposed competency not yet created
    difficulty = Column(Float, default=0.5, nullable=False)
    source_quote = Column(Text, nullable=True)  # verbatim passage the question is based on
    chunk_index = Column(Integer, nullable=True)
    origin = Column(String(20), default="generated", nullable=False)  # generated | manual
    status = Column(String(20), default="pending", nullable=False, index=True)
    edited = Column(Boolean, default=False, nullable=False)
    published_question_id = Column(UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    content_item = relationship("ContentItem")
    competency = relationship("Competency")
