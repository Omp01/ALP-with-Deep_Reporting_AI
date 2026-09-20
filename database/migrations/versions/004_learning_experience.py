"""Phase 2 learning experience: explicit lesson links, tenant-owned progress, resume position

Revision ID: 004_learning_experience
Revises: 003_foundation
Create Date: 2026-09-20 00:00:00.000000

1. `quizzes.content_item_id` and `assignments.content_item_id`
   A quiz or assignment is presented in the course outline as a content item. That
   link used to be a JSON hint in `content_items.metadata` and, in the quiz
   submit handler, a guess by title substring. It is now a real, unique foreign
   key, so "which lesson does this quiz complete?" has exactly one answer.
   Quizzes are back-filled from the existing `metadata.quiz_id` hint.

2. `content_progress.org_id`
   Progress records had no tenant column (every other learner-owned table has
   one). Back-filled from the owning user; then made NOT NULL.

3. `content_progress.position_seconds`
   Where the learner stopped in a video, so playback can resume.

4. `content_items.course_id` back-filled from the module where ingestion left it NULL.

5. Enrollments are reconciled against lesson records. Progress is now derived from
   `content_progress`; stored percentages and "completed" statuses that no lesson
   records support (earlier demo scripts wrote them directly) are corrected.

Idempotent for the same reason as 003: on a new database revision 001's
`create_all()` has already created everything.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_learning_experience"
down_revision: Union[str, None] = "003_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> dict:
    return {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return any(i["name"] == name for i in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. explicit lesson links -------------------------------------------
    for table in ("quizzes", "assignments"):
        if "content_item_id" not in _columns(table):
            op.add_column(
                table,
                sa.Column(
                    "content_item_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("content_items.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        index = f"uq_{table}_content_item"
        if not _has_index(table, index):
            # Partial unique index: at most one quiz / assignment per lesson item.
            op.create_index(
                index, table, ["content_item_id"], unique=True,
                postgresql_where=sa.text("content_item_id IS NOT NULL"),
            )

    bind.execute(
        sa.text(
            "UPDATE quizzes q SET content_item_id = ci.id "
            "FROM content_items ci "
            "WHERE q.content_item_id IS NULL AND ci.org_id = q.org_id "
            "AND ci.content_type = 'QUIZ' AND ci.metadata ->> 'quiz_id' = q.id::text"
        )
    )

    # Ingestion used to create content items without course_id, which every
    # course-level count and progress query relies on.
    bind.execute(
        sa.text(
            "UPDATE content_items ci SET course_id = m.course_id "
            "FROM modules m WHERE ci.module_id = m.id AND ci.course_id IS NULL"
        )
    )

    # --- 2 & 3. content_progress ---------------------------------------------
    progress_cols = _columns("content_progress")
    if "position_seconds" not in progress_cols:
        op.add_column(
            "content_progress",
            sa.Column("position_seconds", sa.Integer(), nullable=False, server_default="0"),
        )
    if "org_id" not in progress_cols:
        op.add_column(
            "content_progress",
            sa.Column(
                "org_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        bind.execute(
            sa.text(
                "UPDATE content_progress cp SET org_id = u.org_id "
                "FROM users u WHERE cp.user_id = u.id"
            )
        )
        op.alter_column("content_progress", "org_id", nullable=False)
        op.create_index("ix_content_progress_org_id", "content_progress", ["org_id"])
    # One progress row per learner per lesson item. Existing duplicates (the demo seed
    # created some) are collapsed first, keeping the most advanced row: completed beats
    # in-progress, then higher percent, then most recent.
    if not _has_index("content_progress", "uq_content_progress_user_item"):
        bind.execute(
            sa.text(
                "DELETE FROM content_progress WHERE id IN ("
                "  SELECT id FROM ("
                "    SELECT id, ROW_NUMBER() OVER ("
                "      PARTITION BY user_id, content_item_id "
                "      ORDER BY (status = 'completed') DESC, progress_percent DESC, last_accessed_at DESC"
                "    ) AS rn FROM content_progress"
                "  ) ranked WHERE rn > 1)"
            )
        )
        op.create_index(
            "uq_content_progress_user_item", "content_progress", ["user_id", "content_item_id"], unique=True
        )

    # --- 5. reconcile enrollments with what the lesson records actually say -------------
    bind.execute(
        sa.text(
            "UPDATE enrollments e SET "
            "  progress_pct = COALESCE(ROUND((100.0 * x.done / NULLIF(x.total, 0))::numeric, 1), 0), "
            "  status = CASE WHEN x.total > 0 AND x.done >= x.total THEN 'completed' "
            "                WHEN e.status = 'completed' THEN 'active' ELSE e.status END, "
            "  completed_at = CASE WHEN x.total > 0 AND x.done >= x.total THEN COALESCE(e.completed_at, now()) "
            "                      ELSE NULL END "
            "FROM ("
            "  SELECT e2.id, COUNT(ci.id) AS total, COUNT(cp.id) FILTER (WHERE cp.status = 'completed') AS done "
            "  FROM enrollments e2 "
            "  JOIN content_items ci ON ci.course_id = e2.course_id AND ci.status = 'published' "
            "  LEFT JOIN content_progress cp ON cp.content_item_id = ci.id AND cp.user_id = e2.user_id "
            "  GROUP BY e2.id"
            ") x "
            "WHERE x.id = e.id AND e.status IN ('active', 'completed')"
        )
    )


def downgrade() -> None:
    op.drop_index("uq_content_progress_user_item", table_name="content_progress")
    op.drop_index("ix_content_progress_org_id", table_name="content_progress")
    op.drop_column("content_progress", "org_id")
    op.drop_column("content_progress", "position_seconds")
    for table in ("assignments", "quizzes"):
        op.drop_index(f"uq_{table}_content_item", table_name=table)
        op.drop_column(table, "content_item_id")
