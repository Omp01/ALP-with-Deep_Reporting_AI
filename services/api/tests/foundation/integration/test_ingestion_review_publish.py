"""
Reviewing generated material and publishing it, through the real API and database.

An administrator decides what learners see: nothing generated reaches a learner until it has
been approved and the content is published.
"""

import pytest

from app.models import (
    AuditLog,
    Competency,
    ContentCompetency,
    ContentItem,
    CourseCompetency,
    IngestionJob,
    ModuleCompetency,
    QuestionCandidate,
    Quiz,
    QuizOption,
    QuizQuestion,
)
from tests.foundation.conftest import API, auth, enroll, make_competency, make_course, make_org, make_user, only_module
from tests.foundation.fakes import PROSE, ScriptedAI

pytestmark = pytest.mark.integration

ADMIN = f"{API}/admin/content"


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    enroll(db_session, org, learner, course)
    db_session.commit()
    return org, ld, learner, course, module


@pytest.fixture
async def reviewed(client, ingestion_env, scene):
    """A text file that has been ingested and is waiting for review."""
    _, ld, _, _, module = scene
    ingestion_env.use_ai(ScriptedAI())
    resp = await client.post(f"{ADMIN}/ingest/file", files={"file": ("Joins.txt", PROSE.encode(), "text/plain")},
                             data={"module_id": str(module.id)}, headers=auth(ld))
    assert resp.status_code == 202
    return resp.json()["content_id"]


def questions_in(session, org):
    return session.query(QuizQuestion).join(Quiz, Quiz.id == QuizQuestion.quiz_id).filter(Quiz.org_id == org.id).count()


async def detail(client, user, content_id):
    return (await client.get(f"{ADMIN}/{content_id}", headers=auth(user))).json()


async def approve_all(client, user, content_id):
    body = await detail(client, user, content_id)
    ids = [c["id"] for c in body["candidates"]]
    resp = await client.post(f"{ADMIN}/{content_id}/candidates/status", json={"ids": ids, "status": "approved"}, headers=auth(user))
    assert resp.status_code == 200
    return ids


def options(*texts, correct=0):
    return [{"text": t, "is_correct": i == correct} for i, t in enumerate(texts)]


# ============================================================================= editing
async def test_metadata_can_be_edited(client, scene, reviewed):
    _, ld, *_ = scene
    resp = await client.put(f"{ADMIN}/{reviewed}", json={"title": "  Joins,   the basics ", "description": "Intro"}, headers=auth(ld))
    assert resp.status_code == 200 and resp.json()["title"] == "Joins, the basics" and resp.json()["description"] == "Intro"
    assert (await client.put(f"{ADMIN}/{reviewed}", json={"title": ""}, headers=auth(ld))).status_code == 422


async def test_content_can_be_moved_to_another_module_in_the_same_tenant_only(client, scene, reviewed, db_session):
    org, ld, *_ = scene
    course = make_course(db_session, org, ld, content_seconds=[])
    other_module = only_module(db_session, course)
    foreign_org = make_org(db_session)
    foreign_ld = make_user(db_session, foreign_org, ["ld_admin"])
    foreign_module = only_module(db_session, make_course(db_session, foreign_org, foreign_ld, content_seconds=[]))
    db_session.commit()

    moved = await client.put(f"{ADMIN}/{reviewed}", json={"module_id": str(other_module.id)}, headers=auth(ld))
    assert moved.status_code == 200 and moved.json()["module_id"] == str(other_module.id) and moved.json()["course_id"] == str(course.id)
    assert (await client.put(f"{ADMIN}/{reviewed}", json={"module_id": str(foreign_module.id)}, headers=auth(ld))).status_code == 404


async def test_the_analysis_can_be_edited_and_is_marked_as_edited(client, scene, reviewed):
    _, ld, *_ = scene
    resp = await client.put(f"{ADMIN}/{reviewed}/analysis", json={
        "objectives": ["Choose the right join for a query", "Explain what NULL means in an outer join"],
        "level": "intermediate", "summary": "A short, corrected summary.",
    }, headers=auth(ld))
    analysis = resp.json()["analysis"]
    assert analysis["objectives"] == ["Choose the right join for a query", "Explain what NULL means in an outer join"]
    assert analysis["level"] == "intermediate" and analysis["edited"] is True
    assert analysis["provenance"]["provider"] == "scripted-ai"                       # the origin is kept

    assert (await client.put(f"{ADMIN}/{reviewed}/analysis", json={"level": "expert"}, headers=auth(ld))).status_code == 422


async def test_competency_decisions_can_link_create_or_skip(client, scene, reviewed, db_session):
    org, ld, *_ = scene
    existing = make_competency(db_session, org, "sql.joins")
    db_session.commit()
    resp = await client.put(f"{ADMIN}/{reviewed}/analysis", json={"competencies": [
        {"name": "Join selection", "action": "link", "competency_id": str(existing.id)},
        {"name": "Null handling", "action": "create", "code": "sql.nulls", "bloom_level": "apply"},
        {"name": "Query planning", "action": "skip"},
    ]}, headers=auth(ld))
    assert resp.status_code == 200
    decisions = {c["name"]: c for c in resp.json()["analysis"]["competencies"]}
    assert decisions["Join selection"]["competency_id"] == str(existing.id)
    assert decisions["Null handling"]["competency_id"] is None and decisions["Query planning"]["action"] == "skip"


async def test_linking_a_competency_from_another_tenant_is_refused(client, scene, reviewed, db_session):
    _, ld, *_ = scene
    foreign = make_competency(db_session, make_org(db_session), "sql.joins")
    db_session.commit()
    resp = await client.put(f"{ADMIN}/{reviewed}/analysis", json={"competencies": [
        {"name": "Join selection", "action": "link", "competency_id": str(foreign.id)}]}, headers=auth(ld))
    assert resp.status_code == 404


async def test_a_link_decision_without_a_target_is_invalid(client, scene, reviewed):
    _, ld, *_ = scene
    resp = await client.put(f"{ADMIN}/{reviewed}/analysis", json={"competencies": [{"name": "Join selection", "action": "link"}]}, headers=auth(ld))
    assert resp.status_code == 422


# ======================================================================= question review
async def test_a_question_can_be_edited_approved_rejected_and_reset(client, scene, reviewed):
    _, ld, *_ = scene
    first = (await detail(client, ld, reviewed))["candidates"][0]

    edited = await client.put(f"{ADMIN}/candidates/{first['id']}", json={
        "question_text": "Which join keeps every row of the left table?",
        "options": options("LEFT JOIN", "INNER JOIN", "CROSS JOIN", correct=0), "difficulty": 0.3, "explanation": "Outer joins keep unmatched rows.",
    }, headers=auth(ld))
    assert edited.status_code == 200
    body = edited.json()
    assert body["edited"] is True and body["question_text"] == "Which join keeps every row of the left table?"
    assert [o["id"] for o in body["options"]] == ["a", "b", "c"] and body["options"][0]["is_correct"] is True
    assert body["status"] == "pending"                                       # editing does not approve

    for status in ("approved", "rejected", "pending"):
        resp = await client.post(f"{ADMIN}/candidates/{first['id']}/status", json={"status": status}, headers=auth(ld))
        assert resp.status_code == 200 and resp.json()["status"] == status
    assert (await client.post(f"{ADMIN}/candidates/{first['id']}/status", json={"status": "published"}, headers=auth(ld))).status_code == 422


@pytest.mark.parametrize("bad, why", [
    (options("A", "B", correct=0), "at least 3"),
    (options("A", "B", "C", "D", "E", "F"), "at most 5"),
    ([{"text": "A", "is_correct": True}, {"text": "B", "is_correct": True}, {"text": "C", "is_correct": False}], "exactly one"),
    ([{"text": "A", "is_correct": False}, {"text": "B", "is_correct": False}, {"text": "C", "is_correct": False}], "no correct"),
    ([{"text": "Same", "is_correct": True}, {"text": "same", "is_correct": False}, {"text": "C", "is_correct": False}], "duplicate"),
])
async def test_invalid_option_sets_are_rejected(client, scene, reviewed, bad, why):
    _, ld, *_ = scene
    first = (await detail(client, ld, reviewed))["candidates"][0]
    resp = await client.put(f"{ADMIN}/candidates/{first['id']}", json={"options": bad}, headers=auth(ld))
    assert resp.status_code == 422, why
    assert (await detail(client, ld, reviewed))["candidates"][0]["options"] == first["options"]     # unchanged


async def test_bulk_status_changes_apply_only_to_this_content(client, scene, reviewed, ingestion_env):
    _, ld, _, _, module = scene
    other = (await client.post(f"{ADMIN}/ingest/file", files={"file": ("Other.txt", (PROSE + " An extra sentence about databases and tables that is unique.").encode(), "text/plain")},
                               data={"module_id": str(module.id)}, headers=auth(ld))).json()["content_id"]
    mine, theirs = await detail(client, ld, reviewed), await detail(client, ld, other)
    ids = [c["id"] for c in mine["candidates"]] + [theirs["candidates"][0]["id"]]
    changed = await client.post(f"{ADMIN}/{reviewed}/candidates/status", json={"ids": ids, "status": "rejected"}, headers=auth(ld))
    assert len(changed.json()) == len(mine["candidates"])
    assert {c["status"] for c in (await detail(client, ld, other))["candidates"]} == {"pending"}


async def test_an_administrator_can_add_their_own_question(client, scene, reviewed):
    _, ld, *_ = scene
    resp = await client.post(f"{ADMIN}/{reviewed}/candidates", json={
        "question_text": "What does the ON clause of a join specify?", "options": options("Which columns must match", "How many rows to return", "The sort order", correct=0),
        "explanation": "It states the join condition.", "source_quote": "The join condition states which columns must match",
    }, headers=auth(ld))
    assert resp.status_code == 201
    body = resp.json()
    assert body["origin"] == "manual" and body["status"] == "approved"           # written by the reviewer, so already reviewed
    assert body["id"] in {c["id"] for c in (await detail(client, ld, reviewed))["candidates"]}


async def test_a_candidate_can_be_deleted(client, scene, reviewed):
    _, ld, *_ = scene
    first = (await detail(client, ld, reviewed))["candidates"][0]
    assert (await client.delete(f"{ADMIN}/candidates/{first['id']}", headers=auth(ld))).status_code == 204
    assert first["id"] not in {c["id"] for c in (await detail(client, ld, reviewed))["candidates"]}


async def test_a_question_can_be_tied_to_an_existing_competency_only_in_the_same_tenant(client, scene, reviewed, db_session):
    org, ld, *_ = scene
    mine, foreign = make_competency(db_session, org, "sql.joins"), make_competency(db_session, make_org(db_session), "sql.joins")
    db_session.commit()
    first = (await detail(client, ld, reviewed))["candidates"][0]
    assert (await client.put(f"{ADMIN}/candidates/{first['id']}", json={"competency_id": str(mine.id)}, headers=auth(ld))).json()["competency_id"] == str(mine.id)
    assert (await client.put(f"{ADMIN}/candidates/{first['id']}", json={"competency_id": str(foreign.id)}, headers=auth(ld))).status_code == 404


# ================================================================================ publish
async def test_publishing_applies_exactly_what_was_reviewed(client, scene, reviewed, db_session):
    org, ld, learner, course, module = scene
    existing = make_competency(db_session, org, "sql.joins")
    db_session.commit()
    await client.put(f"{ADMIN}/{reviewed}/analysis", json={"competencies": [
        {"name": "Join selection", "action": "link", "competency_id": str(existing.id)},
        {"name": "Null handling", "action": "create", "code": "sql.nulls", "description": "Reason about NULL in joins.", "bloom_level": "apply"},
        {"name": "Query planning", "action": "skip"},
    ]}, headers=auth(ld))
    body = await detail(client, ld, reviewed)
    approved, rejected, *left = [c["id"] for c in body["candidates"]]
    await client.post(f"{ADMIN}/candidates/{approved}/status", json={"status": "approved"}, headers=auth(ld))
    await client.post(f"{ADMIN}/candidates/{rejected}/status", json={"status": "rejected"}, headers=auth(ld))
    ready = (await detail(client, ld, reviewed))["readiness"]
    assert ready["can_publish"] is True and any("have not been reviewed" in w for w in ready["warnings"]) == bool(left)

    resp = await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert (result["status"], result["competencies_created"], result["competencies_linked"], result["questions_published"]) == ("published", 1, 1, 1)

    # competencies: one created (in this tenant), one linked, none for the skipped decision
    created = db_session.query(Competency).filter_by(org_id=org.id, code="sql.nulls").one()
    assert created.name == "Null handling" and created.taxonomy_level == "apply"
    assert db_session.query(Competency).filter_by(org_id=org.id, name="Query planning").count() == 0
    mapped = {r.competency_id for r in db_session.query(ContentCompetency).filter_by(content_item_id=reviewed)}
    assert mapped == {existing.id, created.id}
    assert {r.competency_id for r in db_session.query(ModuleCompetency).filter_by(module_id=module.id)} == {existing.id, created.id}
    assert {r.competency_id for r in db_session.query(CourseCompetency).filter_by(course_id=course.id)} == {existing.id, created.id}

    # only the approved question became a real quiz question, with the shuffled options intact
    quiz = db_session.query(Quiz).filter_by(module_id=module.id).one()
    [question] = db_session.query(QuizQuestion).filter_by(quiz_id=quiz.id).all()
    published = db_session.get(QuestionCandidate, approved)
    assert published.status == "published" and published.published_question_id == question.id
    assert question.question_text == published.question_text
    quiz_options = db_session.query(QuizOption).filter_by(question_id=question.id).order_by(QuizOption.order_index).all()
    assert [(o.option_text, o.is_correct) for o in quiz_options] == [(o["text"], o["is_correct"]) for o in published.options]
    assert db_session.get(QuestionCandidate, rejected).status == "rejected"
    assert db_session.query(QuizQuestion).filter_by(quiz_id=quiz.id).count() == 1

    item = db_session.get(ContentItem, reviewed)
    assert item.status == "published"
    assert db_session.query(IngestionJob).filter_by(content_item_id=reviewed).one().status == "completed"
    assert db_session.query(AuditLog).filter_by(org_id=org.id, action="CONTENT_PUBLISHED").count() == 1

    # and a learner now sees it, with the quiz as its own assessment item
    overview = (await client.get(f"{API}/learning/courses/{course.id}", headers=auth(learner))).json()
    kinds = {i["title"]: i["kind"] for i in overview["modules"][0]["items"]}
    assert kinds["Joins"] == "lesson" and kinds["Check your understanding: Joins"] == "assessment"


async def test_publishing_without_approved_questions_creates_no_quiz(client, scene, reviewed, db_session):
    _, ld, _, _, module = scene
    resp = await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    assert resp.status_code == 200 and resp.json()["questions_published"] == 0 and resp.json()["quiz_content_id"] is None
    assert db_session.query(Quiz).filter_by(module_id=module.id).count() == 0


async def test_unreviewed_questions_are_never_published(client, scene, reviewed, db_session):
    org, ld, *_ = scene
    await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    assert questions_in(db_session, org) == 0
    assert {c["status"] for c in (await detail(client, ld, reviewed))["candidates"]} == {"pending"}


async def test_publishing_again_appends_newly_approved_questions_to_the_same_quiz(client, scene, reviewed, db_session):
    org, ld, _, _, module = scene
    ids = [c["id"] for c in (await detail(client, ld, reviewed))["candidates"]]
    await client.post(f"{ADMIN}/candidates/{ids[0]}/status", json={"status": "approved"}, headers=auth(ld))
    first = (await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))).json()
    await client.post(f"{ADMIN}/candidates/{ids[1]}/status", json={"status": "approved"}, headers=auth(ld))
    second = (await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))).json()

    assert first["quiz_content_id"] == second["quiz_content_id"] and second["questions_published"] == 1
    assert db_session.query(Quiz).filter_by(module_id=module.id).count() == 1
    assert questions_in(db_session, org) == 2
    assert db_session.query(ContentItem).filter_by(module_id=module.id, content_type="QUIZ").count() == 1


async def test_republishing_does_not_duplicate_competencies(client, scene, reviewed, db_session):
    org, ld, *_ = scene
    await client.put(f"{ADMIN}/{reviewed}/analysis", json={"competencies": [{"name": "Null handling", "action": "create", "code": "sql.nulls"}]}, headers=auth(ld))
    await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    again = (await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))).json()
    assert again["competencies_created"] == 0
    assert db_session.query(Competency).filter_by(org_id=org.id, code="sql.nulls").count() == 1


async def test_created_competency_codes_are_made_unique_within_the_tenant(client, scene, reviewed, db_session):
    org, ld, *_ = scene
    make_competency(db_session, org, "sql.nulls")
    db_session.commit()
    await client.put(f"{ADMIN}/{reviewed}/analysis", json={"competencies": [{"name": "Null handling", "action": "create", "code": "SQL.Nulls"}]}, headers=auth(ld))
    assert (await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))).status_code == 200
    assert {c.code for c in db_session.query(Competency).filter_by(org_id=org.id)} == {"sql.nulls", "SQL.Nulls-2"}


async def test_questions_inherit_the_competency_created_for_their_name(client, scene, reviewed, db_session):
    org, ld, *_ = scene
    body = await detail(client, ld, reviewed)
    name = body["candidates"][0]["competency_name"]
    await client.put(f"{ADMIN}/{reviewed}/analysis", json={"competencies": [{"name": name, "action": "create", "code": "sql.joins-new"}]}, headers=auth(ld))
    await client.post(f"{ADMIN}/candidates/{body['candidates'][0]['id']}/status", json={"status": "approved"}, headers=auth(ld))
    await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    [question] = db_session.query(QuizQuestion).join(Quiz, Quiz.id == QuizQuestion.quiz_id).filter(Quiz.org_id == org.id).all()
    assert question.competency_id == db_session.query(Competency).filter_by(org_id=org.id, code="sql.joins-new").one().id


async def test_content_that_is_still_processing_or_empty_cannot_be_published(client, scene, reviewed, db_session):
    _, ld, *_ = scene
    item = db_session.get(ContentItem, reviewed)
    item.status = "processing"
    db_session.commit()
    resp = await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "not_publishable"
    assert "Processing is still running." in resp.json()["detail"]["blockers"]

    item.status = "review"
    item.text_content = item.raw_text = None
    db_session.commit()
    resp = await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    assert resp.status_code == 409 and any("nothing for a learner to see" in b for b in resp.json()["detail"]["blockers"])


async def test_published_questions_are_locked_and_content_must_be_unpublished_before_deletion(client, scene, reviewed, db_session):
    _, ld, learner, course, _ = scene
    [first, *_] = await approve_all(client, ld, reviewed)
    await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))

    assert (await client.put(f"{ADMIN}/candidates/{first}", json={"difficulty": 0.9}, headers=auth(ld))).status_code == 409
    assert (await client.post(f"{ADMIN}/candidates/{first}/status", json={"status": "rejected"}, headers=auth(ld))).status_code == 409
    assert (await client.delete(f"{ADMIN}/candidates/{first}", headers=auth(ld))).status_code == 409
    blocked = await client.delete(f"{ADMIN}/{reviewed}", headers=auth(ld))
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "published"

    unpublished = await client.post(f"{ADMIN}/{reviewed}/unpublish", headers=auth(ld))
    assert unpublished.status_code == 200 and unpublished.json()["status"] == "review"
    assert (await client.post(f"{ADMIN}/{reviewed}/unpublish", headers=auth(ld))).status_code == 409   # already unpublished


async def test_unpublished_content_is_hidden_from_learners_but_kept(client, scene, reviewed, db_session):
    _, ld, learner, course, _ = scene
    await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    titles = lambda body: [i["title"] for m in body["modules"] for i in m["items"]]
    assert "Joins" in titles((await client.get(f"{API}/learning/courses/{course.id}", headers=auth(learner))).json())
    await client.post(f"{ADMIN}/{reviewed}/unpublish", headers=auth(ld))
    assert "Joins" not in titles((await client.get(f"{API}/learning/courses/{course.id}", headers=auth(learner))).json())
    assert db_session.get(ContentItem, reviewed) is not None


async def test_deleting_unpublished_content_removes_it_and_its_file(client, scene, reviewed, ingestion_env, db_session):
    _, ld, *_ = scene
    assert len(ingestion_env.storage.objects) == 1
    assert (await client.delete(f"{ADMIN}/{reviewed}", headers=auth(ld))).status_code == 204
    assert (await client.get(f"{ADMIN}/{reviewed}", headers=auth(ld))).status_code == 404
    assert ingestion_env.storage.objects == {}
    assert db_session.query(QuestionCandidate).filter_by(content_item_id=reviewed).count() == 0
    assert db_session.query(IngestionJob).filter_by(content_item_id=reviewed).count() == 0


async def test_generated_questions_reach_learners_only_after_approval_and_publish(client, scene, reviewed):
    """The central promise: a learner cannot see or answer anything the AI wrote until a person approved it."""
    _, ld, learner, course, _ = scene
    overview = (await client.get(f"{API}/learning/courses/{course.id}", headers=auth(learner))).json()
    assert [i for m in overview["modules"] for i in m["items"]] == []
    assert (await client.get(f"{ADMIN}/{reviewed}", headers=auth(learner))).status_code == 403


async def test_the_reviewed_difficulty_reaches_the_published_question(client, scene, reviewed, db_session):
    """Per-answer evidence records the question's difficulty; it must be the one the reviewer saw."""
    org, ld, *_ = scene
    first = (await detail(client, ld, reviewed))["candidates"][0]
    await client.put(f"{ADMIN}/candidates/{first['id']}", json={"difficulty": 0.85}, headers=auth(ld))
    await client.post(f"{ADMIN}/candidates/{first['id']}/status", json={"status": "approved"}, headers=auth(ld))
    await client.post(f"{ADMIN}/{reviewed}/publish", headers=auth(ld))
    [question] = db_session.query(QuizQuestion).join(Quiz, Quiz.id == QuizQuestion.quiz_id).filter(Quiz.org_id == org.id).all()
    assert question.difficulty == pytest.approx(0.85)
