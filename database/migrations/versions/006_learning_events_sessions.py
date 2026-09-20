"""Phase 4 learning events and sessions

Revision ID: 006_learning_events_sessions
Revises: 005_content_ingestion
Create Date: 2026-09-21 00:00:00.000000

1. `learning_sessions` is the real session concept (started_at, ended_at, context, last
   activity, why it ended). Until now events pointed at `adaptive_sessions`, which is the
   adaptive engine's working state. Existing adaptive sessions are copied across with the
   same ids so every existing event still resolves. `adaptive_sessions` is left alone.

2. `learning_events` gains the reference columns the spec asks for (`assessment_id`,
   `question_id`, `competency_id`; existing rows are filled from their payloads where the
   referenced row exists in the same tenant), `received_at` (when the server recorded the
   event, distinct from `timestamp`, when it happened) and `idempotency_key`, unique per
   tenant, which replaces "the client chooses the primary key" (audit R7: one tenant's id
   could suppress another tenant's event).

3. Events become append-only, enforced by the database: a trigger rejects UPDATE and
   DELETE. Foreign keys that could rewrite or erase evidence (`ON DELETE CASCADE` on users
   and organisations, `SET NULL` on course/module/content) become plain restrictions, so
   evidence can neither vanish nor be rewritten when something it refers to is removed.
   A composite key (session_id, org_id, user_id) makes it impossible for an event to point
   at another learner's or another tenant's session.

4. `event_outbox` records which events still have to be published to the stream, so a Redis
   outage delays delivery instead of losing it (audit A5: the old code swallowed the error).

5. `quiz_questions.difficulty` and `question_responses.response_time_ms / error_type` hold
   the per-answer evidence the spec lists. All are nullable: unknown stays unknown.

Idempotent, like 003 to 005.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_learning_events_sessions"
down_revision: Union[str, None] = "005_content_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

END_REASONS = ("explicit", "idle", "superseded")
ERROR_TYPES = (
    "conceptual_misunderstanding", "procedural_error", "calculation_error", "misreading",
    "careless_error", "knowledge_gap", "unknown",
)
UUID_RE = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _columns(table: str) -> dict:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _fk_names(table: str) -> dict:
    return {fk["name"]: fk for fk in _inspector().get_foreign_keys(table)}


def _index_names(table: str) -> set:
    return {i["name"] for i in _inspector().get_indexes(table)}


def _has_check(table: str, name: str) -> bool:
    return any(c["name"] == name for c in _inspector().get_check_constraints(table))


def _has_unique(table: str, name: str) -> bool:
    return any(c["name"] == name for c in _inspector().get_unique_constraints(table))


def _restrict_fk(table: str, name: str, cols: list, ref_table: str, ref_cols: list) -> None:
    """Replace a foreign key by one with no delete action (evidence must not be rewritten or erased)."""
    existing = _fk_names(table).get(name)
    if existing and not (existing.get("options") or {}).get("ondelete"):
        return
    if existing:
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(name, table, ref_table, cols, ref_cols)


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------------- learning_sessions
    # A fresh database reaches this revision with the table already created from the models (revision 001),
    # which know the columns but not every constraint, so each constraint and index is ensured separately.
    if not _has_table("learning_sessions"):
        op.create_table(
            "learning_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id"), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("last_activity_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("end_reason", sa.String(20), nullable=True),
            sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    if not _has_unique("learning_sessions", "uq_learning_sessions_id_org_user"):
        op.create_unique_constraint("uq_learning_sessions_id_org_user", "learning_sessions", ["id", "org_id", "user_id"])
    for name, expression in (
        ("ck_learning_sessions_time_order", "ended_at IS NULL OR ended_at >= started_at"),
        ("ck_learning_sessions_end_reason", "end_reason IS NULL OR end_reason IN (%s)" % ", ".join(f"'{r}'" for r in END_REASONS)),
        ("ck_learning_sessions_end_pair", "(ended_at IS NULL) = (end_reason IS NULL)"),
    ):
        if not _has_check("learning_sessions", name):
            op.create_check_constraint(name, "learning_sessions", expression)
    session_indexes = _index_names("learning_sessions")
    if "ix_learning_sessions_org_user_started" not in session_indexes:
        op.create_index("ix_learning_sessions_org_user_started", "learning_sessions", ["org_id", "user_id", "started_at"])
    if "ix_learning_sessions_org_course" not in session_indexes:
        op.create_index("ix_learning_sessions_org_course", "learning_sessions", ["org_id", "course_id"])

    # Adaptive sessions become learning sessions with the same id, so events that already point at
    # them keep resolving. Rows already copied (a re-run) are skipped.
    if _has_table("adaptive_sessions"):
        # Of several open adaptive sessions for one learner and course, only the newest stays open.
        bind.execute(sa.text("""
            INSERT INTO learning_sessions (id, org_id, user_id, course_id, started_at, last_activity_at, ended_at, end_reason, context)
            SELECT r.id, r.org_id, r.user_id, r.course_id, r.started_at,
                   COALESCE(r.ended_at, r.started_at),
                   CASE WHEN r.ended_at IS NOT NULL THEN r.ended_at
                        WHEN r.newest_open = 1 THEN NULL
                        ELSE r.started_at END,
                   CASE WHEN r.ended_at IS NOT NULL THEN 'explicit'
                        WHEN r.newest_open = 1 THEN NULL
                        ELSE 'superseded' END,
                   COALESCE(r.metadata, '{}'::jsonb) || jsonb_build_object('source', 'adaptive_session_backfill')
              FROM (SELECT a.*,
                           ROW_NUMBER() OVER (PARTITION BY a.org_id, a.user_id, a.course_id
                                              ORDER BY (a.ended_at IS NULL) DESC, a.started_at DESC) AS newest_open
                      FROM adaptive_sessions a) r
             WHERE NOT EXISTS (SELECT 1 FROM learning_sessions s WHERE s.id = r.id)
        """))

    # One open session per learner per course, guaranteed by the database (concurrent starts cannot create two).
    # Created after the backfill, which leaves at most one open session per learner and course.
    if "uq_learning_sessions_one_open" not in _index_names("learning_sessions"):
        op.create_index(
            "uq_learning_sessions_one_open", "learning_sessions", ["org_id", "user_id", "course_id"],
            unique=True, postgresql_where=sa.text("ended_at IS NULL"),
        )

    # ----------------------------------------------------------------- learning_events
    cols = _columns("learning_events")
    additions = [
        ("assessment_id", sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quizzes.id"), nullable=True)),
        ("question_id", sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quiz_questions.id"), nullable=True)),
        ("competency_id", sa.Column("competency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competencies.id"), nullable=True)),
        ("received_at", sa.Column("received_at", sa.DateTime(), nullable=True)),
        ("idempotency_key", sa.Column("idempotency_key", sa.String(128), nullable=True)),
    ]
    for name, column in additions:
        if name not in cols:
            op.add_column("learning_events", column)

    # Fill the new references for existing events from their payloads, only where the row exists in the same tenant.
    for column, payload_key, table in (
        ("assessment_id", "quiz_id", "quizzes"),
        ("competency_id", "competency_id", "competencies"),
    ):
        bind.execute(sa.text(f"""
            UPDATE learning_events e SET {column} = ref.id
              FROM (SELECT ev.id AS event_id,
                           CASE WHEN ev.payload->>'{payload_key}' ~ '{UUID_RE}' THEN (ev.payload->>'{payload_key}')::uuid END AS ref_id
                      FROM learning_events ev WHERE ev.{column} IS NULL) src
              JOIN {table} ref ON ref.id = src.ref_id
             WHERE e.id = src.event_id AND ref.org_id = e.org_id
        """))
    bind.execute(sa.text(f"""
        UPDATE learning_events e SET question_id = ref.id
          FROM (SELECT ev.id AS event_id,
                       CASE WHEN ev.payload->>'question_id' ~ '{UUID_RE}' THEN (ev.payload->>'question_id')::uuid END AS ref_id
                  FROM learning_events ev WHERE ev.question_id IS NULL) src
          JOIN quiz_questions ref ON ref.id = src.ref_id
          JOIN quizzes qz ON qz.id = ref.quiz_id
         WHERE e.id = src.event_id AND qz.org_id = e.org_id
    """))
    bind.execute(sa.text('UPDATE learning_events SET received_at = "timestamp" WHERE received_at IS NULL'))
    op.alter_column("learning_events", "received_at", nullable=False, server_default=sa.text("now()"))

    # A session an event names must belong to that learner in that tenant; repair any that do not.
    bind.execute(sa.text("""
        UPDATE learning_events e SET session_id = NULL
         WHERE e.session_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM learning_sessions s
                            WHERE s.id = e.session_id AND s.org_id = e.org_id AND s.user_id = e.user_id)
    """))

    fks = _fk_names("learning_events")
    if "learning_events_session_id_fkey" in fks:
        op.drop_constraint("learning_events_session_id_fkey", "learning_events", type_="foreignkey")
    if "fk_learning_events_session" not in _fk_names("learning_events"):
        op.create_foreign_key(
            "fk_learning_events_session", "learning_events", "learning_sessions",
            ["session_id", "org_id", "user_id"], ["id", "org_id", "user_id"],
        )

    _restrict_fk("learning_events", "learning_events_user_id_fkey", ["user_id"], "users", ["id"])
    _restrict_fk("learning_events", "learning_events_org_id_fkey", ["org_id"], "organizations", ["id"])
    _restrict_fk("learning_events", "learning_events_course_id_fkey", ["course_id"], "courses", ["id"])
    _restrict_fk("learning_events", "learning_events_module_id_fkey", ["module_id"], "modules", ["id"])
    _restrict_fk("learning_events", "learning_events_content_id_fkey", ["content_id"], "content_items", ["id"])

    indexes = _index_names("learning_events")
    for name, columns, where in (
        ("ix_learning_events_assessment_id", ["assessment_id"], None),
        ("ix_learning_events_question_id", ["question_id"], None),
        ("ix_learning_events_competency_id", ["competency_id"], None),
        ("ix_learning_events_org_user_time", ["org_id", "user_id", "timestamp"], None),
        ("ix_learning_events_org_session_time", ["org_id", "session_id", "timestamp"], None),
        ("ix_learning_events_org_type_time", ["org_id", "event_type", "timestamp"], None),
    ):
        if name not in indexes:
            op.create_index(name, "learning_events", columns)
    if "uq_learning_events_org_idempotency" not in indexes:
        op.create_index(
            "uq_learning_events_org_idempotency", "learning_events", ["org_id", "idempotency_key"],
            unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )

    # Append-only. Created last: the backfills above are the only UPDATEs this table will ever see.
    bind.execute(sa.text("""
        CREATE OR REPLACE FUNCTION learning_events_are_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'learning_events is append-only: % is not permitted', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
    """))
    bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_events_append_only ON learning_events"))
    bind.execute(sa.text("""
        CREATE TRIGGER trg_learning_events_append_only
            BEFORE UPDATE OR DELETE ON learning_events
            FOR EACH ROW EXECUTE FUNCTION learning_events_are_append_only()
    """))

    # ------------------------------------------------------------------- event_outbox
    if not _has_table("event_outbox"):
        op.create_table(
            "event_outbox",
            sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning_events.id"), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("stream_message_id", sa.String(64), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
        )
    if "ix_event_outbox_pending" not in _index_names("event_outbox"):
        op.create_index(
            "ix_event_outbox_pending", "event_outbox", ["next_attempt_at"],
            postgresql_where=sa.text("published_at IS NULL"),
        )

    # ----------------------------------------------- per-answer evidence columns
    if "difficulty" not in _columns("quiz_questions"):
        op.add_column("quiz_questions", sa.Column("difficulty", sa.Float(), nullable=True))
    if not _has_check("quiz_questions", "ck_quiz_questions_difficulty"):
        op.create_check_constraint("ck_quiz_questions_difficulty", "quiz_questions", "difficulty IS NULL OR (difficulty >= 0 AND difficulty <= 1)")

    response_cols = _columns("question_responses")
    if "response_time_ms" not in response_cols:
        op.add_column("question_responses", sa.Column("response_time_ms", sa.Integer(), nullable=True))
    if "response_time_source" not in response_cols:
        op.add_column("question_responses", sa.Column("response_time_source", sa.String(20), nullable=True))
    if "error_type" not in response_cols:
        op.add_column("question_responses", sa.Column("error_type", sa.String(40), nullable=True))
    if not _has_check("question_responses", "ck_question_responses_time"):
        op.create_check_constraint("ck_question_responses_time", "question_responses", "response_time_ms IS NULL OR response_time_ms >= 0")
    if not _has_check("question_responses", "ck_question_responses_error_type"):
        op.create_check_constraint(
            "ck_question_responses_error_type", "question_responses",
            "error_type IS NULL OR error_type IN (%s)" % ", ".join(f"'{t}'" for t in ERROR_TYPES),
        )


def downgrade() -> None:
    bind = op.get_bind()

    for name in ("ck_question_responses_error_type", "ck_question_responses_time"):
        if _has_check("question_responses", name):
            op.drop_constraint(name, "question_responses", type_="check")
    for column in ("error_type", "response_time_source", "response_time_ms"):
        if column in _columns("question_responses"):
            op.drop_column("question_responses", column)
    if _has_check("quiz_questions", "ck_quiz_questions_difficulty"):
        op.drop_constraint("ck_quiz_questions_difficulty", "quiz_questions", type_="check")
    if "difficulty" in _columns("quiz_questions"):
        op.drop_column("quiz_questions", "difficulty")

    if _has_table("event_outbox"):
        op.drop_table("event_outbox")

    bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_learning_events_append_only ON learning_events"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS learning_events_are_append_only()"))

    # Events keep their session ids only where an adaptive session with that id exists again.
    if "fk_learning_events_session" in _fk_names("learning_events"):
        op.drop_constraint("fk_learning_events_session", "learning_events", type_="foreignkey")
    if _has_table("adaptive_sessions"):
        bind.execute(sa.text("""
            UPDATE learning_events e SET session_id = NULL
             WHERE e.session_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM adaptive_sessions a WHERE a.id = e.session_id)
        """))
        if "learning_events_session_id_fkey" not in _fk_names("learning_events"):
            op.create_foreign_key(
                "learning_events_session_id_fkey", "learning_events", "adaptive_sessions",
                ["session_id"], ["id"], ondelete="SET NULL",
            )

    for name, ref_table, cols, ondelete in (
        ("learning_events_user_id_fkey", "users", ["user_id"], "CASCADE"),
        ("learning_events_org_id_fkey", "organizations", ["org_id"], "CASCADE"),
        ("learning_events_course_id_fkey", "courses", ["course_id"], "SET NULL"),
        ("learning_events_module_id_fkey", "modules", ["module_id"], "SET NULL"),
        ("learning_events_content_id_fkey", "content_items", ["content_id"], "SET NULL"),
    ):
        if name in _fk_names("learning_events"):
            op.drop_constraint(name, "learning_events", type_="foreignkey")
        op.create_foreign_key(name, "learning_events", ref_table, cols, ["id"], ondelete=ondelete)

    for name in (
        "uq_learning_events_org_idempotency", "ix_learning_events_org_type_time", "ix_learning_events_org_session_time",
        "ix_learning_events_org_user_time", "ix_learning_events_competency_id", "ix_learning_events_question_id",
        "ix_learning_events_assessment_id",
    ):
        if name in _index_names("learning_events"):
            op.drop_index(name, table_name="learning_events")
    for column in ("idempotency_key", "received_at", "competency_id", "question_id", "assessment_id"):
        if column in _columns("learning_events"):
            op.drop_column("learning_events", column)

    if _has_table("learning_sessions"):
        op.drop_table("learning_sessions")
