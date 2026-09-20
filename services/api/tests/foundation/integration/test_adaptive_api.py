"""
Adaptation inside one session, through the real API: the next step changes as the learner's evidence changes, every decision is
stored with the facts it used, and nothing about it can be asked on behalf of somebody else.
"""

import uuid

import pytest

from app.models import AdaptiveDecision, ContentCompetency, CourseCompetency, LearningEvent
from tests.foundation.conftest import (
    API, auth, enroll, make_competency, make_course, make_item, make_org, make_quiz, make_user, only_module,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    manager = make_user(db_session, org, ["manager"])
    learner = make_user(db_session, org, ["learner"])
    other = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    comp = make_competency(db_session, org, f"sql.joins.{uuid.uuid4().hex[:6]}")
    db_session.add(CourseCompetency(course_id=course.id, competency_id=comp.id, target_mastery=0.7))
    lesson = make_item(db_session, org, course, module, content_type="ARTICLE", order_index=0, title="Joins explained")
    lesson2 = make_item(db_session, org, course, module, content_type="ARTICLE", order_index=1, title="Joins worked examples")
    for item in (lesson, lesson2):
        db_session.add(ContentCompetency(content_item_id=item.id, competency_id=comp.id, weight=1.0))
    quiz_item = make_item(db_session, org, course, module, content_type="QUIZ", order_index=2, title="Joins quiz")
    quiz, built = make_quiz(db_session, org, course, module, quiz_item, questions=3, competency=comp)
    for question, _ in built:
        question.difficulty = 0.5
    enroll(db_session, org, learner, course)
    enroll(db_session, org, other, course)
    db_session.commit()
    return dict(org=org, ld=ld, manager=manager, learner=learner, other=other, course=course, comp=comp, lesson=lesson, lesson2=lesson2, quiz=quiz, built=built, quiz_item=quiz_item)


async def next_step(client, s, user=None, **body):
    resp = await client.post(f"{API}/adaptive/next", headers=auth(user or s["learner"]), json={"course_id": str(s["course"].id), "competency_id": str(s["comp"].id), **body})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def answer(client, s, correct: bool):
    attempt = (await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts", headers=auth(s["learner"]))).json()
    body = {"responses": [{"question_id": str(q.id), "selected_option_id": str(options[0 if correct else 1].id)} for q, options in s["built"]]}
    assert (await client.post(f"{API}/quizzes/{s['quiz'].id}/attempts/{attempt['id']}/submit", headers=auth(s["learner"]), json=body)).status_code == 200


async def complete(client, s, item):
    resp = await client.post(f"{API}/progress/content/{item.id}", headers=auth(s["learner"]), json={"status": "completed", "time_spent_seconds": 60})
    assert resp.status_code == 200, resp.text


async def test_the_next_step_adapts_to_the_learner_inside_one_session(client, scene, db_session):
    s = scene
    first = await next_step(client, s)
    assert (first["action"], first["rule"], first["content"]["title"]) == ("CONTINUE", "no_evidence_learn", "Joins explained")
    await complete(client, s, s["lesson"])
    second = await next_step(client, s)
    assert (second["action"], second["content"]["title"]) == ("ASSESS", "Joins quiz")

    await answer(client, s, correct=False)
    third = await next_step(client, s)
    assert (third["action"], third["rule"], third["content"]["title"]) == ("REMEDIATE", "struggling", "Joins worked examples")
    assert any("of your last 3 answers were incorrect" in line for line in third["why"]["evidence"])
    assert third["why"]["mastery"] < 0.5 and third["why"]["evidence_ids"]

    await complete(client, s, s["lesson2"])
    fourth = await next_step(client, s)
    assert (fourth["action"], fourth["rule"], fourth["content"]["title"]) == ("ASSESS", "reassess_after_content", "Joins quiz")
    assert "Joins worked examples" in fourth["reason"]

    for _ in range(2):
        await answer(client, s, correct=True)
    fifth = await next_step(client, s)
    assert fifth["action"] in ("CONTINUE", "HARDER", "SKIP") and fifth["why"]["mastery"] > third["why"]["mastery"]

    # the same session, and every decision stored with what it used
    db_session.expire_all()
    rows = db_session.query(AdaptiveDecision).filter_by(user_id=s["learner"].id).order_by(AdaptiveDecision.created_at).all()
    assert [r.decision_type for r in rows][:4] == ["continue", "assess", "remediate", "assess"]
    assert rows[2].rule_applied == "struggling" and rows[2].decision_metadata["facts"] and rows[2].decision_metadata["content"]["title"] == "Joins worked examples"
    events = db_session.query(LearningEvent).filter_by(user_id=s["learner"].id, event_type="adaptive_decision_made").all()
    assert len(events) == 5 and len({e.session_id for e in events}) == 1 and all(e.payload["decision_id"] for e in events)


async def test_decisions_can_be_read_back_with_their_facts(client, scene):
    s = scene
    await next_step(client, s)
    mine = (await client.get(f"{API}/adaptive/decisions/{s['learner'].id}", headers=auth(s["learner"]))).json()
    assert mine[0]["action"] == "CONTINUE" and mine[0]["rule"] == "no_evidence_learn" and mine[0]["content"]["title"] == "Joins explained"


async def test_visibility_of_decisions(client, scene):
    s = scene
    await next_step(client, s)
    assert (await client.get(f"{API}/adaptive/decisions/{s['learner'].id}", headers=auth(s["other"]))).status_code == 404
    assert (await client.get(f"{API}/adaptive/decisions/{s['learner'].id}", headers=auth(s["ld"]))).status_code == 200
    assert (await client.get(f"{API}/adaptive/decisions/{s['learner'].id}", headers=auth(s["manager"]))).status_code == 404       # not on the manager's team


async def test_another_tenant_cannot_use_this_course_or_competency(client, scene, db_session):
    s = scene
    foreign = make_user(db_session, make_org(db_session), ["learner"])
    db_session.commit()
    resp = await client.post(f"{API}/adaptive/next", headers=auth(foreign), json={"course_id": str(s["course"].id)})
    assert resp.status_code == 400
    resp = await client.post(f"{API}/adaptive/next", headers=auth(foreign), json={"competency_id": str(s["comp"].id)})
    assert resp.status_code in (400, 422)
    assert (await client.get(f"{API}/adaptive/decisions/{s['learner'].id}", headers=auth(foreign))).status_code == 404


async def test_a_request_cannot_name_another_learner(client, scene):
    s = scene
    result = await next_step(client, s, user=s["other"], learner_id=str(s["learner"].id))      # the field does not exist: the caller is who is decided for
    assert result["why"]["mastery"] is None


async def test_a_course_without_competencies_says_so(client, scene, db_session):
    s = scene
    empty = make_course(db_session, s["org"], s["ld"], content_seconds=[])
    enroll(db_session, s["org"], s["learner"], empty)
    db_session.commit()
    resp = await client.post(f"{API}/adaptive/next", headers=auth(s["learner"]), json={"course_id": str(empty.id)})
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "no_competency"
