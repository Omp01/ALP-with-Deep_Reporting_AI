"""
Migration 007 (competency engine) on a database that already holds data.

Walks a scratch database back to revision 006, inserts what a live installation has (mastery figures written by the earlier
engine, including duplicates and out-of-range values), upgrades, and checks what happened to it: the old figures are kept but
marked as unverified, the new tables exist and are append-only, and running the migration again changes nothing.
"""

import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tests.foundation.conftest import (
    REPO_ROOT, TEST_DB_NAME, _admin_connection, _dev_sync_url, make_competency, make_org, make_user,
)

pytestmark = pytest.mark.integration

MIG_DB = f"{TEST_DB_NAME}_mig007"
MIG_URL = _dev_sync_url.set(database=MIG_DB).render_as_string(hide_password=False)
PREVIOUS = "006_learning_events_sessions"


def alembic(*args):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "database/alembic.ini", *args],
        cwd=REPO_ROOT, env={**os.environ, "DATABASE_URL_SYNC": MIG_URL}, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"


def drop_database():
    conn = _admin_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (MIG_DB,))
        cur.execute(f'DROP DATABASE IF EXISTS "{MIG_DB}"')
    conn.close()


def row(engine, sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).mappings().first()


def scalar_set(engine, sql, **params):
    with engine.connect() as c:
        return {r[0] for r in c.execute(text(sql), params)}


@pytest.fixture(scope="module")
def legacy():
    drop_database()
    conn = _admin_connection()
    with conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{MIG_DB}"')
    conn.close()

    alembic("upgrade", "head")
    alembic("downgrade", PREVIOUS)                        # the shape a live installation has before this phase

    engine = create_engine(MIG_URL)
    assert "evidence_records" not in scalar_set(engine, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")

    db = sessionmaker(bind=engine, expire_on_commit=False)()
    org = make_org(db)
    learner_a, learner_b = make_user(db, org, ["learner"]), make_user(db, org, ["learner"])
    comp_one, comp_two, comp_three = (make_competency(db, org, f"m.{i}") for i in range(3))
    now = datetime.utcnow()

    def state(user, comp, mastery, confidence, points, updated):
        sid = uuid.uuid4()
        db.execute(text("INSERT INTO learner_competencies (id, org_id, user_id, competency_id, mastery_score, confidence_score, data_points_count, status, updated_at) "
                        "VALUES (:i, :o, :u, :c, :m, :cf, :p, 'competent', :t)"),
                   {"i": sid, "o": org.id, "u": user.id, "c": comp.id, "m": mastery, "cf": confidence, "p": points, "t": updated})
        return sid

    ids = dict(
        plain=state(learner_a, comp_one, 0.92, 0.8, 7, now),
        old_duplicate=state(learner_a, comp_two, 0.10, 0.2, 1, now - timedelta(days=5)),
        new_duplicate=state(learner_a, comp_two, 0.55, 0.5, 4, now - timedelta(days=1)),
        out_of_range=state(learner_b, comp_three, 1.4, -0.2, 2, now),
    )
    db.commit()
    db.close()
    yield dict(engine=engine, org=org.id, learner_a=learner_a.id, learner_b=learner_b.id, comp_one=comp_one.id, comp_two=comp_two.id,
               comp_three=comp_three.id, **ids)
    engine.dispose()
    drop_database()


def test_upgrade_keeps_the_old_figures_but_marks_them_unverified(legacy):
    alembic("upgrade", "head")
    e = legacy["engine"]
    rows = {r["id"]: r for r in e.connect().execute(text("SELECT * FROM learner_competencies")).mappings()}
    assert {r["basis"] for r in rows.values()} == {"legacy_unverified"}
    assert rows[legacy["plain"]]["mastery_score"] == pytest.approx(0.92)                  # kept, not deleted: it is only never shown as mastery
    assert (rows[legacy["plain"]]["trend"], rows[legacy["plain"]]["effective_evidence"], rows[legacy["plain"]]["error_distribution"]) == ("insufficient_data", 0.0, {})


def test_duplicates_are_resolved_to_the_newest_and_values_are_brought_into_range(legacy):
    e = legacy["engine"]
    same_key = row(e, "SELECT count(*) AS n FROM learner_competencies WHERE user_id = :u AND competency_id = :c", u=legacy["learner_a"], c=legacy["comp_two"])
    assert same_key["n"] == 1
    kept = row(e, "SELECT mastery_score FROM learner_competencies WHERE user_id = :u AND competency_id = :c", u=legacy["learner_a"], c=legacy["comp_two"])
    assert kept["mastery_score"] == pytest.approx(0.55)
    clamped = row(e, "SELECT mastery_score, confidence_score FROM learner_competencies WHERE id = :i", i=legacy["out_of_range"])
    assert (clamped["mastery_score"], clamped["confidence_score"]) == (1.0, 0.0)


def test_the_database_now_refuses_what_the_engine_must_never_do(legacy):
    e = legacy["engine"]
    with e.connect() as c:
        with pytest.raises(Exception):     # a second state for the same learner and competency
            c.execute(text("INSERT INTO learner_competencies (id, org_id, user_id, competency_id, mastery_score, confidence_score, data_points_count, status, updated_at) "
                           "VALUES (:i, :o, :u, :c, 0.5, 0.5, 1, 'x', now())"), {"i": uuid.uuid4(), "o": legacy["org"], "u": legacy["learner_a"], "c": legacy["comp_one"]})
        c.rollback()
        with pytest.raises(Exception):     # mastery outside 0..1
            c.execute(text("UPDATE learner_competencies SET mastery_score = 1.5 WHERE id = :i"), {"i": legacy["plain"]})
        c.rollback()


def test_evidence_and_audit_tables_exist_and_are_append_only(legacy):
    e = legacy["engine"]
    tables = scalar_set(e, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    assert {"evidence_records", "competency_state_updates", "grading_results"} <= tables
    evidence_id = uuid.uuid4()
    with e.begin() as c:
        c.execute(text("INSERT INTO evidence_records (id, org_id, user_id, competency_id, source_type, signal, confidence, occurred_at) "
                       "VALUES (:i, :o, :u, :c, 'seed_history', 1, 1, now())"), {"i": evidence_id, "o": legacy["org"], "u": legacy["learner_a"], "c": legacy["comp_one"]})
    with e.connect() as c:
        with pytest.raises(Exception, match="append-only"):
            c.execute(text("UPDATE evidence_records SET signal = 0 WHERE id = :i"), {"i": evidence_id})
        c.rollback()
        with pytest.raises(Exception, match="append-only"):
            c.execute(text("DELETE FROM evidence_records WHERE id = :i"), {"i": evidence_id})
        c.rollback()
        with pytest.raises(Exception):     # signal must be a probability
            c.execute(text("INSERT INTO evidence_records (id, org_id, user_id, competency_id, source_type, signal, confidence, occurred_at) "
                           "VALUES (:i, :o, :u, :c, 'x', 2, 1, now())"), {"i": uuid.uuid4(), "o": legacy["org"], "u": legacy["learner_a"], "c": legacy["comp_one"]})
        c.rollback()
        with pytest.raises(Exception):     # evidence cannot point at another tenant's competency
            other = uuid.uuid4()
            c.execute(text("INSERT INTO organizations (id, name, slug) VALUES (:i, 'x', :s)"), {"i": other, "s": f"x-{other.hex[:8]}"})
            c.execute(text("INSERT INTO evidence_records (id, org_id, user_id, competency_id, source_type, signal, confidence, occurred_at) "
                           "VALUES (:i, :o, :u, :c, 'x', 1, 1, now())"), {"i": uuid.uuid4(), "o": other, "u": legacy["learner_a"], "c": legacy["comp_one"]})
        c.rollback()


def test_new_columns_exist_with_safe_defaults(legacy):
    e = legacy["engine"]
    assert {"expected_answer", "rubric"} <= scalar_set(e, "SELECT column_name FROM information_schema.columns WHERE table_name = 'quiz_questions'")
    assert {"grading_status", "score_fraction", "grading_result_id"} <= scalar_set(e, "SELECT column_name FROM information_schema.columns WHERE table_name = 'question_responses'")
    assert "grading_status" in scalar_set(e, "SELECT column_name FROM information_schema.columns WHERE table_name = 'quiz_attempts'")
    assert "risk_details" in scalar_set(e, "SELECT column_name FROM information_schema.columns WHERE table_name = 'learner_risks'")


def test_running_the_migration_again_changes_nothing_and_never_demotes_real_evidence(legacy):
    e = legacy["engine"]
    with e.begin() as c:       # a state written by the new engine
        c.execute(text("UPDATE learner_competencies SET basis = 'evidence', data_points_count = 3 WHERE id = :i"), {"i": legacy["plain"]})
    alembic("stamp", PREVIOUS)                        # pretend it has not run, so the same steps run on an already migrated schema
    alembic("upgrade", "head")
    assert row(e, "SELECT basis, data_points_count FROM learner_competencies WHERE id = :i", i=legacy["plain"]) == {"basis": "evidence", "data_points_count": 3}
    assert row(e, "SELECT basis FROM learner_competencies WHERE id = :i", i=legacy["out_of_range"])["basis"] == "legacy_unverified"
    assert row(e, "SELECT count(*) AS n FROM learner_competencies")["n"] == 3
    assert row(e, "SELECT count(*) AS n FROM evidence_records")["n"] == 1


def test_downgrade_restores_the_previous_shape_and_keeps_the_states(legacy):
    e = legacy["engine"]
    alembic("downgrade", PREVIOUS)
    tables = scalar_set(e, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    columns = scalar_set(e, "SELECT column_name FROM information_schema.columns WHERE table_name = 'learner_competencies'")
    assert not ({"evidence_records", "competency_state_updates", "grading_results"} & tables)
    assert "basis" not in columns and "effective_evidence" not in columns
    assert row(e, "SELECT count(*) AS n FROM learner_competencies")["n"] == 3
    alembic("upgrade", "head")
