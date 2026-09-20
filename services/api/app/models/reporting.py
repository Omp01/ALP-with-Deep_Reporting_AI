"""
Reporting models: AI Insights, Scheduled Reports, and Digests.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class AIInsight(Base):
    """
    Grounded AI narrative report with verifiable source citations and confidence metrics.
    """
    __tablename__ = "ai_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type = Column(String(50), nullable=False, index=True)  # learner_progress, skill_gap, risk_summary, cohort_performance, executive
    scope_type = Column(String(50), nullable=False, index=True)  # learner, cohort, course, executive
    scope_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    narrative_text = Column(Text, nullable=False)
    structured_data = Column(JSONB, default=dict, nullable=False)
    confidence_score = Column(Float, default=0.85, nullable=False)
    citations = Column(JSONB, default=list, nullable=False)  # List of {source_type, source_id, snippet, confidence}
    model_used = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    organization = relationship("Organization")


class ScheduledReport(Base):
    """
    Cadence definition for automated report delivery.
    """
    __tablename__ = "scheduled_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False)
    schedule_cron = Column(String(50), nullable=False)  # standard cron expression
    recipients = Column(JSONB, default=list, nullable=False)  # emails / user_ids
    template_id = Column(String(100), nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization")
    digests = relationship("ReportDigest", back_populates="scheduled_report", cascade="all, delete-orphan")


class ReportDigest(Base):
    """
    Generated output delivery instance of a scheduled report.
    """
    __tablename__ = "report_digests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_report_id = Column(UUID(as_uuid=True), ForeignKey("scheduled_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_content = Column(Text, nullable=False)
    sent_to = Column(JSONB, default=list, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(50), default="success", nullable=False)  # success, failed, partial

    # Relationships
    scheduled_report = relationship("ScheduledReport", back_populates="digests")


class Report(Base):
    """
    A grounded report: the evidence package it was built from, and the claims that survived citation validation.

    The package is stored with the report so every citation can be opened later, exactly as it was when the report was written.
    """
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_scope", "org_id", "audience", "scope_id", "created_at"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    audience = Column(String(20), nullable=False)          # learner | team | ld | organization
    scope_type = Column(String(20), nullable=False)        # learner | team | organization
    scope_id = Column(UUID(as_uuid=True), nullable=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    requested_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_by = Column(String(20), nullable=False)      # ai | deterministic
    ai_status = Column(String(20), nullable=False)         # ok | unavailable | invalid | skipped
    ai_note = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    prompt_version = Column(String(30), nullable=True)
    package_hash = Column(String(64), nullable=False)
    package = Column(JSONB, nullable=False)                # records, metrics, patterns (every evidence id resolves here)
    summary = Column(Text, nullable=True)
    claims = Column(JSONB, nullable=False, default=list)              # accepted and flagged claims
    rejected_claims = Column(JSONB, nullable=False, default=list)     # what validation refused, and why
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
