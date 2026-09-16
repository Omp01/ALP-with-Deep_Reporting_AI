"""
Declarative SQLAlchemy Models for Reporting Engine persistence.
Directly maps to the PostgreSQL database schema.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Float, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)


class Course(Base):
    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(50), default="published")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(50), default="active")
    progress_pct = Column(Float, default=0.0)


class Competency(Base):
    __tablename__ = "competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=False)
    taxonomy_level = Column(String(50), default="remember")


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
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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


class LearnerRisk(Base):
    __tablename__ = "learner_risks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)
    risk_level = Column(String(50), default="low", nullable=False)
    risk_score = Column(Float, default=0.0, nullable=False)
    risk_factors = Column(JSONB, default=list, nullable=False)
    recommended_actions = Column(JSONB, default=list, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    report_type = Column(String(50), nullable=False)
    scope_type = Column(String(50), nullable=False)
    scope_id = Column(UUID(as_uuid=True), nullable=True)
    narrative_text = Column(Text, nullable=False)
    structured_data = Column(JSONB, default=dict, nullable=False)
    confidence_score = Column(Float, default=0.85, nullable=False)
    citations = Column(JSONB, default=list, nullable=False)
    model_used = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False)
    schedule_cron = Column(String(50), nullable=False)
    recipients = Column(JSONB, default=list, nullable=False)
    template_id = Column(String(100), nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReportDigest(Base):
    __tablename__ = "report_digests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    scheduled_report_id = Column(UUID(as_uuid=True), ForeignKey("scheduled_reports.id"), nullable=False)
    generated_content = Column(Text, nullable=False)
    sent_to = Column(JSONB, default=list, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(50), default="success", nullable=False)


class UserTeam(Base):
    __tablename__ = "user_teams"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    team_id = Column(UUID(as_uuid=True), primary_key=True)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
