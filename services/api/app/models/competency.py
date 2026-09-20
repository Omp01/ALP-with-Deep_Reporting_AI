"""
Competency models: Framework, Mappings, Learner State, History, and Gaps.
"""

from datetime import datetime
import uuid
from sqlalchemy import (
    CheckConstraint,
    Column,
    Index,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Competency(Base):
    """
    Core competency node in the curriculum knowledge graph.
    """
    __tablename__ = "competencies"
    # (id, org_id) is unique so that tables referencing a competency can carry a
    # composite foreign key that makes the database itself refuse cross-tenant links.
    __table_args__ = (
        UniqueConstraint("id", "org_id", name="uq_competencies_id_org"),
        CheckConstraint("difficulty >= 0 AND difficulty <= 1", name="ck_competencies_difficulty_range"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    taxonomy_level = Column(String(50), default="remember", nullable=False)  # remember, understand, apply, analyze, evaluate, create
    parent_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True, index=True)
    domain = Column(String(100), nullable=True, index=True)  # e.g. "python", "sql", "genai"
    difficulty = Column(Float, nullable=False, default=0.5, server_default="0.5")  # 0 (easiest) .. 1 (hardest)
    competency_metadata = Column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="competencies")
    parent = relationship("Competency", remote_side=[id], backref="sub_competencies")
    course_mappings = relationship("CourseCompetency", back_populates="competency", cascade="all, delete-orphan")
    module_mappings = relationship("ModuleCompetency", back_populates="competency", cascade="all, delete-orphan")
    learner_records = relationship("LearnerCompetency", back_populates="competency", cascade="all, delete-orphan")
    skill_gaps = relationship("SkillGap", back_populates="competency", cascade="all, delete-orphan")


class CompetencyPrerequisite(Base):
    """
    Directed edge of the skill graph: `competency_id` REQUIRES `prerequisite_id`.

    Example: JOINs requires SQL Basics -> a row (competency=JOINs, prerequisite=SQL Basics).

    Tenant integrity is enforced by the database: both endpoints are referenced
    through composite (id, org_id) foreign keys, so an edge can only ever connect
    two competencies of the SAME organisation as the edge itself. Acyclicity is
    enforced in `app.services.skill_graph` (a cycle check cannot be a simple
    constraint).
    """
    __tablename__ = "competency_prerequisites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["competency_id", "org_id"],
            ["competencies.id", "competencies.org_id"],
            ondelete="CASCADE",
            name="fk_comp_prereq_competency_org",
        ),
        ForeignKeyConstraint(
            ["prerequisite_id", "org_id"],
            ["competencies.id", "competencies.org_id"],
            ondelete="CASCADE",
            name="fk_comp_prereq_prerequisite_org",
        ),
        CheckConstraint("competency_id <> prerequisite_id", name="ck_comp_prereq_not_self"),
        CheckConstraint("min_mastery >= 0 AND min_mastery <= 1", name="ck_comp_prereq_min_mastery"),
    )

    competency_id = Column(UUID(as_uuid=True), primary_key=True)
    prerequisite_id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    # Mastery of the prerequisite at which the dependent competency counts as unblocked.
    min_mastery = Column(Float, nullable=False, default=0.6, server_default="0.6")
    rationale = Column(Text, nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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
    # mastery_score is the mastery PROBABILITY (0..1). It is written only by app/competency/service.py, from
    # stored evidence, and every change has a row in `competency_state_updates`.
    mastery_score = Column(Float, default=0.0, nullable=False)
    confidence_score = Column(Float, default=0.0, nullable=False)  # effective_evidence / (effective_evidence + K)
    data_points_count = Column(Integer, default=0, nullable=False)  # evidence records applied
    status = Column(String(50), default="novice", nullable=False)  # novice, developing, competent, proficient, expert
    last_assessed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ---- the rest of the competency state (Phase 5)
    effective_evidence = Column(Float, default=0.0, nullable=False, server_default="0")   # sum of evidence weights
    correct_count = Column(Integer, default=0, nullable=False, server_default="0")
    incorrect_count = Column(Integer, default=0, nullable=False, server_default="0")
    retry_count = Column(Integer, default=0, nullable=False, server_default="0")          # evidence from attempt 2 or later
    recent_accuracy = Column(Float, nullable=True)                                          # weighted mean signal, last 10 evidence records
    time_on_task_seconds = Column(Integer, default=0, nullable=False, server_default="0")
    error_distribution = Column(JSONB, default=dict, nullable=False, server_default="{}")   # {"unknown": 3, ...}
    trend = Column(String(20), default="insufficient_data", nullable=False, server_default="insufficient_data")
    trend_delta = Column(Float, nullable=True)
    last_evidence_id = Column(UUID(as_uuid=True), nullable=True)
    last_update_id = Column(UUID(as_uuid=True), nullable=True)
    # `evidence`: produced by the engine. `legacy_unverified`: written by an earlier version with no evidence chain;
    # such rows are never shown as mastery and are replaced on the first real evidence.
    basis = Column(String(30), default="evidence", nullable=False, server_default="evidence")

    # Relationships
    user = relationship("User", back_populates="learner_competencies")
    competency = relationship("Competency", back_populates="learner_records")
    history = relationship("CompetencyHistory", back_populates="learner_competency", cascade="all, delete-orphan", order_by="CompetencyHistory.recorded_at")


Index("uq_learner_competencies_state", LearnerCompetency.org_id, LearnerCompetency.user_id, LearnerCompetency.competency_id, unique=True)


class EvidenceRecord(Base):
    """
    One piece of evidence about one learner's competency: a graded answer, a graded assignment.

    Immutable (a database trigger rejects UPDATE and DELETE). It links back to the event and the answer row it came from,
    and carries the deterministic inputs the mastery update used. Citations in reports point at these ids.
    """
    __tablename__ = "evidence_records"
    __table_args__ = (
        CheckConstraint("signal >= 0 AND signal <= 1", name="ck_evidence_signal"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_evidence_confidence"),
        Index("uq_evidence_event_competency", "source_event_id", "competency_id", unique=True, postgresql_where="source_event_id IS NOT NULL"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False, index=True)
    # question_answered | assignment_graded | answer_graded | seed_history (clearly synthetic demo data)
    source_type = Column(String(30), nullable=False)
    source_event_id = Column(UUID(as_uuid=True), ForeignKey("learning_events.id"), nullable=True)
    response_id = Column(UUID(as_uuid=True), ForeignKey("question_responses.id"), nullable=True)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("assignment_submissions.id"), nullable=True)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    signal = Column(Float, nullable=False)             # 0 (no evidence of the skill) .. 1 (full evidence)
    confidence = Column(Float, nullable=False)         # how much the SOURCE is trusted: 1.0 deterministic or human, model's own for AI
    error_type = Column(String(40), nullable=True)
    evidence_quote = Column(Text, nullable=True)       # verbatim from the learner's response, when the grader gave one
    difficulty = Column(Float, nullable=True)
    attempt_number = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    guess_floor = Column(Float, nullable=True)         # chance of a correct answer by guessing, when known (multiple choice: 1/options)
    occurred_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CompetencyStateUpdate(Base):
    """
    The audit trail of mastery: one row per evidence record applied, with the numbers before and after.

    It answers "why did mastery go from 0.41 to 0.68?" with an actual chain: the previous mastery, the evidence,
    the parameters used, and the new mastery. Immutable.
    """
    __tablename__ = "competency_state_updates"
    __table_args__ = (
        Index("ix_competency_state_updates_state_seq", "state_id", "sequence"),
        UniqueConstraint("evidence_id", name="uq_competency_state_updates_evidence"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False, index=True)
    state_id = Column(UUID(as_uuid=True), ForeignKey("learner_competencies.id"), nullable=False)
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("evidence_records.id"), nullable=False)
    sequence = Column(Integer, nullable=False)          # 1, 2, 3 ... within the state
    previous_mastery = Column(Float, nullable=True)     # NULL for the first update: the prior below was used
    new_mastery = Column(Float, nullable=False)
    previous_confidence = Column(Float, nullable=True)
    new_confidence = Column(Float, nullable=False)
    signal = Column(Float, nullable=False)
    weight = Column(Float, nullable=False)              # evidence weight actually applied (source confidence x retry discount)
    method = Column(String(30), nullable=False)         # bkt_soft_v1
    params = Column(JSONB, nullable=False)              # prior, learn, slip, guess after difficulty adjustment, ...
    note = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


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
