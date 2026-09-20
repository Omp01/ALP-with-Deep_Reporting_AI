"""Phase 7 reporting AI: grounded reports with their evidence packages

Revision ID: 008_reports
Revises: 007_competency_engine
Create Date: 2026-09-23 00:00:00.000000

`reports` stores each generated report with the evidence package it was built from, the claims that passed citation
validation and the ones that did not. Idempotent, like 003 to 007.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_reports"
down_revision: Union[str, None] = "007_competency_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "reports" not in insp.get_table_names():
        op.create_table(
            "reports",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("audience", sa.String(20), nullable=False),
            sa.Column("scope_type", sa.String(20), nullable=False),
            sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("period_start", sa.DateTime(), nullable=False),
            sa.Column("period_end", sa.DateTime(), nullable=False),
            sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("generated_by", sa.String(20), nullable=False),
            sa.Column("ai_status", sa.String(20), nullable=False),
            sa.Column("ai_note", sa.Text(), nullable=True),
            sa.Column("model", sa.String(100), nullable=True),
            sa.Column("prompt_version", sa.String(30), nullable=True),
            sa.Column("package_hash", sa.String(64), nullable=False),
            sa.Column("package", postgresql.JSONB(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("claims", postgresql.JSONB(), nullable=False),
            sa.Column("rejected_claims", postgresql.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("reports")}
    if "ix_reports_org_id" not in indexes:
        op.create_index("ix_reports_org_id", "reports", ["org_id"])
    if "ix_reports_created_at" not in indexes:
        op.create_index("ix_reports_created_at", "reports", ["created_at"])
    if "ix_reports_scope" not in indexes:
        op.create_index("ix_reports_scope", "reports", ["org_id", "audience", "scope_id", "created_at"])


def downgrade() -> None:
    if "reports" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("reports")
