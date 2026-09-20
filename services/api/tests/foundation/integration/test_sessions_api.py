"""Learning sessions through the API: lifecycle, idle handling, implicit sessions, visibility."""

import uuid
from datetime import datetime, timedelta

import pytest

from app.models import LearningEvent, LearningSession, Team, UserTeam
from tests.foundation.conftest import API, auth, enroll, make_course, make_item, make_org, make_user, only_module

pytestmark = pytest.mark.integration

SESSIONS = f"{API}/learning/sessions"


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    item = make_item(db_session, org, course, module, content_type="VIDEO")
    second_course = make_course(db_session, org, ld, content_seconds=[])
    enroll(db_session, org, learner, course)
    db_session.commit()
    return org, ld, learner, course, item, second_course


async def start(client, user, course, **context):
    return await client.post(f"{SESSIONS}/start", json={"course_id": str(course.id), "context": context}, headers=auth(user))


def events_of(db_session, session_id, kind=None):
    db_session.expire_all()
    query = db_session.query(LearningEvent).filter_by(session_id=session_id)
    if kind:
        query = query.filter_by(event_type=kind)
    return query.order_by(LearningEvent.timestamp, LearningEvent.id).all()


# ============================================================================== lifecycle
async def test_starting_a_session_creates_a_real_record_and_an_event(client, scene, db_session):
    org, _, learner, course, _, _ = scene
    resp = await start(client, learner, course, source="outline", item="first")
    assert resp.status_code == 201
    body = resp.json()
    assert (body["status"], body["state"], body["course_id"], body["user_id"]) == ("created", "active", str(course.id), str(learner.id))
    assert body["ended_at"] is None and body["context"] == {"source": "outline", "item": "first"}

    row = db_session.get(LearningSession, uuid.UUID(body["session_id"]))
    assert row.org_id == org.id and row.user_id == learner.id and row.ended_at is None
    assert [e.event_type for e in events_of(db_session, row.id)] == ["session_started"]


async def test_starting_again_resumes_the_open_session(client, scene, db_session):
    _, _, learner, course, _, _ = scene
    first = (await start(client, learner, course)).json()
    second = (await start(client, learner, course)).json()
    assert second["session_id"] == first["session_id"] and second["status"] == "resumed"
    assert len(events_of(db_session, uuid.UUID(first["session_id"]), "session_started")) == 1


async def test_each_course_has_its_own_session(client, scene):
    _, _, learner, course, _, second_course = scene
    a = (await start(client, learner, course)).json()
    b = (await start(client, learner, second_course)).json()
    assert a["session_id"] != b["session_id"]


async def test_a_session_can_only_be_started_in_a_course_of_your_tenant(client, scene, db_session):
    _, _, learner, _, _, _ = scene
    other_org = make_org(db_session)
    foreign_course = make_course(db_session, other_org, make_user(db_session, other_org, ["ld_admin"]), content_seconds=[])
    db_session.commit()
    assert (await start(client, learner, foreign_course)).status_code == 404
    assert (await client.post(f"{SESSIONS}/start", json={"course_id": str(uuid.uuid4())}, headers=auth(learner))).status_code == 404


async def test_ending_a_session_records_when_why_and_an_event(client, scene, db_session):
    _, _, learner, course, _, _ = scene
    session_id = (await start(client, learner, course)).json()["session_id"]
    resp = await client.post(f"{SESSIONS}/{session_id}/end", headers=auth(learner))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ended" and body["end_reason"] == "explicit" and body["ended_at"]
    completed = events_of(db_session, uuid.UUID(session_id), "session_completed")
    assert len(completed) == 1 and completed[0].payload["reason"] == "explicit"
    assert completed[0].payload["duration_seconds"] == body["duration_seconds"]


async def test_ending_twice_changes_nothing(client, scene, db_session):
    _, _, learner, course, _, _ = scene
    session_id = (await start(client, learner, course)).json()["session_id"]
    first = (await client.post(f"{SESSIONS}/{session_id}/end", headers=auth(learner))).json()
    second = (await client.post(f"{SESSIONS}/{session_id}/end", headers=auth(learner))).json()
    assert second["ended_at"] == first["ended_at"]
    assert len(events_of(db_session, uuid.UUID(session_id), "session_completed")) == 1


async def test_a_new_session_starts_after_the_previous_one_ended(client, scene):
    _, _, learner, course, _, _ = scene
    first = (await start(client, learner, course)).json()["session_id"]
    await client.post(f"{SESSIONS}/{first}/end", headers=auth(learner))
    second = (await start(client, learner, course)).json()
    assert second["status"] == "created" and second["session_id"] != first


async def test_heartbeat_keeps_a_session_alive_and_is_refused_once_it_ended(client, scene, db_session):
    _, _, learner, course, _, _ = scene
    session_id = (await start(client, learner, course)).json()["session_id"]
    row = db_session.get(LearningSession, uuid.UUID(session_id))
    row.last_activity_at = datetime.utcnow() - timedelta(minutes=20)
    db_session.commit()
    beat = (await client.post(f"{SESSIONS}/{session_id}/heartbeat", headers=auth(learner))).json()
    assert datetime.fromisoformat(beat["last_activity_at"]) > datetime.utcnow() - timedelta(minutes=1)

    await client.post(f"{SESSIONS}/{session_id}/end", headers=auth(learner))
    ended = await client.post(f"{SESSIONS}/{session_id}/heartbeat", headers=auth(learner))
    assert ended.status_code == 409 and ended.json()["detail"]["code"] == "session_ended"


async def test_the_active_session_endpoint(client, scene):
    _, _, learner, course, _, second_course = scene
    assert (await client.get(f"{SESSIONS}/active", headers=auth(learner))).json() == {"active": False, "session": None}
    session_id = (await start(client, learner, course)).json()["session_id"]
    assert (await client.get(f"{SESSIONS}/active", headers=auth(learner))).json()["session"]["session_id"] == session_id
    assert (await client.get(f"{SESSIONS}/active", params={"course_id": str(course.id)}, headers=auth(learner))).json()["active"] is True
    assert (await client.get(f"{SESSIONS}/active", params={"course_id": str(second_course.id)}, headers=auth(learner))).json()["active"] is False


# ==================================================================================== idle
async def test_a_forgotten_session_is_closed_at_its_last_activity_not_when_noticed(client, scene, db_session):
    """A tab left open overnight must not count as hours of learning."""
    _, _, learner, course, _, _ = scene
    old = (await start(client, learner, course)).json()
    row = db_session.get(LearningSession, uuid.UUID(old["session_id"]))
    started = datetime.utcnow() - timedelta(hours=5)
    last_seen = started + timedelta(minutes=12)
    row.started_at, row.last_activity_at = started, last_seen
    db_session.commit()

    fresh = (await start(client, learner, course)).json()
    assert fresh["status"] == "created" and fresh["session_id"] != old["session_id"]

    db_session.expire_all()
    closed = db_session.get(LearningSession, uuid.UUID(old["session_id"]))
    assert closed.end_reason == "idle" and closed.ended_at == last_seen
    completed = events_of(db_session, closed.id, "session_completed")[0]
    assert completed.timestamp == last_seen and completed.payload["duration_seconds"] == 12 * 60


async def test_the_active_endpoint_closes_a_quiet_session_and_reports_none(client, scene, db_session):
    _, _, learner, course, _, _ = scene
    session_id = (await start(client, learner, course)).json()["session_id"]
    row = db_session.get(LearningSession, uuid.UUID(session_id))
    row.last_activity_at = datetime.utcnow() - timedelta(hours=2)
    row.started_at = row.last_activity_at - timedelta(minutes=5)
    db_session.commit()
    assert (await client.get(f"{SESSIONS}/active", headers=auth(learner))).json()["active"] is False
    db_session.expire_all()
    assert db_session.get(LearningSession, uuid.UUID(session_id)).end_reason == "idle"


async def test_a_listed_quiet_session_is_marked_idle(client, scene, db_session):
    _, _, learner, course, _, _ = scene
    session_id = (await start(client, learner, course)).json()["session_id"]
    row = db_session.get(LearningSession, uuid.UUID(session_id))
    row.last_activity_at = datetime.utcnow() - timedelta(hours=1)
    row.started_at = row.last_activity_at - timedelta(minutes=1)
    db_session.commit()
    listed = (await client.get(SESSIONS, headers=auth(learner))).json()["items"]
    assert next(s for s in listed if s["session_id"] == session_id)["state"] == "idle"


# ================================================================================= implicit
async def test_course_activity_with_no_session_starts_one_implicitly(client, scene, db_session):
    _, _, learner, _, item, _ = scene
    resp = await client.post(f"{API}/progress/content/{item.id}", json={"status": "in_progress", "progress_percent": 5}, headers=auth(learner))
    assert resp.status_code == 200
    sessions = db_session.query(LearningSession).filter_by(user_id=learner.id).all()
    assert len(sessions) == 1 and sessions[0].context == {"source": "implicit"}
    started = db_session.query(LearningEvent).filter_by(user_id=learner.id, event_type="content_started").one()
    assert started.session_id == sessions[0].id


async def test_an_explicit_session_is_reused_by_later_activity(client, scene, db_session):
    _, _, learner, course, item, _ = scene
    session_id = (await start(client, learner, course, source="player")).json()["session_id"]
    await client.post(f"{API}/progress/content/{item.id}", json={"status": "in_progress", "progress_percent": 5}, headers=auth(learner))
    await client.post(f"{API}/events", json={"event_type": "lesson_opened", "content_id": str(item.id)}, headers=auth(learner))
    assert db_session.query(LearningSession).filter_by(user_id=learner.id).count() == 1
    kinds = {e.event_type for e in events_of(db_session, uuid.UUID(session_id))}
    assert {"session_started", "content_started", "lesson_opened"} <= kinds


# ============================================================================== visibility
async def test_a_learner_sees_only_their_own_sessions(client, scene, db_session):
    org, _, learner, course, _, _ = scene
    peer = make_user(db_session, org, ["learner"])
    db_session.commit()
    mine = (await start(client, learner, course)).json()["session_id"]
    theirs = (await start(client, peer, course)).json()["session_id"]
    listed = {s["session_id"] for s in (await client.get(SESSIONS, headers=auth(learner))).json()["items"]}
    assert mine in listed and theirs not in listed
    assert (await client.get(f"{SESSIONS}/{theirs}", headers=auth(learner))).status_code == 404
    assert (await client.get(f"{SESSIONS}/{theirs}/events", headers=auth(learner))).status_code == 404
    assert (await client.post(f"{SESSIONS}/{theirs}/end", headers=auth(learner))).status_code == 404
    assert (await client.post(f"{SESSIONS}/{theirs}/heartbeat", headers=auth(learner))).status_code == 404
    assert (await client.get(SESSIONS, params={"user_id": str(peer.id)}, headers=auth(learner))).json()["items"] == []


async def test_a_manager_sees_their_teams_sessions_and_nobody_elses(client, scene, db_session):
    org, _, learner, course, _, _ = scene
    manager = make_user(db_session, org, ["manager"])
    stranger = make_user(db_session, org, ["learner"])
    team = Team(id=uuid.uuid4(), org_id=org.id, name="Data", manager_id=manager.id)
    db_session.add(team)
    db_session.flush()
    db_session.add(UserTeam(user_id=learner.id, team_id=team.id, org_id=org.id))
    db_session.commit()
    on_team = (await start(client, learner, course)).json()["session_id"]
    off_team = (await start(client, stranger, course)).json()["session_id"]

    listed = {s["session_id"] for s in (await client.get(SESSIONS, headers=auth(manager))).json()["items"]}
    assert on_team in listed and off_team not in listed
    assert (await client.get(f"{SESSIONS}/{on_team}", headers=auth(manager))).status_code == 200
    assert (await client.get(f"{SESSIONS}/{off_team}", headers=auth(manager))).status_code == 404


async def test_l_and_d_admins_see_the_whole_organisation(client, scene, db_session):
    org, ld, learner, course, _, _ = scene
    other = make_user(db_session, org, ["learner"])
    db_session.commit()
    a = (await start(client, learner, course)).json()["session_id"]
    b = (await start(client, other, course)).json()["session_id"]
    listed = {s["session_id"] for s in (await client.get(SESSIONS, params={"limit": 200}, headers=auth(ld))).json()["items"]}
    assert {a, b} <= listed


async def test_session_details_summarise_what_happened_from_the_events(client, scene, db_session):
    _, _, learner, course, item, _ = scene
    session_id = (await start(client, learner, course)).json()["session_id"]
    await client.post(f"{API}/events", json={"event_type": "lesson_opened", "content_id": str(item.id), "session_id": session_id}, headers=auth(learner))
    await client.post(f"{API}/events", json={"event_type": "video_started", "content_id": str(item.id), "session_id": session_id,
                                             "payload": {"position_seconds": 0}}, headers=auth(learner))
    detail = (await client.get(f"{SESSIONS}/{session_id}", headers=auth(learner))).json()
    assert detail["summary"]["by_type"] == {"session_started": 1, "lesson_opened": 1, "video_started": 1}
    assert detail["summary"]["events"] == 3 and detail["summary"]["content_items_touched"] == 1
    assert detail["summary"]["questions_answered"] == 0

    timeline = (await client.get(f"{SESSIONS}/{session_id}/events", headers=auth(learner))).json()
    assert [e["event_type"] for e in timeline["items"]] == ["session_started", "lesson_opened", "video_started"]
    assert timeline["session"]["session_id"] == session_id and timeline["next_cursor"] is None


async def test_session_lists_can_be_filtered(client, scene):
    _, _, learner, course, _, second_course = scene
    a = (await start(client, learner, course)).json()["session_id"]
    await client.post(f"{SESSIONS}/{a}/end", headers=auth(learner))
    b = (await start(client, learner, second_course)).json()["session_id"]
    async def listing(**params):
        return {s["session_id"] for s in (await client.get(SESSIONS, params=params, headers=auth(learner))).json()["items"]}

    assert await listing(course_id=str(course.id)) == {a}
    assert await listing(active="true") == {b}
    assert await listing(active="false") == {a}
