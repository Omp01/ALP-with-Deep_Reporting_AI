"""Login check-ins: an AI-written quiz on course material, a self-report, and their scored report

Revision ID: 009_checkins
Revises: 008_reports
Create Date: 2026-09-24 00:00:00.000000

`checkins` stores each check-in with the verified questions (and the passages they came from), the learner's answers, the
scores and the report. Idempotent, like 003 to 008.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_checkins"
down_revision: Union[str, None] = "008_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "checkins" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "checkins",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("learner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="generating"),
            sa.Column("quiz", postgresql.JSONB(), nullable=False, server_default="[]"),
            sa.Column("psychometric", postgresql.JSONB(), nullable=False, server_default="[]"),
            sa.Column("answers", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("scores", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("report", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("error_code", sa.String(40), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("ready_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("checkins")}
    if "ix_checkins_org_id" not in indexes:
        op.create_index("ix_checkins_org_id", "checkins", ["org_id"])
    if "ix_checkins_learner" not in indexes:
        op.create_index("ix_checkins_learner", "checkins", ["org_id", "learner_id", "created_at"])


def downgrade() -> None:
    if "checkins" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("checkins")
