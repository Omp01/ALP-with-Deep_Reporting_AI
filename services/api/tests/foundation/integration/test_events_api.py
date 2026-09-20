"""The events API: what a browser may report and how it is checked, and how events are queried."""

import uuid
from datetime import datetime, timedelta

import pytest

from app.models import LearningEvent, LearningSession, Team, UserTeam
from tests.foundation.conftest import (
    API, auth, enroll, make_competency, make_course, make_item, make_org, make_quiz, make_assignment, make_user, only_module,
)

pytestmark = pytest.mark.integration

EVENTS = f"{API}/events"
SESSIONS = f"{API}/learning/sessions"


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    video = make_item(db_session, org, course, module, content_type="VIDEO", order_index=0)
    article = make_item(db_session, org, course, module, content_type="ARTICLE", order_index=1)
    competency = make_competency(db_session, org, "sql.joins")
    quiz_item = make_item(db_session, org, course, module, content_type="QUIZ", order_index=2)
    quiz, built = make_quiz(db_session, org, course, module, quiz_item, questions=2, competency=competency)
    lab_item = make_item(db_session, org, course, module, content_type="ASSIGNMENT", order_index=3)
    assignment = make_assignment(db_session, org, course, module, lab_item)
    enroll(db_session, org, learner, course)
    db_session.commit()
    return dict(org=org, ld=ld, learner=learner, course=course, module=module, video=video, article=article, quiz=quiz,
                questions=[q for q, _ in built], competency=competency, assignment=assignment, lab_item=lab_item)


async def post(client, user, **body):
    return await client.post(EVENTS, json=body, headers=auth(user))


def stored(db_session, user, kind=None):
    db_session.expire_all()
    query = db_session.query(LearningEvent).filter_by(user_id=user.id)
    if kind:
        query = query.filter_by(event_type=kind)
    return query.order_by(LearningEvent.timestamp, LearningEvent.id).all()


# ================================================================================ ingestion
async def test_a_lesson_opened_event_is_recorded_with_everything_derived_server_side(client, scene, db_session):
    s = scene
    resp = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), payload={"source": "outline"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ingested" and body["event_type"] == "lesson_opened" and body["session_id"]

    [event] = stored(db_session, s["learner"], "lesson_opened")
    assert event.org_id == s["org"].id and event.user_id == s["learner"].id
    assert (event.course_id, event.module_id, event.content_id) == (s["course"].id, s["module"].id, s["video"].id)
    assert event.payload == {"source": "outline"} and event.received_at is not None and str(event.session_id) == body["session_id"]


async def test_the_tenant_and_learner_come_from_the_token_not_the_body(client, scene, db_session):
    s = scene
    other_org = make_org(db_session)
    db_session.commit()
    await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id),
               org_id=str(other_org.id), user_id=str(s["ld"].id))
    [event] = stored(db_session, s["learner"], "lesson_opened")
    assert event.org_id == s["org"].id and event.user_id == s["learner"].id


@pytest.mark.parametrize("kind, payload", [
    ("video_started", {"position_seconds": 0, "duration_seconds": 754}),
    ("video_paused", {"position_seconds": 61}),
    ("video_resumed", {"position_seconds": 61}),
    ("video_progress", {"position_seconds": 90, "percent": 12}),
])
async def test_video_interaction_events(client, scene, db_session, kind, payload):
    resp = await post(client, scene["learner"], event_type=kind, content_id=str(scene["video"].id), payload=payload)
    assert resp.status_code == 201, resp.text
    [event] = stored(db_session, scene["learner"], kind)
    assert event.payload["position_seconds"] == payload["position_seconds"]


async def test_article_opened(client, scene):
    assert (await post(client, scene["learner"], event_type="article_opened", content_id=str(scene["article"].id))).status_code == 201


@pytest.mark.parametrize("kind", ["question_answered", "assessment_completed", "content_completed", "content_started", "assignment_graded",
                                  "assignment_submitted", "competency_updated", "answer_graded", "session_completed", "adaptive_decision_made"])
async def test_a_learner_cannot_report_evidence_about_themselves(client, scene, db_session, kind):
    resp = await post(client, scene["learner"], event_type=kind, content_id=str(scene["video"].id),
                      payload={"is_correct": True, "score": 100})
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "server_only_event"
    assert stored(db_session, scene["learner"], kind) == []


async def test_even_an_administrator_cannot_forge_server_facts_through_the_browser_endpoint(client, scene):
    resp = await post(client, scene["ld"], event_type="question_answered", question_id=str(scene["questions"][0].id))
    assert resp.status_code == 403


@pytest.mark.parametrize("kind, code", [("made_up", "unknown_event_type"), ("article_read", "deprecated_event_type"), ("", "unknown_event_type")])
async def test_unknown_event_types_are_refused_with_the_accepted_list(client, scene, kind, code):
    resp = await post(client, scene["learner"], event_type=kind, content_id=str(scene["video"].id))
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == code
    assert "lesson_opened" in resp.json()["detail"]["accepted"]


async def test_legacy_names_are_accepted_and_stored_under_the_current_name(client, scene, db_session):
    s = scene
    attempt = (await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts", headers=auth(s["learner"]))).json()
    resp = await post(client, s["learner"], event_type="question_viewed", question_id=str(s["questions"][0].id), payload={"attempt_id": attempt["id"]})
    assert resp.status_code == 201 and resp.json()["event_type"] == "question_shown"
    assert stored(db_session, s["learner"], "question_viewed") == []


async def test_payloads_are_validated_and_extra_fields_rejected(client, scene, db_session):
    s = scene
    for bad in ({"position_seconds": -4}, {"position_seconds": 5, "note": "x"}, {}):
        resp = await post(client, s["learner"], event_type="video_started", content_id=str(s["video"].id), payload=bad)
        assert resp.status_code == 422 and resp.json()["detail"]["code"] == "invalid_payload"
    assert stored(db_session, s["learner"], "video_started") == []


async def test_content_must_exist_in_the_callers_tenant(client, scene, db_session):
    other_org = make_org(db_session)
    other_owner = make_user(db_session, other_org, ["ld_admin"])
    other_course = make_course(db_session, other_org, other_owner, content_seconds=[])
    foreign = make_item(db_session, other_org, other_course, only_module(db_session, other_course))
    db_session.commit()
    for content_id in (foreign.id, uuid.uuid4()):
        resp = await post(client, scene["learner"], event_type="lesson_opened", content_id=str(content_id))
        assert resp.status_code == 404
    assert (await post(client, scene["learner"], event_type="lesson_opened")).status_code == 422


async def test_a_wrong_course_id_is_a_mismatch_not_an_override(client, scene, db_session):
    s = scene
    other_course = make_course(db_session, s["org"], s["ld"], content_seconds=[])
    db_session.commit()
    resp = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), course_id=str(other_course.id))
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "reference_mismatch"
    ok = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), course_id=str(s["course"].id))
    assert ok.status_code == 201


async def test_an_oversized_or_malformed_body_is_rejected(client, scene):
    assert (await client.post(EVENTS, json={"content_id": "nope"}, headers=auth(scene["learner"]))).status_code == 422
    assert (await post(client, scene["learner"], event_type="x" * 300)).status_code == 422


# ----------------------------------------------------------------------------- idempotency
async def test_a_retry_with_the_same_key_is_recorded_once(client, scene, db_session):
    s = scene
    first = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), idempotency_key="open-1")
    again = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), idempotency_key="open-1")
    assert first.json()["status"] == "ingested" and again.json()["status"] == "duplicate_ignored"
    assert first.json()["event_id"] == again.json()["event_id"]
    assert len(stored(db_session, s["learner"], "lesson_opened")) == 1


async def test_the_legacy_event_id_field_works_as_the_key(client, scene, db_session):
    key = str(uuid.uuid4())
    for _ in range(2):
        await post(client, scene["learner"], event_type="lesson_opened", content_id=str(scene["video"].id), event_id=key)
    assert len(stored(db_session, scene["learner"], "lesson_opened")) == 1


async def test_two_learners_may_use_the_same_key(client, scene, db_session):
    s = scene
    peer = make_user(db_session, s["org"], ["learner"])
    db_session.commit()
    a = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), idempotency_key="k")
    b = await post(client, peer, event_type="lesson_opened", content_id=str(s["video"].id), idempotency_key="k")
    assert a.json()["status"] == "ingested" and b.json()["status"] == "ingested"
    assert a.json()["event_id"] != b.json()["event_id"]


# -------------------------------------------------------------------------------- timestamps
async def test_a_plausible_browser_time_is_kept_and_an_impossible_one_is_replaced(client, scene, db_session):
    s = scene
    when = (datetime.utcnow() - timedelta(minutes=3)).replace(microsecond=0)
    await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), timestamp=when.isoformat())
    await post(client, s["learner"], event_type="article_opened", content_id=str(s["article"].id), timestamp=(datetime.utcnow() + timedelta(days=2)).isoformat())
    await post(client, s["learner"], event_type="video_paused", content_id=str(s["video"].id), payload={"position_seconds": 3},
               timestamp=(datetime.utcnow() - timedelta(days=9)).isoformat())
    opened, article, paused = (stored(db_session, s["learner"], k)[0] for k in ("lesson_opened", "article_opened", "video_paused"))
    assert opened.timestamp == when
    for event in (article, paused):
        assert abs((event.timestamp - event.received_at).total_seconds()) < 1     # replaced by the server's time


# ---------------------------------------------------------------------------------- sessions
async def test_an_explicit_session_must_be_yours_and_open(client, scene, db_session):
    s = scene
    peer = make_user(db_session, s["org"], ["learner"])
    db_session.commit()
    mine = (await client.post(f"{SESSIONS}/start", json={"course_id": str(s["course"].id)}, headers=auth(s["learner"]))).json()["session_id"]
    theirs = (await client.post(f"{SESSIONS}/start", json={"course_id": str(s["course"].id)}, headers=auth(peer))).json()["session_id"]

    ok = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), session_id=mine)
    assert ok.status_code == 201 and ok.json()["session_id"] == mine
    assert (await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), session_id=theirs)).status_code == 404
    assert (await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), session_id=str(uuid.uuid4()))).status_code == 404

    await client.post(f"{SESSIONS}/{mine}/end", headers=auth(s["learner"]))
    gone = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), session_id=mine)
    assert gone.status_code == 409 and gone.json()["detail"]["code"] == "session_ended"


async def test_an_event_that_happened_before_the_session_ended_still_joins_it(client, scene, db_session):
    """On page close the browser flushes its last events and ends the session at the same moment."""
    s = scene
    session_id = (await client.post(f"{SESSIONS}/start", json={"course_id": str(s["course"].id)}, headers=auth(s["learner"]))).json()["session_id"]
    happened = datetime.utcnow() - timedelta(seconds=1)
    await client.post(f"{SESSIONS}/{session_id}/end", headers=auth(s["learner"]))

    late = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), session_id=session_id, timestamp=happened.isoformat())
    assert late.status_code == 201 and late.json()["session_id"] == session_id
    after = await post(client, s["learner"], event_type="lesson_opened", content_id=str(s["video"].id), session_id=session_id,
                       timestamp=(datetime.utcnow() + timedelta(seconds=30)).isoformat())
    assert after.status_code == 409 and after.json()["detail"]["code"] == "session_ended"
    db_session.expire_all()
    assert db_session.get(LearningSession, uuid.UUID(session_id)).ended_at is not None      # the session was not reopened


# --------------------------------------------------------------------------------- questions
async def test_question_events_need_a_real_open_attempt_of_yours(client, scene, db_session):
    s = scene
    attempt = (await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts", headers=auth(s["learner"]))).json()
    question = s["questions"][0]

    shown = await post(client, s["learner"], event_type="question_shown", question_id=str(question.id), payload={"attempt_id": attempt["id"], "position": 0})
    assert shown.status_code == 201
    [event] = stored(db_session, s["learner"], "question_shown")
    assert (event.assessment_id, event.question_id, event.competency_id) == (s["quiz"].id, question.id, s["competency"].id)
    assert (event.course_id, event.content_id) == (s["course"].id, s["quiz"].content_item_id)

    hint = await post(client, s["learner"], event_type="hint_requested", question_id=str(question.id), payload={"attempt_id": attempt["id"], "hint_index": 0})
    assert hint.status_code == 201

    peer = make_user(db_session, s["org"], ["learner"])
    db_session.commit()
    assert (await post(client, peer, event_type="question_shown", question_id=str(question.id), payload={"attempt_id": attempt["id"]})).status_code == 422
    assert (await post(client, s["learner"], event_type="question_shown", question_id=str(question.id), payload={"attempt_id": str(uuid.uuid4())})).status_code == 422
    assert (await post(client, s["learner"], event_type="question_shown", question_id=str(uuid.uuid4()), payload={"attempt_id": attempt["id"]})).status_code == 404

    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]),
                      json={"responses": [{"question_id": str(question.id)}]})
    late = await post(client, s["learner"], event_type="question_shown", question_id=str(question.id), payload={"attempt_id": attempt["id"]})
    assert late.status_code == 409 and late.json()["detail"]["code"] == "attempt_finished"      # no time given: cannot be shown to precede it
    after = await post(client, s["learner"], event_type="question_shown", question_id=str(question.id), payload={"attempt_id": attempt["id"]},
                       timestamp=(datetime.utcnow() + timedelta(seconds=30)).isoformat())
    assert after.status_code == 409                                                             # claims to be after the submission


async def test_a_question_shown_just_before_submission_is_accepted_when_it_arrives_just_after(client, scene, db_session):
    """The browser reports in batches: the last question's event can land after the attempt was submitted."""
    s = scene
    attempt = (await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts", headers=auth(s["learner"]))).json()
    shown_at = datetime.utcnow()
    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]),
                      json={"responses": [{"question_id": str(s["questions"][0].id)}]})
    resp = await post(client, s["learner"], event_type="question_shown", question_id=str(s["questions"][1].id),
                      payload={"attempt_id": attempt["id"], "position": 1}, timestamp=(shown_at - timedelta(seconds=1)).isoformat())
    assert resp.status_code == 201, resp.text
    [event] = stored(db_session, s["learner"], "question_shown")
    assert event.question_id == s["questions"][1].id and event.timestamp < datetime.utcnow()


async def test_assignment_opened_derives_its_references_from_the_assignment(client, scene, db_session):
    s = scene
    resp = await post(client, s["learner"], event_type="assignment_opened", payload={"assignment_id": str(s["assignment"].id)})
    assert resp.status_code == 201
    [event] = stored(db_session, s["learner"], "assignment_opened")
    assert (event.course_id, event.content_id) == (s["course"].id, s["lab_item"].id)
    assert (await post(client, s["learner"], event_type="assignment_opened", payload={"assignment_id": str(uuid.uuid4())})).status_code == 404
    assert (await post(client, s["learner"], event_type="assignment_opened", payload={"assignment_id": "x"})).status_code == 422


# ------------------------------------------------------------------------------------ batch
async def test_a_batch_is_recorded_together(client, scene, db_session):
    s = scene
    resp = await client.post(f"{EVENTS}/batch", headers=auth(s["learner"]), json={"events": [
        {"event_type": "lesson_opened", "content_id": str(s["video"].id)},
        {"event_type": "video_started", "content_id": str(s["video"].id), "payload": {"position_seconds": 0}},
        {"event_type": "article_opened", "content_id": str(s["article"].id)},
    ]})
    assert resp.status_code == 201 and resp.json()["count"] == 3
    assert {e.session_id for e in stored(db_session, s["learner"]) if e.event_type != "session_started"} == \
           {stored(db_session, s["learner"], "session_started")[0].session_id}


async def test_one_bad_event_rejects_the_whole_batch_and_names_it(client, scene, db_session):
    s = scene
    resp = await client.post(f"{EVENTS}/batch", headers=auth(s["learner"]), json={"events": [
        {"event_type": "lesson_opened", "content_id": str(s["video"].id)},
        {"event_type": "question_answered", "question_id": str(s["questions"][0].id)},
    ]})
    assert resp.status_code == 403 and resp.json()["detail"]["index"] == 1
    assert stored(db_session, s["learner"]) == []


async def test_batches_are_bounded(client, scene):
    events = [{"event_type": "lesson_opened", "content_id": str(scene["video"].id)}] * 51
    assert (await client.post(f"{EVENTS}/batch", headers=auth(scene["learner"]), json={"events": events})).status_code == 422
    assert (await client.post(f"{EVENTS}/batch", headers=auth(scene["learner"]), json={"events": []})).status_code == 422


async def test_batch_keys_make_a_retried_batch_harmless(client, scene, db_session):
    s = scene
    body = {"events": [{"event_type": "lesson_opened", "content_id": str(s["video"].id), "idempotency_key": "b-1"},
                       {"event_type": "article_opened", "content_id": str(s["article"].id), "idempotency_key": "b-2"}]}
    first = await client.post(f"{EVENTS}/batch", headers=auth(s["learner"]), json=body)
    again = await client.post(f"{EVENTS}/batch", headers=auth(s["learner"]), json=body)
    assert [e["status"] for e in first.json()["events"]] == ["ingested", "ingested"]
    assert [e["status"] for e in again.json()["events"]] == ["duplicate_ignored", "duplicate_ignored"]
    assert len(stored(db_session, s["learner"], "lesson_opened")) == 1


# ==================================================================================== queries
@pytest.fixture
def busy(client, scene, db_session):
    """A learner with a spread of events across items and time."""
    s = scene
    base = datetime.utcnow() - timedelta(hours=3)
    rows = []
    for i in range(7):
        item = s["video"] if i % 2 == 0 else s["article"]
        rows.append(LearningEvent(
            id=uuid.uuid4(), org_id=s["org"].id, user_id=s["learner"].id, course_id=s["course"].id, module_id=s["module"].id,
            content_id=item.id, event_type="lesson_opened" if i % 3 else "content_started", payload={"n": i},
            timestamp=base + timedelta(minutes=10 * i),
        ))
    db_session.add_all(rows)
    db_session.commit()
    return rows


async def ids(client, user, **params):
    body = (await client.get(EVENTS, params=params, headers=auth(user))).json()
    return [e["id"] for e in body["items"]], body["next_cursor"]


async def test_events_can_be_filtered_by_each_reference(client, scene, busy):
    s = scene
    mine = {str(r.id) for r in busy}
    video = {str(r.id) for r in busy if r.content_id == s["video"].id}
    got = set(await ids_only(client, s["learner"], content_id=str(s["video"].id), limit=200))
    assert video <= got and not ((mine - video) & got)                       # the video's events, and none of the article's
    assert mine <= set(await ids_only(client, s["learner"], course_id=str(s["course"].id), limit=200))
    for params in ({"course_id": uuid.uuid4()}, {"module_id": uuid.uuid4()}, {"content_id": uuid.uuid4()},
                   {"competency_id": s["competency"].id}, {"session_id": uuid.uuid4()}, {"question_id": uuid.uuid4()}, {"assessment_id": uuid.uuid4()}):
        assert await ids_only(client, s["learner"], **{k: str(v) for k, v in params.items()}) == []


async def ids_only(client, user, **params):
    return (await ids(client, user, **params))[0]


async def test_event_types_can_be_combined_and_legacy_names_work(client, scene, busy):
    s = scene
    types = lambda rows: {e["event_type"] for e in rows}
    body = (await client.get(EVENTS, params={"event_type": ["lesson_opened", "content_started"], "limit": 200}, headers=auth(s["learner"]))).json()
    assert types(body["items"]) == {"lesson_opened", "content_started"}
    only = (await client.get(EVENTS, params={"event_type": "content_started", "limit": 200}, headers=auth(s["learner"]))).json()
    assert types(only["items"]) == {"content_started"}
    legacy = (await client.get(EVENTS, params={"event_type": "question_viewed"}, headers=auth(s["learner"]))).json()
    assert legacy["items"] == []


async def test_events_can_be_limited_to_a_time_window(client, scene, busy):
    s = scene
    lo, hi = busy[2].timestamp, busy[5].timestamp
    window = await ids_only(client, s["learner"], since=lo.isoformat(), until=hi.isoformat(), limit=200)
    mine = {str(r.id) for r in busy if lo <= r.timestamp < hi}
    assert mine <= set(window) and str(busy[5].id) not in window and str(busy[1].id) not in window


async def test_pagination_neither_repeats_nor_skips_events_even_with_equal_timestamps(client, scene, db_session):
    s = scene
    same = datetime.utcnow() - timedelta(days=1)
    db_session.add_all([LearningEvent(id=uuid.uuid4(), org_id=s["org"].id, user_id=s["learner"].id, course_id=s["course"].id,
                                      content_id=s["video"].id, event_type="lesson_opened", payload={"n": i}, timestamp=same) for i in range(11)])
    db_session.commit()

    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 4, "content_id": str(s["video"].id)}
        if cursor:
            params["cursor"] = cursor
        body = (await client.get(EVENTS, params=params, headers=auth(s["learner"]))).json()
        seen += [e["id"] for e in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 11 and pages == 3


async def test_pagination_is_stable_while_new_events_arrive(client, scene, db_session, busy):
    s = scene
    first = (await client.get(EVENTS, params={"limit": 3}, headers=auth(s["learner"]))).json()
    await post(client, s["learner"], event_type="article_opened", content_id=str(s["article"].id))     # arrives mid-paging
    second = (await client.get(EVENTS, params={"limit": 3, "cursor": first["next_cursor"]}, headers=auth(s["learner"]))).json()
    assert not ({e["id"] for e in first["items"]} & {e["id"] for e in second["items"]})


async def test_ascending_order_and_bad_cursors(client, scene, busy):
    s = scene
    asc = (await client.get(EVENTS, params={"order": "asc", "content_id": str(s["video"].id), "limit": 200}, headers=auth(s["learner"]))).json()["items"]
    stamps = [e["timestamp"] for e in asc]
    assert stamps == sorted(stamps)
    assert (await client.get(EVENTS, params={"cursor": "garbage"}, headers=auth(s["learner"]))).status_code == 422
    assert (await client.get(EVENTS, params={"order": "sideways"}, headers=auth(s["learner"]))).status_code == 422
    assert (await client.get(EVENTS, params={"limit": 1000}, headers=auth(s["learner"]))).status_code == 422


async def test_one_event_can_be_fetched_by_id(client, scene, busy):
    s = scene
    one = (await client.get(f"{EVENTS}/{busy[3].id}", headers=auth(s["learner"]))).json()
    assert one["id"] == str(busy[3].id) and one["payload"] == {"n": 3} and one["received_at"]
    assert (await client.get(f"{EVENTS}/{uuid.uuid4()}", headers=auth(s["learner"]))).status_code == 404


# ---------------------------------------------------------------------------------- visibility
async def test_a_learner_sees_only_their_own_events_whatever_they_ask_for(client, scene, busy, db_session):
    s = scene
    peer = make_user(db_session, s["org"], ["learner"])
    db_session.commit()
    await post(client, peer, event_type="lesson_opened", content_id=str(s["video"].id))
    listing = (await client.get(EVENTS, params={"limit": 200}, headers=auth(s["learner"]))).json()["items"]
    assert listing and {e["user_id"] for e in listing} == {str(s["learner"].id)}
    assert await ids_only(client, s["learner"], user_id=str(peer.id)) == []
    peer_event = stored(db_session, peer, "lesson_opened")[0]
    assert (await client.get(f"{EVENTS}/{peer_event.id}", headers=auth(s["learner"]))).status_code == 404


async def test_a_manager_sees_their_teams_events_only(client, scene, busy, db_session):
    s = scene
    manager = make_user(db_session, s["org"], ["manager"])
    stranger = make_user(db_session, s["org"], ["learner"])
    team = Team(id=uuid.uuid4(), org_id=s["org"].id, name="T", manager_id=manager.id)
    db_session.add(team)
    db_session.flush()
    db_session.add(UserTeam(user_id=s["learner"].id, team_id=team.id, org_id=s["org"].id))
    db_session.commit()
    await post(client, stranger, event_type="lesson_opened", content_id=str(s["video"].id))

    seen = (await client.get(EVENTS, params={"limit": 200}, headers=auth(manager))).json()["items"]
    users = {e["user_id"] for e in seen}
    assert str(s["learner"].id) in users and str(stranger.id) not in users
    assert await ids_only(client, manager, user_id=str(stranger.id)) == []


async def test_l_and_d_and_org_admins_see_everyone_in_their_tenant(client, scene, busy, db_session):
    s = scene
    org_admin = make_user(db_session, s["org"], ["org_admin"])
    other = make_user(db_session, s["org"], ["learner"])
    db_session.commit()
    await post(client, other, event_type="lesson_opened", content_id=str(s["video"].id))
    for admin in (s["ld"], org_admin):
        users = {e["user_id"] for e in (await client.get(EVENTS, params={"limit": 200}, headers=auth(admin))).json()["items"]}
        assert {str(s["learner"].id), str(other.id)} <= users


# ------------------------------------------------------------------------------------- stats
async def test_stats_count_by_type_and_day_for_what_the_viewer_may_see(client, scene, busy, db_session):
    s = scene
    stats = (await client.get(f"{EVENTS}/stats", headers=auth(s["ld"]))).json()
    assert stats["total_events"] == sum(stats["breakdown"].values())
    assert stats["breakdown"]["lesson_opened"] >= 4 and stats["learners"] >= 1 and stats["by_day"]
    assert sum(d["count"] for d in stats["by_day"]) == stats["total_events"]
    scoped = (await client.get(f"{EVENTS}/stats", params={"event_type": "content_started"}, headers=auth(s["ld"]))).json()
    assert set(scoped["breakdown"]) == {"content_started"}


async def test_the_session_count_matches_the_sessions_list(client, scene, db_session):
    s = scene
    before = (await client.get(f"{EVENTS}/stats", params={"course_id": str(s["course"].id)}, headers=auth(s["ld"]))).json()["sessions"]
    assert before == 0
    await client.post(f"{SESSIONS}/start", json={"course_id": str(s["course"].id)}, headers=auth(s["learner"]))
    stats = (await client.get(f"{EVENTS}/stats", params={"course_id": str(s["course"].id)}, headers=auth(s["ld"]))).json()
    listed = (await client.get(SESSIONS, params={"course_id": str(s["course"].id)}, headers=auth(s["ld"]))).json()["items"]
    assert stats["sessions"] == len(listed) == 1


async def test_learners_cannot_read_stats(client, scene):
    assert (await client.get(f"{EVENTS}/stats", headers=auth(scene["learner"]))).status_code == 403


async def test_manager_stats_cover_only_their_team(client, scene, busy, db_session):
    s = scene
    manager = make_user(db_session, s["org"], ["manager"])
    db_session.commit()
    stats = (await client.get(f"{EVENTS}/stats", headers=auth(manager))).json()
    assert stats["total_events"] == 0        # a manager with no team sees no learners' events


async def test_unauthenticated_requests_are_refused(client, scene):
    for path in ("", "/stats", f"/{uuid.uuid4()}"):
        assert (await client.get(f"{EVENTS}{path}")).status_code == 401
    assert (await client.post(EVENTS, json={"event_type": "lesson_opened"})).status_code == 401
