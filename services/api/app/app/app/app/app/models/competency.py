"""
Competency models: Framework, Mappings, Learner State, History, and Gaps.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Competency(Base):
    """
    Core competency node in the curriculum knowledge graph.
    """
    __tablename__ = "competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    taxonomy_level = Column(String(50), default="remember", nullable=False)  # remember, understand, apply, analyze, evaluate, create
    parent_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="competencies")
    parent = relationship("Competency", remote_side=[id], backref="sub_competencies")
    course_mappings = relationship("CourseCompetency", back_populates="competency", cascade="all, delete-orphan")
    module_mappings = relationship("ModuleCompetency", back_populates="competency", cascade="all, delete-orphan")
    learner_records = relationship("LearnerCompetency", back_populates="competency", cascade="all, delete-orphan")
    skill_gaps = relationship("SkillGap", back_populates="competency", cascade="all, delete-orphan")


class CourseCompetency(Base):
    """
    Mapping between Courses and Target Competencies.
    """
    __tablename__ = "course_competencies"

    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), primary_key=True)
    target_mastery = Column(Float, default=0.8, nullable=False)
    is_primary = Column(Boolean, default=True, nullable=False)

    # Relationships
    course = relationship("Course", back_populates="competency_mappings")
    competency = relationship("Competency", back_populates="course_mappings")


class ModuleCompetency(Base):
    """
    Mapping between Modules and targeted Competencies with contribution weight.
    """
    __tablename__ = "module_competencies"

    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), primary_key=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), primary_key=True)
    weight = Column(Float, default=1.0, nullable=False)

    # Relationships
    module = relationship("Module", back_populates="competency_mappings")
    competency = relationship("Competency", back_populates="module_mappings")


class LearnerCompetency(Base):
    """
    Real-time estimated mastery and status of a learner in a specific competency.
    """
    __tablename__ = "learner_competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False, index=True)
    mastery_score = Column(Float, default=0.0, nullable=False)  # 0.0 to 1.0
    confidence_score = Column(Float, default=0.0, nullable=False)  # Bayesian / data density confidence 0.0 to 1.0
    data_points_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="novice", nullable=False)  # novice, developing, competent, proficient, expert
    last_assessed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="learner_competencies")
    competency = relationship("Competency", back_populates="learner_records")
    history = relationship("CompetencyHistory", back_populates="learner_competency", cascade="all, delete-orphan", order_by="CompetencyHistory.recorded_at")


class CompetencyHistory(Base):
    """
    Point-in-time progression log of mastery updates.
    """
    __tablename__ = "competency_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    learner_competency_id = Column(UUID(as_uuid=True), ForeignKey("learner_competencies.id", ondelete="CASCADE"), nullable=False, index=True)
    mastery_score = Column(Float, nullable=False)
    event_id = Column(UUID(as_uuid=True), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    learner_competency = relationship("LearnerCompetency", back_populates="history")


class SkillGap(Base):
    """
    Identified competency deficit at the learner or cohort level.
    """
    __tablename__ = "skill_gaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False, index=True)
    current_mastery = Column(Float, nullable=False)
    target_mastery = Column(Float, nullable=False)
    gap_size = Column(Float, nullable=False)  # target_mastery - current_mastery
    severity = Column(String(50), default="medium", nullable=False)  # low, medium, high, critical
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    competency = relationship("Competency", back_populates="skill_gaps")
    team = relationship("Team", back_populates="skill_gaps")
