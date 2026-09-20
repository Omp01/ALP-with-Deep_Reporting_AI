"""Phase 1 foundation: roles, skill graph, content model, honest course fields

Revision ID: 003_foundation
Revises: 002_lms_entities
Create Date: 2026-09-19 00:00:00.000000

What this migration does
------------------------
1. `roles` + `user_roles`  — real role tables; back-fills one assignment per
   existing user from the legacy `users.role` column.
2. `competencies`          — adds `domain`, `difficulty`, `metadata`; adds the
   (id, org_id) unique key that lets other tables carry tenant-safe foreign keys.
3. `competency_prerequisites` — the skill graph, with composite foreign keys that
   make the DATABASE reject cross-tenant edges, plus self-loop and range checks.
4. `content_items`         — adds `source_type`, `source_url`, `analysis` and a
   status check constraint (draft/processing/review/published/failed).
5. `courses`               — `rating` and `duration_minutes` become nullable and
   existing values are cleared. Revision 002 gave every course a rating of 4.8 and
   a duration of 120 by default; there is no ratings source, so those numbers were
   fabricated. Duration is now computed from content at read time.

Idempotency
-----------
Revision 001 runs `Base.metadata.create_all()` from the *current* models, so on a
brand-new database every object below already exists by the time this revision
runs. Each step therefore checks before creating, and the data steps (role
catalogue, user_roles back-fill) always run. On an existing database at revision
002 the same code performs the real upgrade.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_foundation"
down_revision: Union[str, None] = "002_lms_entities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTENT_STATUSES = ("draft", "processing", "review", "published", "failed")

# Frozen copy of the role catalogue (do not import app code into a migration).
ROLE_CATALOGUE = [
    ("learner", "Learner", "Consumes learning content and sees their own learning data.", 10),
    ("manager", "Manager", "Sees learning data and skill gaps for the teams they manage.", 20),
    ("ld_admin", "L&D Admin", "Owns learning programmes: content, courses, competencies and assessments.", 30),
    ("org_admin", "Organization Admin", "Administers the organisation: users, roles and organisation-level reporting.", 40),
    ("super_admin", "Super Admin", "Platform-level administration across organisations.", 50),
]

# Bloom's taxonomy level -> default competency difficulty (0..1).
BLOOM_DIFFICULTY = {
    "remember": 0.10,
    "understand": 0.25,
    "apply": 0.50,
    "analyze": 0.65,
    "evaluate": 0.80,
    "create": 0.90,
}


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _columns(table: str) -> dict:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _has_unique(table: str, name: str) -> bool:
    return any(u["name"] == name for u in _inspector().get_unique_constraints(table))


def _has_check(table: str, name: str) -> bool:
    return any(c["name"] == name for c in _inspector().get_check_constraints(table))


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------ roles
    if not _has_table("roles"):
        op.create_table(
            "roles",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_roles_code", "roles", ["code"], unique=True)

    for code, name, description, rank in ROLE_CATALOGUE:
        bind.execute(
            sa.text(
                "INSERT INTO roles (id, code, name, description, rank, is_system, created_at) "
                "VALUES (gen_random_uuid(), :code, :name, :description, :rank, true, now()) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "name": name, "description": description, "rank": rank},
        )

    if not _has_table("user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_user_roles_org_id", "user_roles", ["org_id"])

    # One assignment per existing user, translating the legacy spellings.
    bind.execute(
        sa.text(
            "INSERT INTO user_roles (user_id, role_id, org_id, assigned_at) "
            "SELECT u.id, r.id, u.org_id, now() FROM users u "
            "JOIN roles r ON r.code = CASE u.role "
            "  WHEN 'instructor' THEN 'ld_admin' "
            "  WHEN 'system_admin' THEN 'super_admin' "
            "  ELSE u.role END "
            "ON CONFLICT DO NOTHING"
        )
    )

    # ---------------------------------------------------------- competencies
    comp_cols = _columns("competencies")
    difficulty_is_new = "difficulty" not in comp_cols
    if "domain" not in comp_cols:
        op.add_column("competencies", sa.Column("domain", sa.String(100), nullable=True))
        op.create_index("ix_competencies_domain", "competencies", ["domain"])
    if difficulty_is_new:
        op.add_column("competencies", sa.Column("difficulty", sa.Float(), nullable=False, server_default="0.5"))
    if "metadata" not in comp_cols:
        op.add_column(
            "competencies",
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
    if not _has_unique("competencies", "uq_competencies_id_org"):
        op.create_unique_constraint("uq_competencies_id_org", "competencies", ["id", "org_id"])
    if not _has_check("competencies", "ck_competencies_difficulty_range"):
        op.create_check_constraint("ck_competencies_difficulty_range", "competencies", "difficulty >= 0 AND difficulty <= 1")

    # Derive from data that already exists rather than inventing values:
    #  - domain: the code prefix ("python.oop" -> "python"), only where a dot exists
    #  - difficulty: Bloom's taxonomy level, only for rows just given a difficulty column
    bind.execute(
        sa.text(
            "UPDATE competencies SET domain = split_part(code, '.', 1) "
            "WHERE domain IS NULL AND position('.' in code) > 0"
        )
    )
    if difficulty_is_new:
        for level, value in BLOOM_DIFFICULTY.items():
            bind.execute(
                sa.text("UPDATE competencies SET difficulty = :v WHERE taxonomy_level = :l"),
                {"v": value, "l": level},
            )

    # ------------------------------------------------- competency_prerequisites
    if not _has_table("competency_prerequisites"):
        op.create_table(
            "competency_prerequisites",
            sa.Column("competency_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("prerequisite_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("min_mastery", sa.Float(), nullable=False, server_default="0.6"),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("competency_id", "prerequisite_id"),
            sa.ForeignKeyConstraint(
                ["competency_id", "org_id"], ["competencies.id", "competencies.org_id"],
                ondelete="CASCADE", name="fk_comp_prereq_competency_org",
            ),
            sa.ForeignKeyConstraint(
                ["prerequisite_id", "org_id"], ["competencies.id", "competencies.org_id"],
                ondelete="CASCADE", name="fk_comp_prereq_prerequisite_org",
            ),
            sa.CheckConstraint("competency_id <> prerequisite_id", name="ck_comp_prereq_not_self"),
            sa.CheckConstraint("min_mastery >= 0 AND min_mastery <= 1", name="ck_comp_prereq_min_mastery"),
        )
        op.create_index("ix_competency_prerequisites_org_id", "competency_prerequisites", ["org_id"])
        op.create_index("ix_competency_prerequisites_prerequisite_id", "competency_prerequisites", ["prerequisite_id"])

    # ---------------------------------------------------------- content_items
    content_cols = _columns("content_items")
    source_type_is_new = "source_type" not in content_cols
    if source_type_is_new:
        op.add_column("content_items", sa.Column("source_type", sa.String(30), nullable=False, server_default="authored"))
    if "source_url" not in content_cols:
        op.add_column("content_items", sa.Column("source_url", sa.String(2048), nullable=True))
    if "analysis" not in content_cols:
        op.add_column("content_items", sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    if source_type_is_new:
        # Ingestion stores uploads under "<org_id>/<job_id>_<filename>" in content_url.
        bind.execute(
            sa.text(
                "UPDATE content_items SET source_type = 'upload' "
                "WHERE content_url LIKE org_id::text || '/%'"
            )
        )
    if not _has_check("content_items", "ck_content_items_status"):
        allowed = ", ".join(f"'{s}'" for s in CONTENT_STATUSES)
        op.create_check_constraint("ck_content_items_status", "content_items", f"status IN ({allowed})")

    # ---------------------------------------------------------------- courses
    course_cols = _columns("courses")
    if not course_cols["rating"]["nullable"]:
        op.alter_column("courses", "rating", existing_type=sa.Float(), nullable=True, server_default=None)
        bind.execute(sa.text("UPDATE courses SET rating = NULL"))
    if not course_cols["duration_minutes"]["nullable"]:
        op.alter_column("courses", "duration_minutes", existing_type=sa.Integer(), nullable=True, server_default=None)
        bind.execute(sa.text("UPDATE courses SET duration_minutes = NULL"))


def downgrade() -> None:
    bind = op.get_bind()

    # courses: the previous schema required NOT NULL with defaults, so NULLs are
    # refilled with those defaults. This is lossy by nature (the values were never real).
    bind.execute(sa.text("UPDATE courses SET rating = 4.8 WHERE rating IS NULL"))
    bind.execute(sa.text("UPDATE courses SET duration_minutes = 120 WHERE duration_minutes IS NULL"))
    op.alter_column("courses", "rating", existing_type=sa.Float(), nullable=False, server_default="4.8")
    op.alter_column("courses", "duration_minutes", existing_type=sa.Integer(), nullable=False, server_default="120")

    op.drop_constraint("ck_content_items_status", "content_items", type_="check")
    op.drop_column("content_items", "analysis")
    op.drop_column("content_items", "source_url")
    op.drop_column("content_items", "source_type")

    op.drop_table("competency_prerequisites")

    op.drop_constraint("ck_competencies_difficulty_range", "competencies", type_="check")
    op.drop_constraint("uq_competencies_id_org", "competencies", type_="unique")
    op.drop_column("competencies", "metadata")
    op.drop_column("competencies", "difficulty")
    op.drop_index("ix_competencies_domain", table_name="competencies")
    op.drop_column("competencies", "domain")

    op.drop_table("user_roles")
    op.drop_table("roles")
