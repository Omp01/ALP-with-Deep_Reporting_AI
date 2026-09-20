"""Phase 3 content ingestion: job stages, reviewable question candidates, content hash

Revision ID: 005_content_ingestion
Revises: 004_learning_experience
Create Date: 2026-09-20 00:00:00.000000

1. `ingestion_jobs` gains what a staged, resumable pipeline needs: the source
   (`upload` or `youtube`), its URL, a link to the content item being produced, the
   current stage, a per-stage log, a machine-readable error code, an attempt count and
   timestamps. `storage_path` becomes nullable (a YouTube job stores no file). Statuses
   are constrained.

2. `question_candidates` holds generated (or hand-written) questions while an
   administrator reviews them. Nothing here is visible to learners; on publish the
   approved candidates become a real quiz.

3. `content_items.content_hash` (SHA-256 of the file or transcript) lets the pipeline
   skip re-analysing unchanged content, which avoids repeat AI calls.

4. `content_chunks.embedding_model` records which model produced an embedding, so a
   vector is never compared with one from a different model.

Idempotent for the same reason as 003 and 004.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_content_ingestion"
down_revision: Union[str, None] = "004_learning_experience"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_STATUSES = ("pending", "processing", "ready_for_review", "needs_attention", "failed", "completed")
CANDIDATE_STATUSES = ("pending", "approved", "rejected", "published")


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> dict:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _has_check(table: str, name: str) -> bool:
    return any(c["name"] == name for c in _inspector().get_check_constraints(table))


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------- ingestion_jobs
    cols = _columns("ingestion_jobs")
    additions = [
        ("source_type", sa.Column("source_type", sa.String(20), nullable=False, server_default="upload")),
        ("source_url", sa.Column("source_url", sa.String(2048), nullable=True)),
        (
            "content_item_id",
            sa.Column(
                "content_item_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("content_items.id", ondelete="SET NULL"),
                nullable=True,
            ),
        ),
        ("stage", sa.Column("stage", sa.String(40), nullable=True)),
        ("stages", sa.Column("stages", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb"))),
        ("error_code", sa.Column("error_code", sa.String(60), nullable=True)),
        ("attempts", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")),
        ("started_at", sa.Column("started_at", sa.DateTime(), nullable=True)),
        ("updated_at", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()"))),
    ]
    for name, column in additions:
        if name not in cols:
            op.add_column("ingestion_jobs", column)
    if "content_item_id" not in cols:
        op.create_index("ix_ingestion_jobs_content_item_id", "ingestion_jobs", ["content_item_id"])
    if not cols["storage_path"]["nullable"]:
        op.alter_column("ingestion_jobs", "storage_path", existing_type=sa.String(1024), nullable=True)

    # Older statuses: pending, processing, completed, failed. Map into the new set.
    if not _has_check("ingestion_jobs", "ck_ingestion_jobs_status"):
        allowed = ", ".join(f"'{s}'" for s in JOB_STATUSES)
        bind.execute(sa.text(f"UPDATE ingestion_jobs SET status = 'failed' WHERE status NOT IN ({allowed})"))
        op.create_check_constraint("ck_ingestion_jobs_status", "ingestion_jobs", f"status IN ({allowed})")

    # --------------------------------------------------------- question_candidates
    if not _inspector().has_table("question_candidates"):
        op.create_table(
            "question_candidates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("content_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("question_type", sa.String(30), nullable=False, server_default="multiple_choice"),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("competency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True),
            sa.Column("competency_name", sa.String(255), nullable=True),
            sa.Column("difficulty", sa.Float(), nullable=False, server_default="0.5"),
            sa.Column("source_quote", sa.Text(), nullable=True),
            sa.Column("chunk_index", sa.Integer(), nullable=True),
            sa.Column("origin", sa.String(20), nullable=False, server_default="generated"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("published_question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quiz_questions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("difficulty >= 0 AND difficulty <= 1", name="ck_question_candidates_difficulty"),
            sa.CheckConstraint(
                "status IN (" + ", ".join(f"'{s}'" for s in CANDIDATE_STATUSES) + ")",
                name="ck_question_candidates_status",
            ),
        )
        op.create_index("ix_question_candidates_org_id", "question_candidates", ["org_id"])
        op.create_index("ix_question_candidates_content_item_id", "question_candidates", ["content_item_id"])
        op.create_index("ix_question_candidates_status", "question_candidates", ["status"])

    # -------------------------------------------------- content_items / chunks
    if "content_hash" not in _columns("content_items"):
        op.add_column("content_items", sa.Column("content_hash", sa.String(64), nullable=True))
        op.create_index("ix_content_items_content_hash", "content_items", ["content_hash"])
    if "embedding_model" not in _columns("content_chunks"):
        op.add_column("content_chunks", sa.Column("embedding_model", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("content_chunks", "embedding_model")
    op.drop_index("ix_content_items_content_hash", table_name="content_items")
    op.drop_column("content_items", "content_hash")
    op.drop_table("question_candidates")
    op.drop_constraint("ck_ingestion_jobs_status", "ingestion_jobs", type_="check")
    op.execute("UPDATE ingestion_jobs SET storage_path = '' WHERE storage_path IS NULL")
    op.alter_column("ingestion_jobs", "storage_path", existing_type=sa.String(1024), nullable=False)
    op.drop_index("ix_ingestion_jobs_content_item_id", table_name="ingestion_jobs")
    for name in ("updated_at", "started_at", "attempts", "error_code", "stages", "stage", "content_item_id", "source_url", "source_type"):
        op.drop_column("ingestion_jobs", name)
