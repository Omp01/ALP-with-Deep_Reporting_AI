"""
Declarative SQLAlchemy Models for Adaptive Engine persistence.
Exactly matches the Alembic migration schema.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Float, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Competency(Base):
    __tablename__ = "competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    taxonomy_level = Column(String(50), default="remember")
    parent_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class LearnerCompetency(Base):
    __tablename__ = "learner_competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False)
    mastery_score = Column(Float, default=0.0, nullable=False)
    confidence_score = Column(Float, default=0.0, nullable=False)
    data_points_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="novice", nullable=False)
    last_assessed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    competency = relationship("Competency", lazy="selectin")


class CompetencyHistory(Base):
    __tablename__ = "competency_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    learner_competency_id = Column(UUID(as_uuid=True), ForeignKey("learner_competencies.id"), nullable=False)
    mastery_score = Column(Float, nullable=False)
    event_id = Column(UUID(as_uuid=True), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AdaptiveSession(Base):
    __tablename__ = "adaptive_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)
    current_module_id = Column(UUID(as_uuid=True), nullable=True)
    state = Column(String(50), default="active", nullable=False)
    current_difficulty = Column(Float, default=0.5, nullable=False)
    recommended_next_action = Column(String(100), nullable=True)
    session_metadata = Column("metadata", JSONB, default=dict)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class SessionSequenceStep(Base):
    __tablename__ = "session_sequence_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("adaptive_sessions.id"), nullable=False)
    step_order = Column(Integer, default=1, nullable=False)
    item_type = Column(String(50), nullable=False)
    item_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(String(50), default="presented", nullable=False)
    result_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SkillGap(Base):
    __tablename__ = "skill_gaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    team_id = Column(UUID(as_uuid=True), nullable=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False)
    current_mastery = Column(Float, nullable=False)
    target_mastery = Column(Float, nullable=False)
    gap_size = Column(Float, nullable=False)
    severity = Column(String(50), default="medium", nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    competency = relationship("Competency", lazy="selectin")


class LearningEvent(Base):
    __tablename__ = "learning_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    course_id = Column(UUID(as_uuid=True), nullable=True)
    module_id = Column(UUID(as_uuid=True), nullable=True)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSONB, default=dict)
    timestamp = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    module_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(255), nullable=False)
    content_type = Column(String(32), default="text")
    sort_order = Column(Integer, default=0)


class Module(Base):
    __tablename__ = "modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(255), nullable=False)
    sequence_order = Column(Integer, default=0)


class UserTeam(Base):
    __tablename__ = "user_teams"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    team_id = Column(UUID(as_uuid=True), primary_key=True)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
