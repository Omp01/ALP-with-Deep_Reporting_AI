"""
The events the server itself records as a learner works: progress, quiz attempts (with the
per-answer evidence of spec section 17), assignments. These are facts the browser cannot
claim, so they are recorded where they are established.
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models import EventOutbox, LearningEvent, LearningSession, QuestionResponse
from tests.foundation.conftest import (
    API, auth, enroll, make_assignment, make_competency, make_course, make_item, make_org, make_quiz, make_user, only_module,
)

pytestmark = pytest.mark.integration


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
    quiz, built = make_quiz(db_session, org, course, module, quiz_item, questions=3, competency=competency)
    built[0][0].difficulty = 0.3          # the second and third are deliberately left unrated
    lab_item = make_item(db_session, org, course, module, content_type="ASSIGNMENT", order_index=3)
    assignment = make_assignment(db_session, org, course, module, lab_item)
    enroll(db_session, org, learner, course)
    db_session.commit()
    return dict(org=org, ld=ld, learner=learner, course=course, module=module, video=video, article=article, competency=competency,
                quiz=quiz, quiz_item=quiz_item, built=built, assignment=assignment, lab_item=lab_item)


def events(db_session, user, *kinds, **filters):
    db_session.expire_all()
    query = db_session.query(LearningEvent).filter_by(user_id=user.id, **filters)
    if kinds:
        query = query.filter(LearningEvent.event_type.in_(kinds))
    return query.order_by(LearningEvent.timestamp, LearningEvent.id).all()


async def report(client, user, item, **body):
    return await client.post(f"{API}/progress/content/{item.id}", json=body, headers=auth(user))


async def begin(client, s):
    return (await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts", headers=auth(s["learner"]))).json()


def backdate_attempt(db_session, attempt_id, seconds):
    db_session.execute(text("UPDATE quiz_attempts SET started_at = :t WHERE id = :i"),
                       {"t": datetime.utcnow() - timedelta(seconds=seconds), "i": attempt_id})
    db_session.commit()


def answers(s, picks, times=None):
    body = []
    for index, (question, options) in enumerate(s["built"]):
        entry = {"question_id": str(question.id)}
        if picks[index] is not None:
            entry["selected_option_id"] = str(options[picks[index]].id)
        if times and times[index] is not None:
            entry["response_time_ms"] = times[index]
        body.append(entry)
    return {"responses": body}


# ======================================================================================= progress
async def test_watching_a_video_to_the_end_records_a_started_completed_and_typed_completion(client, scene, db_session):
    s = scene
    await report(client, s["learner"], s["video"], status="in_progress", progress_percent=10, time_spent_seconds=5)
    await report(client, s["learner"], s["video"], status="completed", progress_percent=100, time_spent_seconds=5)

    started, completed, typed = (events(db_session, s["learner"], k, content_id=s["video"].id)[0] for k in ("content_started", "content_completed", "video_completed"))
    assert (started.timestamp < completed.timestamp < typed.timestamp)
    assert typed.payload["derived_from"] == str(completed.id) and typed.payload["content_type"] == "VIDEO"
    assert len({started.session_id, completed.session_id, typed.session_id}) == 1 and started.session_id is not None
    assert (typed.course_id, typed.module_id) == (s["course"].id, s["module"].id)


async def test_reading_an_article_records_article_completed(client, scene, db_session):
    s = scene
    await report(client, s["learner"], s["article"], status="completed", progress_percent=100, time_spent_seconds=30)
    typed = events(db_session, s["learner"], "article_completed")
    assert len(typed) == 1 and typed[0].payload["derived_from"] == str(events(db_session, s["learner"], "content_completed")[0].id)


async def test_completion_is_recorded_once_however_often_it_is_reported(client, scene, db_session):
    s = scene
    for _ in range(3):
        await report(client, s["learner"], s["video"], status="completed", progress_percent=100)
    for kind in ("content_started", "content_completed", "video_completed"):
        assert len(events(db_session, s["learner"], kind)) == 1


async def test_a_learner_cannot_complete_a_quiz_through_progress_and_no_completion_event_appears(client, scene, db_session):
    s = scene
    await report(client, s["learner"], s["quiz_item"], status="completed", progress_percent=100)
    assert events(db_session, s["learner"], "content_completed") == []


# ======================================================================================= quizzes
async def test_starting_an_attempt_is_an_event_and_a_second_attempt_is_a_retry(client, scene, db_session):
    s = scene
    first = await begin(client, s)
    assert [e.event_type for e in events(db_session, s["learner"], "assessment_started", "retry_started")] == ["assessment_started"]

    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{first['id']}/submit", headers=auth(s["learner"]), json=answers(s, [0, 0, 0]))
    second = await begin(client, s)
    kinds = events(db_session, s["learner"], "assessment_started", "retry_started")
    assert [e.event_type for e in kinds] == ["assessment_started", "assessment_started", "retry_started"]
    retry = kinds[-1]
    assert retry.payload["attempt_number"] == 2 and retry.payload["attempt_id"] == second["id"] and retry.payload["previous_attempt_id"] == first["id"]
    assert (retry.assessment_id, retry.course_id, retry.content_id) == (s["quiz"].id, s["course"].id, s["quiz_item"].id)


async def test_every_answer_is_evidence_with_the_fields_the_spec_lists(client, scene, db_session):
    s = scene
    attempt = await begin(client, s)
    backdate_attempt(db_session, attempt["id"], 120)
    resp = await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]),
                             json=answers(s, [0, 1, None], times=[4_000, 3_000_000, None]))
    assert resp.status_code == 200

    answered = events(db_session, s["learner"], "question_answered")
    assert [e.question_id for e in answered] == [q.id for q, _ in s["built"]]           # in question order
    right, wrong, blank = answered

    for e in answered:
        assert (e.org_id, e.user_id, e.assessment_id, e.competency_id, e.course_id) == (s["org"].id, s["learner"].id, s["quiz"].id, s["competency"].id, s["course"].id)
        assert e.session_id is not None and e.payload["attempt_id"] == attempt["id"] and e.payload["attempt_number"] == 1
        assert e.payload["question_type"] == "multiple_choice"

    assert right.payload["is_correct"] is True and right.payload["error_type"] is None and right.payload["points_awarded"] == 10.0
    assert right.payload["selected_option_id"] == str(s["built"][0][1][0].id) and right.payload["answered"] is True
    assert right.payload["difficulty"] == 0.3
    assert (right.payload["response_time_ms"], right.payload["response_time_source"]) == (4_000, "client")

    assert wrong.payload["is_correct"] is False and wrong.payload["error_type"] == "unknown" and wrong.payload["points_awarded"] == 0.0
    assert wrong.payload["difficulty"] is None                                             # unrated stays unknown, not "medium"
    assert wrong.payload["response_time_source"] == "client_clamped" and 110_000 <= wrong.payload["response_time_ms"] <= 130_000

    assert blank.payload["answered"] is False and blank.payload["selected_option_id"] is None and blank.payload["is_correct"] is False
    assert blank.payload["response_time_ms"] is None and blank.payload["response_time_source"] is None


async def test_the_answer_rows_hold_the_same_evidence(client, scene, db_session):
    s = scene
    attempt = await begin(client, s)
    backdate_attempt(db_session, attempt["id"], 60)
    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]), json=answers(s, [0, 1, 0], times=[2_500, 3_000, None]))
    rows = {r.question_id: r for r in db_session.query(QuestionResponse).filter_by(attempt_id=uuid.UUID(attempt["id"]))}
    first, second, third = (rows[q.id] for q, _ in s["built"])
    assert (first.is_correct, first.response_time_ms, first.response_time_source, first.error_type) == (True, 2_500, "client", None)
    assert (second.is_correct, second.error_type, second.response_time_ms) == (False, "unknown", 3_000)
    assert (third.response_time_ms, third.response_time_source) == (None, None)


async def test_the_assessment_completion_event_carries_the_result(client, scene, db_session):
    s = scene
    attempt = await begin(client, s)
    backdate_attempt(db_session, attempt["id"], 90)
    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]), json=answers(s, [0, 0, 1]))
    [done] = events(db_session, s["learner"], "assessment_completed")
    assert done.assessment_id == s["quiz"].id and done.payload["attempt_id"] == attempt["id"]
    assert (done.payload["score"], done.payload["passed"], done.payload["earned_points"], done.payload["total_points"]) == (66.7, False, 20.0, 30.0)
    assert 85 <= done.payload["duration_seconds"] <= 100
    assert done.timestamp > events(db_session, s["learner"], "question_answered")[-1].timestamp


async def test_a_whole_quiz_sits_in_one_session_in_order(client, scene, db_session):
    s = scene
    attempt = await begin(client, s)
    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]), json=answers(s, [0, 0, 0]))
    trail = events(db_session, s["learner"])
    assert [e.event_type for e in trail if e.event_type != "content_started"][:1] == ["session_started"]
    kinds = [e.event_type for e in trail]
    assert kinds.index("assessment_started") < kinds.index("question_answered") < kinds.index("assessment_completed")
    assert len({e.session_id for e in trail}) == 1 and db_session.query(LearningSession).filter_by(user_id=s["learner"].id).count() == 1


async def test_a_passing_attempt_also_completes_the_lesson_within_the_same_session(client, scene, db_session):
    s = scene
    attempt = await begin(client, s)
    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]), json=answers(s, [0, 0, 0]))
    completed = events(db_session, s["learner"], "content_completed", content_id=s["quiz_item"].id)
    assert len(completed) == 1 and completed[0].session_id == events(db_session, s["learner"], "assessment_completed")[0].session_id


async def test_client_response_times_cannot_be_negative_or_absurd(client, scene, db_session):
    s = scene
    attempt = await begin(client, s)
    for bad in (-1, 4_000_000):
        body = answers(s, [0, 0, 0])
        body["responses"][0]["response_time_ms"] = bad
        assert (await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]), json=body)).status_code == 422


# ===================================================================================== assignments
async def test_submitting_and_grading_an_assignment_are_events(client, scene, db_session):
    s = scene
    submitted = await client.post(f"{API}/assignments/{s['assignment'].id}/submit", headers=auth(s["learner"]), json={"submission_text": "my work"})
    assert submitted.status_code == 201
    [sub] = events(db_session, s["learner"], "assignment_submitted")
    assert sub.payload["assignment_id"] == str(s["assignment"].id) and sub.payload["submission_id"] == submitted.json()["id"]
    assert (sub.course_id, sub.content_id) == (s["course"].id, s["lab_item"].id) and sub.session_id is not None

    graded = await client.post(f"{API}/assignments/submissions/{submitted.json()['id']}/grade", headers=auth(s["ld"]),
                               json={"score": 88.0, "feedback": "Good", "rubric_scores": {"correctness": 88}})
    assert graded.status_code == 200
    [grade] = events(db_session, s["learner"], "assignment_graded")
    assert grade.user_id == s["learner"].id                                    # evidence about the LEARNER
    assert grade.payload["graded_by"] == str(s["ld"].id) and grade.payload["score"] == 88.0 and grade.payload["max_score"] == 100.0
    assert grade.session_id is None                                            # the learner was not there
    assert events(db_session, s["ld"]) == []                                   # and the grader gains no learning events


# ========================================================================================= outbox
async def test_the_server_recorded_facts_are_queued_for_the_stream_except_held_back_ones(client, scene, db_session):
    s = scene
    await report(client, s["learner"], s["video"], status="completed", progress_percent=100)
    attempt = await begin(client, s)
    await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]), json=answers(s, [0, 0, 0]))
    await client.post(f"{API}/assignments/{s['assignment'].id}/submit", headers=auth(s["learner"]), json={"submission_text": "x"})

    queued = {e.event_type for e in events(db_session, s["learner"]) if db_session.get(EventOutbox, e.id) is not None}
    stored_kinds = {e.event_type for e in events(db_session, s["learner"])}
    assert {"content_completed", "assessment_started", "assessment_completed", "session_started"} <= queued
    assert {"question_answered", "assignment_submitted"} <= stored_kinds and not ({"question_answered", "assignment_submitted"} & queued)


async def test_nothing_is_published_synchronously_so_a_stream_outage_cannot_fail_a_request(client, scene, monkeypatch, db_session):
    from app.core.events import event_publisher

    async def boom(_):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(event_publisher, "publish_event", boom)
    s = scene
    resp = await report(client, s["learner"], s["video"], status="completed", progress_percent=100)
    assert resp.status_code == 200 and events(db_session, s["learner"], "content_completed")


# ================================================================================ content deletion
async def test_content_with_learner_activity_cannot_be_deleted(client, scene, db_session):
    s = scene
    await report(client, s["learner"], s["article"], status="in_progress", progress_percent=5)
    s["article"].status = "review"
    db_session.commit()
    resp = await client.delete(f"{API}/admin/content/{s['article'].id}", headers=auth(s["ld"]))
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "has_learner_activity"
    assert events(db_session, s["learner"], "content_started", content_id=s["article"].id)


async def test_content_without_activity_can_still_be_deleted(client, scene, db_session):
    s = scene
    fresh = make_item(db_session, s["org"], s["course"], s["module"], content_type="ARTICLE", status="review", order_index=9)
    db_session.commit()
    assert (await client.delete(f"{API}/admin/content/{fresh.id}", headers=auth(s["ld"]))).status_code == 204
