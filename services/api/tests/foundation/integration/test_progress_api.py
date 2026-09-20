"""
Progress: derived, server-verified where it matters, and honest about time.

The rules under test (see app/services/progress.py):
  * course progress is completed/published lesson items, derived from stored rows;
  * a client cannot complete a quiz or an assignment;
  * time credited never exceeds real elapsed time;
  * completion is recorded once, as one `content_completed` event.
"""

import pytest

from app.models import ContentProgress, Enrollment, LearningEvent
from tests.foundation.conftest import (
    API, auth, enroll, make_assignment, make_competency, make_course, make_item, make_org, make_quiz,
    make_user, only_module,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    items = [make_item(db_session, org, course, module, content_type="VIDEO", order_index=i, seconds=600) for i in range(3)]
    enrollment = enroll(db_session, org, learner, course)
    db_session.commit()
    return org, ld, learner, course, module, items, enrollment


async def report(client, learner, item, *, status="in_progress", percent=0.0, seconds=0, position=None):
    body = {"status": status, "progress_percent": percent, "time_spent_seconds": seconds}
    if position is not None:
        body["position_seconds"] = position
    return await client.post(f"{API}/progress/content/{item.id}", json=body, headers=auth(learner))


async def test_first_report_creates_a_record_and_a_content_started_event(client, scene, db_session):
    org, _, learner, _, _, items, _ = scene
    resp = await report(client, learner, items[0], percent=10, seconds=5, position=42)
    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["progress_percent"], body["position_seconds"]) == ("in_progress", 10.0, 42)

    events = db_session.query(LearningEvent).filter_by(user_id=learner.id, content_id=items[0].id).all()
    assert [e.event_type for e in events] == ["content_started"]
    assert events[0].org_id == org.id and events[0].course_id == items[0].course_id


async def test_progress_percent_never_goes_backwards(client, scene):
    _, _, learner, _, _, items, _ = scene
    await report(client, learner, items[0], percent=60)
    body = (await report(client, learner, items[0], percent=20)).json()
    assert body["progress_percent"] == 60.0


async def test_reaching_the_threshold_completes_once_and_emits_one_event(client, scene, db_session):
    _, _, learner, _, _, items, _ = scene
    first = (await report(client, learner, items[0], percent=95)).json()
    assert (first["status"], first["progress_percent"]) == ("completed", 100.0)
    again = (await report(client, learner, items[0], percent=95)).json()
    assert again["status"] == "completed"

    completed = db_session.query(LearningEvent).filter_by(content_id=items[0].id, event_type="content_completed").count()
    assert completed == 1


async def test_completed_stays_completed_when_the_learner_rewatches(client, scene):
    _, _, learner, _, _, items, _ = scene
    await report(client, learner, items[0], status="completed", percent=100)
    body = (await report(client, learner, items[0], percent=5)).json()
    assert (body["status"], body["progress_percent"]) == ("completed", 100.0)


async def test_time_credit_is_capped_per_report_and_by_real_elapsed_time(client, scene):
    _, _, learner, _, _, items, _ = scene
    first = (await report(client, learner, items[0], percent=1, seconds=3600)).json()
    assert first["time_spent_seconds"] == 60            # heartbeat cap, however much is claimed
    second = (await report(client, learner, items[0], percent=2, seconds=60)).json()
    assert second["time_spent_seconds"] <= 61            # the second report came milliseconds later


async def test_client_cannot_complete_a_quiz_or_assignment(client, db_session, scene):
    org, _, learner, course, module, _, _ = scene
    quiz_item = make_item(db_session, org, course, module, content_type="QUIZ", order_index=5)
    lab_item = make_item(db_session, org, course, module, content_type="ASSIGNMENT", order_index=6)
    db_session.commit()
    for item in (quiz_item, lab_item):
        body = (await report(client, learner, item, status="completed", percent=100)).json()
        assert body["status"] != "completed", item.content_type
        assert body["progress_percent"] < 90


async def test_course_progress_is_derived_and_syncs_the_enrollment(client, scene, db_session):
    _, _, learner, course, _, items, enrollment = scene
    await report(client, learner, items[0], status="completed", percent=100)
    await report(client, learner, items[1], status="completed", percent=100)

    summary = (await client.get(f"{API}/progress/course/{course.id}", headers=auth(learner))).json()
    assert (summary["total_items"], summary["completed_items"], summary["progress_percent"]) == (3, 2, 66.7)
    assert set(summary["items_progress"]) == {str(items[0].id), str(items[1].id)}

    db_session.expire_all()
    assert db_session.get(Enrollment, enrollment.id).progress_pct == 66.7
    assert db_session.get(Enrollment, enrollment.id).status == "active"

    await report(client, learner, items[2], status="completed", percent=100)
    db_session.expire_all()
    done = db_session.get(Enrollment, enrollment.id)
    assert (done.progress_pct, done.status) == (100.0, "completed") and done.completed_at is not None


async def test_unpublished_items_do_not_count_and_cannot_be_reported(client, scene, db_session):
    org, ld, learner, course, module, items, _ = scene
    draft = make_item(db_session, org, course, module, status="draft", order_index=9)
    db_session.commit()

    assert (await report(client, learner, draft, percent=50)).status_code == 404
    await report(client, learner, items[0], status="completed", percent=100)
    summary = (await client.get(f"{API}/progress/course/{course.id}", headers=auth(learner))).json()
    assert summary["total_items"] == 3  # the draft is not in the denominator


async def test_progress_falls_back_when_new_content_is_published_after_completion(client, scene, db_session):
    org, _, learner, course, module, items, enrollment = scene
    for item in items:
        await report(client, learner, item, status="completed", percent=100)
    db_session.expire_all()
    assert db_session.get(Enrollment, enrollment.id).status == "completed"

    fresh = make_item(db_session, org, course, module, order_index=10)
    db_session.commit()
    await report(client, learner, fresh, percent=10)
    db_session.expire_all()
    reopened = db_session.get(Enrollment, enrollment.id)
    assert (reopened.status, reopened.progress_pct) == ("active", 75.0) and reopened.completed_at is None


async def test_progress_rows_are_tenant_owned(client, scene, db_session):
    org, _, learner, _, _, items, _ = scene
    await report(client, learner, items[0], percent=10)
    row = db_session.query(ContentProgress).filter_by(user_id=learner.id).one()
    assert row.org_id == org.id


async def test_one_progress_row_per_learner_per_item(client, scene, db_session):
    _, _, learner, _, _, items, _ = scene
    for percent in (10, 20, 30):
        await report(client, learner, items[0], percent=percent)
    assert db_session.query(ContentProgress).filter_by(user_id=learner.id, content_item_id=items[0].id).count() == 1


# --- quizzes and assignments complete the lesson item server-side ------------------------------
async def _take_quiz(client, learner, quiz, questions, *, answer_correctly: bool):
    attempt = (await client.post(f"{API}/quizzes/{quiz.id}/attempts", headers=auth(learner))).json()
    responses = [
        {"question_id": str(q.id), "selected_option_id": str((options[0] if answer_correctly else options[1]).id)}
        for q, options in questions
    ]
    return await client.post(
        f"{API}/quizzes/{quiz.id}/attempts/{attempt['id']}/submit", json={"responses": responses}, headers=auth(learner)
    )


async def test_passing_a_quiz_completes_its_lesson_item(client, scene, db_session):
    org, _, learner, course, module, _, _ = scene
    item = make_item(db_session, org, course, module, content_type="QUIZ", order_index=7)
    quiz, questions = make_quiz(db_session, org, course, module, item)
    db_session.commit()

    resp = await _take_quiz(client, learner, quiz, questions, answer_correctly=True)
    assert resp.status_code == 200 and resp.json()["passed"] is True

    db_session.expire_all()
    row = db_session.query(ContentProgress).filter_by(user_id=learner.id, content_item_id=item.id).one()
    assert row.status == "completed"
    assert row.org_id == org.id
    # Time is what actually elapsed between starting and submitting, not the quiz's time limit.
    assert row.time_spent_seconds < 10 * 60


async def test_failing_a_quiz_does_not_complete_its_lesson_item(client, scene, db_session):
    org, _, learner, course, module, _, _ = scene
    item = make_item(db_session, org, course, module, content_type="QUIZ", order_index=7)
    quiz, questions = make_quiz(db_session, org, course, module, item, passing_score=100)
    db_session.commit()

    resp = await _take_quiz(client, learner, quiz, questions, answer_correctly=False)
    assert resp.json()["passed"] is False
    db_session.expire_all()
    row = db_session.query(ContentProgress).filter_by(user_id=learner.id, content_item_id=item.id).one()
    assert row.status == "in_progress"


async def test_a_quiz_completes_only_the_item_it_is_linked_to(client, scene, db_session):
    """Regression: the old handler guessed the item from the quiz title, or took 'the first quiz item'."""
    org, _, learner, course, module, _, _ = scene
    linked = make_item(db_session, org, course, module, content_type="QUIZ", order_index=7, title="Quiz A")
    other = make_item(db_session, org, course, module, content_type="QUIZ", order_index=8, title="Quiz A (copy)")
    quiz, questions = make_quiz(db_session, org, course, module, linked)
    db_session.commit()

    await _take_quiz(client, learner, quiz, questions, answer_correctly=True)
    db_session.expire_all()
    assert db_session.query(ContentProgress).filter_by(user_id=learner.id, content_item_id=other.id).count() == 0


async def test_submitting_an_assignment_completes_its_lesson_item(client, scene, db_session):
    org, _, learner, course, module, _, _ = scene
    item = make_item(db_session, org, course, module, content_type="ASSIGNMENT", order_index=8)
    assignment = make_assignment(db_session, org, course, module, item)
    db_session.commit()

    resp = await client.post(
        f"{API}/assignments/{assignment.id}/submit", json={"submission_text": "my work"}, headers=auth(learner)
    )
    assert resp.status_code == 201
    db_session.expire_all()
    row = db_session.query(ContentProgress).filter_by(user_id=learner.id, content_item_id=item.id).one()
    assert row.status == "completed"


# --- the old "set my progress" endpoint no longer lets anyone claim completion -----------------------
async def test_a_learner_cannot_declare_their_enrollment_complete(client, scene):
    _, _, learner, _, _, _, enrollment = scene
    resp = await client.put(
        f"{API}/enrollments/{enrollment.id}/progress", json={"progress_pct": 100.0, "status": "active"},
        headers=auth(learner),
    )
    assert resp.status_code == 200
    assert (resp.json()["progress_pct"], resp.json()["status"]) == (0.0, "active")


async def test_a_learner_cannot_mark_an_enrollment_completed_by_status(client, scene):
    _, _, learner, _, _, _, enrollment = scene
    resp = await client.put(
        f"/api/v1/enrollments/{enrollment.id}/progress", json={"status": "completed"}, headers=auth(learner)
    )
    assert resp.status_code == 422


async def test_only_the_enrolled_learner_can_change_an_enrollment(client, scene, db_session):
    org, ld, learner, _, _, _, enrollment = scene
    manager = make_user(db_session, org, ["manager"])
    db_session.commit()
    resp = await client.put(f"{API}/enrollments/{enrollment.id}/progress", json={"status": "dropped"}, headers=auth(manager))
    assert resp.status_code == 403


async def test_a_learner_can_drop_their_enrollment(client, scene):
    _, _, learner, _, _, _, enrollment = scene
    resp = await client.put(f"{API}/enrollments/{enrollment.id}/progress", json={"status": "dropped"}, headers=auth(learner))
    assert resp.status_code == 200 and resp.json()["status"] == "dropped"
