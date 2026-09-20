"""
Tenant isolation for events and sessions.

Tenant B's learner works (through the API); tenant A's most privileged non-platform users
then try to read, end, or write into that activity. A foreign id must look exactly like one
that does not exist, and nothing of B's may appear in any of A's listings or statistics.
"""

import uuid

import pytest

from app.models import LearningEvent, LearningSession
from tests.foundation.conftest import API, auth, make_assignment, make_item, make_quiz

pytestmark = pytest.mark.integration


@pytest.fixture
async def foreign(client, world, db_session):
    """Tenant B: a session with real events, a quiz question with an open attempt, and an assignment."""
    b = world.b
    quiz_item = make_item(db_session, b.org, b.course, b.module, content_type="QUIZ", order_index=50)
    quiz, built = make_quiz(db_session, b.org, b.course, b.module, quiz_item, questions=1)
    lab_item = make_item(db_session, b.org, b.course, b.module, content_type="ASSIGNMENT", order_index=51)
    assignment = make_assignment(db_session, b.org, b.course, b.module, lab_item)
    db_session.commit()

    started = (await client.post(f"{API}/learning/sessions/start", json={"course_id": str(b.course.id)}, headers=auth(b.learner))).json()
    opened = (await client.post(f"{API}/events", headers=auth(b.learner),
                                json={"event_type": "lesson_opened", "content_id": str(b.content.id), "session_id": started["session_id"]})).json()
    attempt = (await client.post(f"{API}/quizzes/{quiz.id}/attempts", headers=auth(b.learner))).json()
    return dict(session=started["session_id"], event=opened["event_id"], content=b.content, question=built[0][0], quiz=quiz,
                attempt=attempt["id"], assignment=assignment)


async def test_foreign_sessions_are_not_found(client, world, foreign):
    for user in (world.a.org_admin, world.a.ld_admin, world.a.learner, world.a.manager):
        for method, path in (("GET", f"/learning/sessions/{foreign['session']}"), ("GET", f"/learning/sessions/{foreign['session']}/events"),
                             ("POST", f"/learning/sessions/{foreign['session']}/end"), ("POST", f"/learning/sessions/{foreign['session']}/heartbeat")):
            resp = await client.request(method, f"{API}{path}", headers=auth(user))
            assert resp.status_code == 404, (method, path, resp.status_code)


async def test_a_foreign_event_is_not_found_and_matches_a_missing_one(client, world, foreign):
    for user in (world.a.org_admin, world.a.ld_admin, world.a.learner):
        real = await client.get(f"{API}/events/{foreign['event']}", headers=auth(user))
        missing = await client.get(f"{API}/events/{uuid.uuid4()}", headers=auth(user))
        assert real.status_code == missing.status_code == 404 and real.json() == missing.json()


async def test_listings_and_statistics_never_include_another_tenant(client, world, foreign, db_session):
    b_ids = {str(e.id) for e in db_session.query(LearningEvent).filter_by(org_id=world.b.org.id)}
    b_sessions = {str(s.id) for s in db_session.query(LearningSession).filter_by(org_id=world.b.org.id)}
    for user in (world.a.org_admin, world.a.ld_admin):
        listing = (await client.get(f"{API}/events", params={"limit": 200}, headers=auth(user))).json()["items"]
        assert not ({e["id"] for e in listing} & b_ids)
        assert not ({e["user_id"] for e in listing} & {str(world.b.learner.id)})
        sessions = (await client.get(f"{API}/learning/sessions", params={"limit": 200}, headers=auth(user))).json()["items"]
        assert not ({s["session_id"] for s in sessions} & b_sessions)
        # even when asked for by name, or filtered by the foreign ids
        assert (await client.get(f"{API}/events", params={"user_id": str(world.b.learner.id)}, headers=auth(user))).json()["items"] == []
        assert (await client.get(f"{API}/events", params={"session_id": foreign["session"]}, headers=auth(user))).json()["items"] == []
        assert (await client.get(f"{API}/events", params={"course_id": str(world.b.course.id)}, headers=auth(user))).json()["items"] == []
        assert (await client.get(f"{API}/learning/sessions", params={"user_id": str(world.b.learner.id)}, headers=auth(user))).json()["items"] == []
        stats = (await client.get(f"{API}/events/stats", params={"course_id": str(world.b.course.id)}, headers=auth(user))).json()
        assert stats["total_events"] == 0 and stats["learners"] == 0


async def test_events_cannot_be_written_against_another_tenants_items(client, world, foreign):
    a = world.a.learner
    attempts = [
        {"event_type": "lesson_opened", "content_id": str(foreign["content"].id)},
        {"event_type": "question_shown", "question_id": str(foreign["question"].id), "payload": {"attempt_id": foreign["attempt"]}},
        {"event_type": "assignment_opened", "payload": {"assignment_id": str(foreign["assignment"].id)}},
        {"event_type": "lesson_opened", "content_id": str(world.a.content.id), "session_id": foreign["session"]},
    ]
    for body in attempts:
        resp = await client.post(f"{API}/events", json=body, headers=auth(a))
        assert resp.status_code in (404, 422), (body["event_type"], resp.status_code)


async def test_a_session_cannot_be_started_in_another_tenants_course(client, world):
    resp = await client.post(f"{API}/learning/sessions/start", json={"course_id": str(world.b.course.id)}, headers=auth(world.a.learner))
    assert resp.status_code == 404


async def test_nothing_of_the_foreign_session_changed(client, world, foreign, db_session):
    await client.post(f"{API}/learning/sessions/{foreign['session']}/end", headers=auth(world.a.org_admin))
    db_session.expire_all()
    assert db_session.get(LearningSession, uuid.UUID(foreign["session"])).ended_at is None


async def test_a_super_admin_reaches_another_tenant_only_by_naming_it(client, world, foreign):
    without = (await client.get(f"{API}/events", params={"limit": 200}, headers=auth(world.super_admin))).json()["items"]
    assert str(world.b.learner.id) not in {e["user_id"] for e in without}
    named = await client.get(f"{API}/events", params={"limit": 200}, headers={**auth(world.super_admin), "X-Tenant-ID": str(world.b.org.id)})
    assert str(world.b.learner.id) in {e["user_id"] for e in named.json()["items"]}


async def test_the_tenant_check_alone_stops_a_question_reference_even_if_an_attempt_row_existed(client, world, foreign, db_session):
    """Defence in depth: were a tenant-A learner ever to hold an attempt on tenant B's quiz (bad data, an old bug),
    the question lookup itself must still refuse tenant B's question."""
    from datetime import datetime

    from app.models import QuizAttempt

    stray = QuizAttempt(id=uuid.uuid4(), quiz_id=foreign["quiz"].id, user_id=world.a.learner.id, attempt_number=1, started_at=datetime.utcnow())
    db_session.add(stray)
    db_session.commit()
    resp = await client.post(f"{API}/events", headers=auth(world.a.learner), json={
        "event_type": "question_shown", "question_id": str(foreign["question"].id), "payload": {"attempt_id": str(stray.id)}})
    assert resp.status_code == 404
