"""Phase 5 competency engine: state, evidence, audit trail, grading results

Revision ID: 007_competency_engine
Revises: 006_learning_events_sessions
Create Date: 2026-09-22 00:00:00.000000

1. `learner_competencies` becomes the full competency state (evidence weight, counts, retry count, recent accuracy,
   time on task, error distribution, trend, links to the latest evidence and update) with one row per
   (tenant, learner, competency). Rows written by the earlier engine are kept but marked `legacy_unverified`: that
   engine recorded every quiz answer as correct (audit C1), so those numbers have no evidence behind them. They are
   never shown as mastery and are replaced by the first real evidence.

2. `evidence_records` and `competency_state_updates` give every mastery figure a chain: the evidence that produced it,
   the previous value, the new value, and the parameters used. Both are append-only, enforced by a trigger.

3. `grading_results` holds each grading act on a written answer (by a model or a person). Append-only.

4. Written-answer support: `expected_answer` and `rubric` on questions and candidates, grading status on answers and
   attempts. `learner_risks.risk_details` keeps structured, explainable reasons.

Idempotent, like 003 to 006: on a fresh database revision 001 has already created tables from the models.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_competency_engine"
down_revision: Union[str, None] = "006_learning_events_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATE_COLUMNS = [
    ("effective_evidence", sa.Column("effective_evidence", sa.Float(), nullable=False, server_default="0")),
    ("correct_count", sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0")),
    ("incorrect_count", sa.Column("incorrect_count", sa.Integer(), nullable=False, server_default="0")),
    ("retry_count", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")),
    ("recent_accuracy", sa.Column("recent_accuracy", sa.Float(), nullable=True)),
    ("time_on_task_seconds", sa.Column("time_on_task_seconds", sa.Integer(), nullable=False, server_default="0")),
    ("error_distribution", sa.Column("error_distribution", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"))),
    ("trend", sa.Column("trend", sa.String(20), nullable=False, server_default="insufficient_data")),
    ("trend_delta", sa.Column("trend_delta", sa.Float(), nullable=True)),
    ("last_evidence_id", sa.Column("last_evidence_id", postgresql.UUID(as_uuid=True), nullable=True)),
    ("last_update_id", sa.Column("last_update_id", postgresql.UUID(as_uuid=True), nullable=True)),
]


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _columns(table: str) -> dict:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _indexes(table: str) -> set:
    return {i["name"] for i in _inspector().get_indexes(table)}


def _fks(table: str) -> set:
    return {f["name"] for f in _inspector().get_foreign_keys(table)}


def _has_check(table: str, name: str) -> bool:
    return any(c["name"] == name for c in _inspector().get_check_constraints(table))


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------- learner_competencies: the competency state
    columns = _columns("learner_competencies")
    first_time = "basis" not in columns
    for name, column in STATE_COLUMNS:
        _add("learner_competencies", column)
    _add("learner_competencies", sa.Column("basis", sa.String(30), nullable=False, server_default="evidence"))
    if first_time:
        # Everything that exists now was written by the earlier engine, without evidence behind it.
        bind.execute(sa.text("UPDATE learner_competencies SET basis = 'legacy_unverified'"))

    # One state per (tenant, learner, competency): keep the newest of any duplicates.
    bind.execute(sa.text("""
        DELETE FROM learner_competencies a USING learner_competencies b
         WHERE a.org_id = b.org_id AND a.user_id = b.user_id AND a.competency_id = b.competency_id
           AND (a.updated_at, a.id) < (b.updated_at, b.id)
    """))
    if "uq_learner_competencies_state" not in _indexes("learner_competencies"):
        op.create_index("uq_learner_competencies_state", "learner_competencies", ["org_id", "user_id", "competency_id"], unique=True)
    if not _has_check("learner_competencies", "ck_learner_competencies_mastery"):
        bind.execute(sa.text("UPDATE learner_competencies SET mastery_score = LEAST(GREATEST(mastery_score, 0), 1), confidence_score = LEAST(GREATEST(confidence_score, 0), 1)"))
        op.create_check_constraint("ck_learner_competencies_mastery", "learner_competencies",
                                   "mastery_score >= 0 AND mastery_score <= 1 AND confidence_score >= 0 AND confidence_score <= 1")

    # -------------------------------------------------------------------------------- evidence_records
    if not _has_table("evidence_records"):
        op.create_table(
            "evidence_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("competency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competencies.id"), nullable=False),
            sa.Column("source_type", sa.String(30), nullable=False),
            sa.Column("source_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning_events.id"), nullable=True),
            sa.Column("response_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("question_responses.id"), nullable=True),
            sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assignment_submissions.id"), nullable=True),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("signal", sa.Float(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("error_type", sa.String(40), nullable=True),
            sa.Column("evidence_quote", sa.Text(), nullable=True),
            sa.Column("difficulty", sa.Float(), nullable=True),
            sa.Column("attempt_number", sa.Integer(), nullable=True),
            sa.Column("response_time_ms", sa.Integer(), nullable=True),
            sa.Column("guess_floor", sa.Float(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    for name, expression in (("ck_evidence_signal", "signal >= 0 AND signal <= 1"), ("ck_evidence_confidence", "confidence >= 0 AND confidence <= 1")):
        if not _has_check("evidence_records", name):
            op.create_check_constraint(name, "evidence_records", expression)
    indexes = _indexes("evidence_records")
    for name, columns in (("ix_evidence_records_org_id", ["org_id"]), ("ix_evidence_records_user_id", ["user_id"]),
                          ("ix_evidence_records_competency_id", ["competency_id"]), ("ix_evidence_records_occurred_at", ["occurred_at"])):
        if name not in indexes:
            op.create_index(name, "evidence_records", columns)
    if "uq_evidence_event_competency" not in indexes:
        op.create_index("uq_evidence_event_competency", "evidence_records", ["source_event_id", "competency_id"], unique=True,
                        postgresql_where=sa.text("source_event_id IS NOT NULL"))
    if "fk_evidence_competency_org" not in _fks("evidence_records"):
        op.create_foreign_key("fk_evidence_competency_org", "evidence_records", "competencies", ["competency_id", "org_id"], ["id", "org_id"])

    # ------------------------------------------------------------------------ competency_state_updates
    if not _has_table("competency_state_updates"):
        op.create_table(
            "competency_state_updates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("competency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competencies.id"), nullable=False),
            sa.Column("state_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learner_competencies.id"), nullable=False),
            sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_records.id"), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("previous_mastery", sa.Float(), nullable=True),
            sa.Column("new_mastery", sa.Float(), nullable=False),
            sa.Column("previous_confidence", sa.Float(), nullable=True),
            sa.Column("new_confidence", sa.Float(), nullable=False),
            sa.Column("signal", sa.Float(), nullable=False),
            sa.Column("weight", sa.Float(), nullable=False),
            sa.Column("method", sa.String(30), nullable=False),
            sa.Column("params", postgresql.JSONB(), nullable=False),
            sa.Column("note", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    indexes = _indexes("competency_state_updates")
    for name, columns in (("ix_competency_state_updates_org_id", ["org_id"]), ("ix_competency_state_updates_user_id", ["user_id"]),
                          ("ix_competency_state_updates_competency_id", ["competency_id"]), ("ix_competency_state_updates_created_at", ["created_at"]),
                          ("ix_competency_state_updates_state_seq", ["state_id", "sequence"])):
        if name not in indexes:
            op.create_index(name, "competency_state_updates", columns)
    if not any(u["name"] == "uq_competency_state_updates_evidence" for u in _inspector().get_unique_constraints("competency_state_updates")) \
            and "uq_competency_state_updates_evidence" not in indexes:
        op.create_unique_constraint("uq_competency_state_updates_evidence", "competency_state_updates", ["evidence_id"])
    if "uq_competency_state_updates_state_seq" not in indexes:
        op.create_index("uq_competency_state_updates_state_seq", "competency_state_updates", ["state_id", "sequence"], unique=True)
    if "fk_state_updates_competency_org" not in _fks("competency_state_updates"):
        op.create_foreign_key("fk_state_updates_competency_org", "competency_state_updates", "competencies", ["competency_id", "org_id"], ["id", "org_id"])

    # --------------------------------------------------------------------------------- grading_results
    if not _has_table("grading_results"):
        op.create_table(
            "grading_results",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("response_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("question_responses.id"), nullable=False),
            sa.Column("source", sa.String(10), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("provider", sa.String(100), nullable=True),
            sa.Column("model", sa.String(100), nullable=True),
            sa.Column("prompt_version", sa.String(30), nullable=True),
            sa.Column("correctness_signal", sa.Float(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("error_type", sa.String(40), nullable=True),
            sa.Column("evidence_quote", sa.Text(), nullable=True),
            sa.Column("quote_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("rubric_scores", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("feedback", sa.Text(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("graded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    for name, expression in (
        ("ck_grading_signal", "correctness_signal >= 0 AND correctness_signal <= 1"),
        ("ck_grading_confidence", "confidence >= 0 AND confidence <= 1"),
        ("ck_grading_source", "source IN ('ai', 'human')"),
        ("ck_grading_status", "status IN ('accepted', 'needs_review')"),
    ):
        if not _has_check("grading_results", name):
            op.create_check_constraint(name, "grading_results", expression)
    indexes = _indexes("grading_results")
    for name, columns in (("ix_grading_results_org_id", ["org_id"]), ("ix_grading_results_response_id", ["response_id"]), ("ix_grading_results_created_at", ["created_at"])):
        if name not in indexes:
            op.create_index(name, "grading_results", columns)

    _add("grading_results", sa.Column("note", sa.Text(), nullable=True))

    # -------------------------------------------------------------- written answers, risks
    _add("quiz_questions", sa.Column("expected_answer", sa.Text(), nullable=True))
    _add("quiz_questions", sa.Column("rubric", postgresql.JSONB(), nullable=True))
    _add("question_responses", sa.Column("grading_status", sa.String(20), nullable=False, server_default="graded"))
    _add("question_responses", sa.Column("score_fraction", sa.Float(), nullable=True))
    _add("question_responses", sa.Column("grading_result_id", postgresql.UUID(as_uuid=True), nullable=True))
    _add("quiz_attempts", sa.Column("grading_status", sa.String(20), nullable=False, server_default="graded"))
    _add("question_candidates", sa.Column("expected_answer", sa.Text(), nullable=True))
    _add("question_candidates", sa.Column("rubric", postgresql.JSONB(), nullable=True))
    _add("learner_risks", sa.Column("risk_details", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    for table, name in (("question_responses", "ck_question_responses_grading_status"), ("quiz_attempts", "ck_quiz_attempts_grading_status")):
        if not _has_check(table, name):
            op.create_check_constraint(name, table, "grading_status IN ('graded', 'needs_review')")
    if not _has_check("question_responses", "ck_question_responses_score_fraction"):
        op.create_check_constraint("ck_question_responses_score_fraction", "question_responses", "score_fraction IS NULL OR (score_fraction >= 0 AND score_fraction <= 1)")

    # ------------------------------------------------------------------------------ append-only
    bind.execute(sa.text("""
        CREATE OR REPLACE FUNCTION alms_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
    """))
    for table in ("evidence_records", "competency_state_updates", "grading_results"):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}"))
        bind.execute(sa.text(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION alms_append_only()"))


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("evidence_records", "competency_state_updates", "grading_results"):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS alms_append_only()"))

    for table in ("competency_state_updates", "grading_results", "evidence_records"):
        if _has_table(table):
            op.drop_table(table)

    for table, name in (("question_responses", "ck_question_responses_score_fraction"), ("question_responses", "ck_question_responses_grading_status"),
                        ("quiz_attempts", "ck_quiz_attempts_grading_status"), ("learner_competencies", "ck_learner_competencies_mastery")):
        if _has_check(table, name):
            op.drop_constraint(name, table, type_="check")
    for table, column in (("learner_risks", "risk_details"), ("question_candidates", "rubric"), ("question_candidates", "expected_answer"),
                          ("quiz_attempts", "grading_status"), ("question_responses", "grading_result_id"), ("question_responses", "score_fraction"),
                          ("question_responses", "grading_status"), ("quiz_questions", "rubric"), ("quiz_questions", "expected_answer")):
        if column in _columns(table):
            op.drop_column(table, column)

    if "uq_learner_competencies_state" in _indexes("learner_competencies"):
        op.drop_index("uq_learner_competencies_state", table_name="learner_competencies")
    for name in ["basis"] + [n for n, _ in STATE_COLUMNS]:
        if name in _columns("learner_competencies"):
            op.drop_column("learner_competencies", name)
