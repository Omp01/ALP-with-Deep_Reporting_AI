"""
Assignment and AssignmentSubmission models for hands-on labs and project evaluation.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Index, Text, Integer, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Assignment(Base):
    """
    Hands-on assignment, practical lab, or project with structured evaluation rubric.
    """
    __tablename__ = "assignments"
    __table_args__ = (
        Index("uq_assignments_content_item", "content_item_id", unique=True, postgresql_where=text("content_item_id IS NOT NULL")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True, index=True)
    # The lesson item that presents this assignment in the course outline (unique when set).
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    instructions = Column(Text, nullable=False)
    difficulty = Column(String(50), default="intermediate", nullable=False)  # beginner, intermediate, advanced
    max_score = Column(Float, default=100.0, nullable=False)
    rubric = Column(JSONB, default=dict, nullable=False)  # Evaluation criteria with weights
    status = Column(String(50), default="published", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    course = relationship("Course", back_populates="assignments")
    module = relationship("Module", back_populates="assignments")
    competency = relationship("Competency")
    submissions = relationship("AssignmentSubmission", back_populates="assignment", cascade="all, delete-orphan")


class AssignmentSubmission(Base):
    """
    Learner submission record for assignments with AI-assisted or human grading.
    """
    __tablename__ = "assignment_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    learner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_text = Column(Text, nullable=True)
    submission_url = Column(String(1024), nullable=True)
    status = Column(String(50), default="SUBMITTED", nullable=False)  # ASSIGNED, IN_PROGRESS, SUBMITTED, GRADED
    score = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    rubric_scores = Column(JSONB, default=dict, nullable=False)
    is_ai_graded = Column(Boolean, default=False, nullable=False)
    graded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    graded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    assignment = relationship("Assignment", back_populates="submissions")
    learner = relationship("User", foreign_keys=[learner_id])
    graded_by = relationship("User", foreign_keys=[graded_by_id])
