"""
Migration 006 on a database that already holds data.

The shared test database is built on an empty schema, so it cannot show what the migration
does to real rows. This builds a second scratch database, walks it back to revision 005,
inserts the kind of data a live installation has (adaptive sessions, events whose payloads
name quizzes, questions and competencies), upgrades, and checks what happened to it.
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
    REPO_ROOT, TEST_DB_NAME, _admin_connection, _dev_sync_url, make_competency, make_course, make_org, make_user, only_module,
)

pytestmark = pytest.mark.integration

MIG_DB = f"{TEST_DB_NAME}_mig006"
MIG_URL = _dev_sync_url.set(database=MIG_DB).render_as_string(hide_password=False)


def alembic(*args):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "database/alembic.ini", *args],
        cwd=REPO_ROOT, env={**os.environ, "DATABASE_URL_SYNC": MIG_URL}, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"


@pytest.fixture(scope="module")
def legacy():
    """A database at revision 005 with legacy rows. Yields ids and an engine."""
    conn = _admin_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (MIG_DB,))
        cur.execute(f'DROP DATABASE IF EXISTS "{MIG_DB}"')
        cur.execute(f'CREATE DATABASE "{MIG_DB}"')
    conn.close()

    alembic("upgrade", "head")
    alembic("downgrade", "005_content_ingestion")       # back to the shape a live installation has today

    engine = create_engine(MIG_URL)
    with engine.connect() as c:
        tables = {r[0] for r in c.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))}
    assert "learning_sessions" not in tables and "event_outbox" not in tables

    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    org = make_org(db)
    other_org = make_org(db)
    owner = make_user(db, org, ["ld_admin"])
    learner = make_user(db, org, ["learner"])
    other_owner = make_user(db, other_org, ["ld_admin"])
    course = make_course(db, org, owner, content_seconds=[])
    module = only_module(db, course)
    other_course = make_course(db, other_org, other_owner, content_seconds=[])
    other_module = only_module(db, other_course)
    competency_id = make_competency(db, org, "a.b").id
    other_competency_id = make_competency(db, other_org, "c.d").id
    quiz_id, foreign_quiz_id, question_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    from app.models import Quiz

    for qid, o, c, m in ((quiz_id, org.id, course.id, module.id), (foreign_quiz_id, other_org.id, other_course.id, other_module.id)):
        db.add(Quiz(id=qid, org_id=o, course_id=c, module_id=m, title="Quiz", passing_score=70.0, time_limit_mins=10, max_attempts=3))
    db.flush()
    db.execute(text("INSERT INTO quiz_questions (id, quiz_id, competency_id, question_text, question_type, points, order_index, created_at) "
                    "VALUES (:i, :q, :c, 'Q?', 'multiple_choice', 10, 0, now())"),
               {"i": question_id, "q": quiz_id, "c": competency_id})

    now = datetime.utcnow()
    ended, older_open, newer_open = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for sid, started, ended_at in ((ended, now - timedelta(days=3), now - timedelta(days=3) + timedelta(minutes=20)),
                                   (older_open, now - timedelta(days=2), None), (newer_open, now - timedelta(days=1), None)):
        db.execute(text("INSERT INTO adaptive_sessions (id, org_id, user_id, course_id, state, current_difficulty, metadata, started_at, ended_at) "
                        "VALUES (:i, :o, :u, :c, :s, 0.5, '{\"device\": \"x\"}', :st, :en)"),
                   {"i": sid, "o": org.id, "u": learner.id, "c": course.id, "s": "completed" if ended_at else "active", "st": started, "en": ended_at})

    def event(payload, session_id=None, kind="question_answered", content_offset=0):
        eid = uuid.uuid4()
        db.execute(text("INSERT INTO learning_events (id, org_id, user_id, session_id, course_id, event_type, payload, timestamp, processed) "
                        "VALUES (:i, :o, :u, :s, :c, :t, CAST(:p AS jsonb), :ts, false)"),
                   {"i": eid, "o": org.id, "u": learner.id, "s": session_id, "c": course.id, "t": kind,
                    "p": __import__("json").dumps(payload), "ts": now - timedelta(days=3) + timedelta(minutes=content_offset)})
        return eid

    ids = dict(
        good=event({"quiz_id": str(quiz_id), "question_id": str(question_id), "competency_id": str(competency_id)}, session_id=ended),
        foreign=event({"quiz_id": str(foreign_quiz_id), "competency_id": str(other_competency_id)}, content_offset=1),
        garbage=event({"quiz_id": "not-a-uuid", "question_id": 42, "competency_id": None}, content_offset=2),
        plain=event({}, kind="content_started", content_offset=3),
        on_open=event({}, session_id=newer_open, kind="content_started", content_offset=4),
    )
    db.commit()
    db.close()
    yield dict(engine=engine, org=org.id, learner=learner.id, course=course.id, quiz=quiz_id, question=question_id, competency=competency_id,
               ended=ended, older_open=older_open, newer_open=newer_open, **{f"event_{k}": v for k, v in ids.items()})
    engine.dispose()
    conn = _admin_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (MIG_DB,))
        cur.execute(f'DROP DATABASE IF EXISTS "{MIG_DB}"')
    conn.close()


def row(engine, sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).mappings().first()


def test_upgrade_carries_existing_data_across(legacy):
    alembic("upgrade", "head")
    e = legacy["engine"]

    # sessions: same ids; the newest open one stays open, the older open one is closed as superseded
    a = row(e, "SELECT * FROM learning_sessions WHERE id = :i", i=legacy["ended"])
    assert a["end_reason"] == "explicit" and a["ended_at"] is not None and a["context"]["source"] == "adaptive_session_backfill" and a["context"]["device"] == "x"
    old = row(e, "SELECT * FROM learning_sessions WHERE id = :i", i=legacy["older_open"])
    assert old["end_reason"] == "superseded" and old["ended_at"] == old["started_at"]
    new = row(e, "SELECT * FROM learning_sessions WHERE id = :i", i=legacy["newer_open"])
    assert new["ended_at"] is None and new["end_reason"] is None
    assert row(e, "SELECT count(*) AS n FROM learning_sessions WHERE user_id = :u AND ended_at IS NULL", u=legacy["learner"])["n"] == 1

    # events keep their sessions and gain references only where the target exists in the same tenant
    good = row(e, "SELECT * FROM learning_events WHERE id = :i", i=legacy["event_good"])
    assert good["session_id"] == legacy["ended"]
    assert (good["assessment_id"], good["question_id"], good["competency_id"]) == (legacy["quiz"], legacy["question"], legacy["competency"])
    foreign = row(e, "SELECT * FROM learning_events WHERE id = :i", i=legacy["event_foreign"])
    assert (foreign["assessment_id"], foreign["competency_id"]) == (None, None)      # another tenant's ids are never linked
    garbage = row(e, "SELECT * FROM learning_events WHERE id = :i", i=legacy["event_garbage"])
    assert (garbage["assessment_id"], garbage["question_id"], garbage["competency_id"]) == (None, None, None)
    assert row(e, "SELECT received_at = timestamp AS same FROM learning_events WHERE id = :i", i=legacy["event_plain"])["same"] is True
    assert row(e, "SELECT session_id FROM learning_events WHERE id = :i", i=legacy["event_on_open"])["session_id"] == legacy["newer_open"]


def test_after_upgrade_the_guarantees_hold_on_the_migrated_data(legacy):
    e = legacy["engine"]
    with e.connect() as c:
        with pytest.raises(Exception, match="append-only"):
            c.execute(text("UPDATE learning_events SET event_type = 'x' WHERE id = :i"), {"i": legacy["event_good"]})
        c.rollback()
        with pytest.raises(Exception):
            c.execute(text("INSERT INTO learning_sessions (id, org_id, user_id, course_id) VALUES (:i, :o, :u, :c)"),
                      {"i": uuid.uuid4(), "o": legacy["org"], "u": legacy["learner"], "c": legacy["course"]})   # a second open session
        c.rollback()
    assert row(e, "SELECT count(*) AS n FROM learning_events")["n"] == 5


def test_running_the_upgrade_again_changes_nothing(legacy):
    alembic("downgrade", "005_content_ingestion")
    alembic("upgrade", "head")
    assert row(legacy["engine"], "SELECT count(*) AS n FROM learning_sessions")["n"] == 3
    assert row(legacy["engine"], "SELECT count(*) AS n FROM learning_events WHERE assessment_id IS NOT NULL")["n"] == 1


def test_downgrade_restores_the_previous_shape_and_keeps_the_events(legacy):
    alembic("downgrade", "005_content_ingestion")
    e = legacy["engine"]
    with e.connect() as c:
        tables = {r[0] for r in c.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))}
        columns = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'learning_events'"))}
    assert "learning_sessions" not in tables and "event_outbox" not in tables
    assert not ({"assessment_id", "question_id", "competency_id", "received_at", "idempotency_key"} & columns)
    assert row(e, "SELECT count(*) AS n FROM learning_events")["n"] == 5            # nothing was lost
    # the old link works again: the events still name their (adaptive) sessions
    assert row(e, "SELECT session_id FROM learning_events WHERE id = :i", i=legacy["event_good"])["session_id"] == legacy["ended"]
    with e.connect() as c:
        c.execute(text("UPDATE learning_events SET payload = payload WHERE id = :i"), {"i": legacy["event_good"]})   # editable again: no trigger
        c.commit()
    alembic("upgrade", "head")
