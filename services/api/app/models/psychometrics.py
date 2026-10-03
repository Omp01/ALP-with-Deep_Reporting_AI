"""
Psychometrics data models: in-course questions, learner responses, and longitudinal progression.
Strictly non-diagnostic learning constructs (confidence, perceived understanding, cognitive effort, application readiness).
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class PsychometricQuestion(Base):
    """
    Versioned psychometric self-report question mapped to a course, module, topic, or content item.
    Categorized by construct and learning stage.
    """
    __tablename__ = "psychometric_questions"
    __table_args__ = (
        Index("ix_psychometric_q_stage", "course_id", "learning_stage"),
        Index("ix_psychometric_q_topic", "topic", "construct"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), nullable=True, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=True, index=True)
    
    topic = Column(String(255), nullable=True, index=True)
    # CONFIDENCE, PERCEIVED_UNDERSTANDING, COGNITIVE_EFFORT, LEARNING_DIFFICULTY, APPLICATION_READINESS, RETENTION_CONFIDENCE, ENGAGEMENT, SELF_ASSESSED_MASTERY, REFLECTION, MOTIVATION
    construct = Column(String(50), nullable=False, index=True)
    # before_course, during_course, after_topic, after_video, after_assessment, end_of_module, end_of_course
    learning_stage = Column(String(50), nullable=False, index=True)
    
    question_text = Column(Text, nullable=False)
    scale_type = Column(String(30), default="likert_5", nullable=False)
    scale_min = Column(Integer, default=1, nullable=False)
    scale_max = Column(Integer, default=5, nullable=False)
    scale_labels = Column(JSONB, nullable=False)  # e.g. ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"]
    
    # If True, higher rating = higher score (favorable). If False, higher rating = higher friction (reverse-keyed)
    higher_is_favorable = Column(Boolean, default=True, nullable=False)
    version = Column(String(20), default="1.0.0", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    course = relationship("Course")
    module = relationship("Module")
    content_item = relationship("ContentItem")
    responses = relationship("LearnerPsychometricResponse", back_populates="question", cascade="all, delete-orphan")


class LearnerPsychometricResponse(Base):
    """
    Learner's response to an in-course psychometric question.
    Stores both the raw rating and the normalized score, along with context metadata and formula version.
    """
    __tablename__ = "learner_psychometric_responses"
    __table_args__ = (
        Index("ix_learner_psych_user_topic", "user_id", "topic"),
        Index("ix_learner_psych_user_stage", "user_id", "learning_stage"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("psychometric_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="SET NULL"), nullable=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True)
    topic = Column(String(255), nullable=True, index=True)
    
    construct = Column(String(50), nullable=False, index=True)
    learning_stage = Column(String(50), nullable=False, index=True)
    
    raw_response = Column(Float, nullable=False)
    normalized_score = Column(Float, nullable=False)  # 0.0 .. 100.0
    methodology_version = Column(String(20), default="1.0.0", nullable=False)
    context_metadata = Column(JSONB, nullable=True)  # stores associated assessment scores, prompt trigger reason, etc.
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    question = relationship("PsychometricQuestion", back_populates="responses")


class LearnerTopicProgression(Base):
    """
    Longitudinal record of a learner's progression for a specific topic across the 7 learning stages:
    Baseline -> Learning -> Practice -> Assessment -> Revision -> Reassessment -> Retention.
    Pairs subjective confidence with objective knowledge performance to compute the calibration gap.
    """
    __tablename__ = "learner_topic_progressions"
    __table_args__ = (
        Index("ix_topic_prog_user_topic", "user_id", "topic", "stage"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
    topic = Column(String(255), nullable=False, index=True)
    
    # baseline, learning, practice, assessment, revision, reassessment, retention
    stage = Column(String(50), nullable=False)
    confidence_score = Column(Float, default=0.0, nullable=False)     # 0..100
    performance_score = Column(Float, default=0.0, nullable=False)    # 0..100
    first_attempt_acc = Column(Float, default=0.0, nullable=False)    # 0..100
    gap = Column(Float, default=0.0, nullable=False)                  # confidence - performance
    # calibrated_mastery, blind_spot, underestimated_competence, accurate_struggle
    alignment_quadrant = Column(String(50), default="calibrated_mastery", nullable=False)
    methodology_version = Column(String(20), default="1.0.0", nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    course = relationship("Course")
