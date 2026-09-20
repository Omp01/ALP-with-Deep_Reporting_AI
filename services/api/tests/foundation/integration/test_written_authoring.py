"""
Authoring written questions and publishing them, then a learner answering one.

A reviewer can write a short-answer or open-ended question with an expected answer and a rubric. The publisher turns it into a
quiz question with no options; learners see the rubric but never the expected answer; and the answer is graded (by the grading
agent, or a person) into evidence for the competency.
"""

import pytest

from app.models import EvidenceRecord, QuestionCandidate, Quiz, QuizQuestion
from tests.foundation.conftest import API, auth, enroll, make_competency, make_course, make_org, make_user, only_module
from tests.foundation.fakes import PROSE, ScriptedAI

pytestmark = pytest.mark.integration

ADMIN = f"{API}/admin/content"
RUBRIC = [{"criterion": "Matching rows", "weight": 1.0, "description": "Says only rows with a match are kept"}]
EXPECTED = "An inner join keeps only the rows that have a matching value in both tables."


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    competency = make_competency(db_session, org, "sql.joins")
    enroll(db_session, org, learner, course)
    db_session.commit()
    return dict(org=org, ld=ld, learner=learner, course=course, module=module, competency=competency)


@pytest.fixture
async def content(client, ingestion_env, scene):
    ingestion_env.use_ai(ScriptedAI())
    resp = await client.post(f"{ADMIN}/ingest/file", files={"file": ("Joins.txt", PROSE.encode(), "text/plain")},
                             data={"module_id": str(scene["module"].id)}, headers=auth(scene["ld"]))
    assert resp.status_code == 202, resp.text
    return resp.json()["content_id"]


def written(competency=None, **overrides):
    body = {"question_text": "Explain what an inner join returns.", "question_type": "short_answer", "expected_answer": EXPECTED, "rubric": RUBRIC,
            "difficulty": 0.6}
    if competency is not None:
        body["competency_id"] = str(competency.id)
    body.update(overrides)
    return body


async def add(client, s, content, **body):
    return await client.post(f"{ADMIN}/{content}/candidates", json=body, headers=auth(s["ld"]))


# ============================================================================== creating
async def test_a_written_question_is_created_approved_with_its_answer_key_and_rubric(client, scene, content):
    resp = await add(client, scene, content, **written(scene["competency"]))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["question_type"] == "short_answer" and body["options"] == [] and body["status"] == "approved" and body["origin"] == "manual"
    assert body["expected_answer"] == EXPECTED and body["rubric"][0]["criterion"] == "Matching rows"


@pytest.mark.parametrize("overrides,reason", [
    ({"expected_answer": None, "rubric": None}, "expected answer or a rubric"),
    ({"options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": False}, {"text": "c", "is_correct": False}]}, "no options"),
    ({"rubric": [{"criterion": "Accuracy", "weight": 1}, {"criterion": "accuracy", "weight": 1}]}, "different from each other"),
    ({"rubric": []}, "1 to 8"),
    ({"question_type": "essay"}, ""),
])
async def test_a_written_question_must_be_gradable(client, scene, content, overrides, reason):
    resp = await add(client, scene, content, **written(scene["competency"], **overrides))
    assert resp.status_code == 422 and reason in resp.text


async def test_a_written_question_must_name_a_competency_because_its_answers_are_evidence_for_it(client, scene, content):
    resp = await add(client, scene, content, **written())
    assert resp.status_code == 422 and "competency" in resp.text
    assert (await add(client, scene, content, **written(competency_name="Join semantics"))).status_code == 201


async def test_a_multiple_choice_question_still_needs_valid_options_and_no_answer_key(client, scene, content):
    ok = {"question_text": "What does ON specify in a join?", "options": [{"text": "Match", "is_correct": True}, {"text": "Sort", "is_correct": False}, {"text": "Limit", "is_correct": False}]}
    assert (await add(client, scene, content, **ok)).status_code == 201
    assert (await add(client, scene, content, **{**ok, "options": ok["options"][:2]})).status_code == 422
    assert (await add(client, scene, content, **{**ok, "expected_answer": "x" * 20})).status_code == 422
    missing = {k: v for k, v in ok.items() if k != "options"}
    assert (await add(client, scene, content, **missing)).status_code == 422


async def test_another_tenant_cannot_author_on_this_content(client, scene, content, db_session):
    foreign_ld = make_user(db_session, make_org(db_session), ["ld_admin"])
    db_session.commit()
    assert (await client.post(f"{ADMIN}/{content}/candidates", json=written(scene["competency"]), headers=auth(foreign_ld))).status_code == 404


# ============================================================================== editing
async def test_a_written_question_can_be_edited_but_not_given_options(client, scene, content):
    created = (await add(client, scene, content, **written(scene["competency"]))).json()
    ok = await client.put(f"{ADMIN}/candidates/{created['id']}", json={"expected_answer": "Rows with matches in both tables only.", "rubric": [{"criterion": "Accuracy", "weight": 1}]}, headers=auth(scene["ld"]))
    assert ok.status_code == 200 and ok.json()["expected_answer"].startswith("Rows with matches") and ok.json()["rubric"][0]["criterion"] == "Accuracy" and ok.json()["edited"]
    bad = await client.put(f"{ADMIN}/candidates/{created['id']}", json={"options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": False}, {"text": "c", "is_correct": False}]}, headers=auth(scene["ld"]))
    assert bad.status_code == 422
    empty = await client.put(f"{ADMIN}/candidates/{created['id']}", json={"expected_answer": "", "rubric": []}, headers=auth(scene["ld"]))
    assert empty.status_code == 422                           # a written question always keeps something to grade against


async def test_an_answer_key_cannot_be_put_on_a_multiple_choice_question(client, scene, content):
    ok = {"question_text": "What does ON specify in a join?", "options": [{"text": "Match", "is_correct": True}, {"text": "Sort", "is_correct": False}, {"text": "Limit", "is_correct": False}]}
    created = (await add(client, scene, content, **ok)).json()
    resp = await client.put(f"{ADMIN}/candidates/{created['id']}", json={"expected_answer": "x" * 20}, headers=auth(scene["ld"]))
    assert resp.status_code == 422


# ============================================================================== publishing and answering
async def test_publishing_carries_the_answer_key_and_a_learner_answers_it_end_to_end(client, scene, content, ingestion_env, db_session):
    created = (await add(client, scene, content, **written(scene["competency"]))).json()
    published = await client.post(f"{ADMIN}/{content}/publish", headers=auth(scene["ld"]))
    assert published.status_code == 200, published.text
    assert published.json()["questions_published"] == 1

    db_session.expire_all()
    candidate = db_session.get(QuestionCandidate, created["id"])
    question = db_session.get(QuizQuestion, candidate.published_question_id)
    assert question.question_type == "short_answer" and question.expected_answer == EXPECTED and question.rubric[0]["criterion"] == "Matching rows"
    assert db_session.query(QuizQuestion).filter_by(id=question.id).one().competency_id == scene["competency"].id
    quiz = db_session.get(Quiz, question.quiz_id)

    # what the learner is shown
    shown = await client.get(f"{API}/quizzes/{quiz.id}/questions", headers=auth(scene["learner"]))
    assert EXPECTED not in shown.text and shown.json()[0]["rubric"][0]["criterion"] == "Matching rows" and shown.json()[0]["options"] == []

    # and answering it: graded by the (scripted) grading agent, then evidence
    ingestion_env.use_ai(ScriptedAI())
    attempt = (await client.post(f"{API}/quizzes/{quiz.id}/attempts", headers=auth(scene["learner"]))).json()
    result = await client.post(f"{API}/quizzes/{quiz.id}/attempts/{attempt['id']}/submit", headers=auth(scene["learner"]),
                               json={"responses": [{"question_id": str(question.id), "text_response": "An inner join keeps only the rows that have a matching value in both tables."}]})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["grading_status"] == "graded" and body["passed"] is True and body["responses"][0]["graded_by"] == "ai"
    db_session.expire_all()
    [evidence] = db_session.query(EvidenceRecord).filter_by(user_id=scene["learner"].id, competency_id=scene["competency"].id).all()
    assert evidence.source_type == "answer_graded" and evidence.difficulty == 0.6 and evidence.response_id is not None


async def test_when_the_grader_is_down_the_published_question_waits_for_review(client, scene, content, ingestion_env, db_session):
    from tests.foundation.fakes import outage
    created = (await add(client, scene, content, **written(scene["competency"]))).json()
    await client.post(f"{ADMIN}/{content}/publish", headers=auth(scene["ld"]))
    ingestion_env.use_ai(outage())
    db_session.expire_all()
    question = db_session.get(QuizQuestion, db_session.get(QuestionCandidate, created["id"]).published_question_id)
    attempt = (await client.post(f"{API}/quizzes/{question.quiz_id}/attempts", headers=auth(scene["learner"]))).json()
    result = await client.post(f"{API}/quizzes/{question.quiz_id}/attempts/{attempt['id']}/submit", headers=auth(scene["learner"]),
                               json={"responses": [{"question_id": str(question.id), "text_response": EXPECTED}]})
    assert result.json()["grading_status"] == "needs_review"
    queue = (await client.get(f"{API}/grading/queue", headers=auth(scene["ld"]))).json()["items"]
    assert [i["answer"] for i in queue if i["learner"]["id"] == str(scene["learner"].id)] == [EXPECTED]
