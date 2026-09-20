"""
The schema that ships: verified by running the real Alembic migrations.

These tests prove the database itself enforces the foundation rules, independent of
any API code — so a bug or a raw-SQL script cannot bypass them.
"""

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError

from app.models import CompetencyPrerequisite, ContentItem
from tests.foundation.conftest import make_competency, make_org, make_user

pytestmark = pytest.mark.integration


def test_foundation_tables_exist(db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert {"roles", "user_roles", "competency_prerequisites", "competencies", "content_items"} <= tables


def test_role_catalogue_is_seeded_by_the_migration(db_session):
    rows = db_session.execute(text("SELECT code, rank FROM roles ORDER BY rank")).all()
    assert [r.code for r in rows] == ["learner", "manager", "ld_admin", "org_admin", "super_admin"]


def test_competency_has_spec_fields(db_session):
    columns = {c["name"] for c in inspect(db_session.bind).get_columns("competencies")}
    assert {"id", "name", "description", "domain", "difficulty", "metadata", "org_id"} <= columns


def test_content_item_has_source_and_analysis_fields(db_session):
    columns = {c["name"] for c in inspect(db_session.bind).get_columns("content_items")}
    assert {"source_type", "source_url", "analysis", "status"} <= columns


def test_course_rating_and_duration_are_nullable_with_no_default(db_session):
    columns = {c["name"]: c for c in inspect(db_session.bind).get_columns("courses")}
    for name in ("rating", "duration_minutes"):
        assert columns[name]["nullable"] is True
        assert columns[name]["default"] is None, f"{name} must not carry a fabricated default"


def test_edge_between_two_competencies_of_one_tenant_is_accepted(db_session):
    org = make_org(db_session)
    a, b = make_competency(db_session, org), make_competency(db_session, org)
    db_session.add(CompetencyPrerequisite(competency_id=a.id, prerequisite_id=b.id, org_id=org.id))
    db_session.flush()  # no error


def test_database_rejects_self_prerequisite(db_session):
    org = make_org(db_session)
    a = make_competency(db_session, org)
    db_session.add(CompetencyPrerequisite(competency_id=a.id, prerequisite_id=a.id, org_id=org.id))
    with pytest.raises(IntegrityError, match="ck_comp_prereq_not_self"):
        db_session.flush()


def test_database_rejects_cross_tenant_prerequisite(db_session):
    """The composite (id, org_id) foreign keys make a cross-tenant edge impossible."""
    org_a, org_b = make_org(db_session), make_org(db_session)
    in_a, in_b = make_competency(db_session, org_a), make_competency(db_session, org_b)
    # Claim the edge belongs to tenant A while pointing its prerequisite at tenant B's competency.
    db_session.add(CompetencyPrerequisite(competency_id=in_a.id, prerequisite_id=in_b.id, org_id=org_a.id))
    with pytest.raises(IntegrityError, match="fk_comp_prereq_prerequisite_org"):
        db_session.flush()


def test_database_rejects_edge_labelled_with_wrong_tenant(db_session):
    org_a, org_b = make_org(db_session), make_org(db_session)
    a1, a2 = make_competency(db_session, org_a), make_competency(db_session, org_a)
    db_session.add(CompetencyPrerequisite(competency_id=a1.id, prerequisite_id=a2.id, org_id=org_b.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_min_mastery_out_of_range(db_session):
    org = make_org(db_session)
    a, b = make_competency(db_session, org), make_competency(db_session, org)
    db_session.add(CompetencyPrerequisite(competency_id=a.id, prerequisite_id=b.id, org_id=org.id, min_mastery=1.5))
    with pytest.raises(IntegrityError, match="ck_comp_prereq_min_mastery"):
        db_session.flush()


def test_database_rejects_competency_difficulty_out_of_range(db_session):
    org = make_org(db_session)
    with pytest.raises(IntegrityError, match="ck_competencies_difficulty_range"):
        make_competency(db_session, org, difficulty=1.4)  # the helper flushes


def test_database_rejects_unknown_content_status(db_session):
    org = make_org(db_session)
    from tests.foundation.conftest import make_course

    owner = make_user(db_session, org, ["ld_admin"])
    course = make_course(db_session, org, owner, content_seconds=[])
    from app.models import Module

    module = db_session.query(Module).filter_by(course_id=course.id).one()
    db_session.add(ContentItem(
        id=uuid.uuid4(), org_id=org.id, module_id=module.id, title="x", content_type="VIDEO", status="bogus",
    ))
    with pytest.raises(IntegrityError, match="ck_content_items_status"):
        db_session.flush()


def test_deleting_a_competency_removes_its_edges(db_session):
    org = make_org(db_session)
    a, b = make_competency(db_session, org), make_competency(db_session, org)
    db_session.add(CompetencyPrerequisite(competency_id=a.id, prerequisite_id=b.id, org_id=org.id))
    db_session.flush()
    db_session.delete(b)
    db_session.flush()
    remaining = db_session.query(CompetencyPrerequisite).filter_by(competency_id=a.id).count()
    assert remaining == 0
