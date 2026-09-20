"""Course overview, player payload, and learner home: assembled from stored data only."""

import uuid
from datetime import datetime, timedelta

import pytest

from app.models import (
    AIInsight, CompetencyPrerequisite, ContentCompetency, CourseCompetency, LearningEvent,
)
from tests.foundation.conftest import (
    API, auth, enroll, make_assignment, make_competency, make_course, make_item, make_org, make_quiz,
    make_user, only_module, set_mastery,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    video = make_item(db_session, org, course, module, content_type="VIDEO", order_index=1, seconds=0, title="Intro video",
                      source_type="youtube", source_url="https://www.youtube.com/watch?v=aJc5MuJbOr0")
    article = make_item(db_session, org, course, module, content_type="ARTICLE", order_index=2, seconds=420,
                        title="Reading", text_content="# Notes\nHello.")
    quiz_item = make_item(db_session, org, course, module, content_type="QUIZ", order_index=3, seconds=600, title="Check")
    quiz, _ = make_quiz(db_session, org, course, module, quiz_item)
    lab_item = make_item(db_session, org, course, module, content_type="ASSIGNMENT", order_index=4, seconds=0, title="Lab")
    assignment = make_assignment(db_session, org, course, module, lab_item)
    db_session.commit()
    return org, ld, learner, course, module, dict(video=video, article=article, quiz=quiz_item, lab=lab_item), quiz, assignment


async def overview(client, user, course):
    return await client.get(f"{API}/learning/courses/{course.id}", headers=auth(user))


# --- overview ---------------------------------------------------------------------------
async def test_overview_describes_modules_items_and_kinds(client, scene):
    _, _, learner, course, module, items, quiz, assignment = scene
    body = (await overview(client, learner, course)).json()

    assert body["course"]["id"] == str(course.id)
    [mod] = body["modules"]
    assert (mod["lessons"], mod["assessments"], mod["total_items"]) == (2, 2, 4)
    by_id = {i["id"]: i for i in mod["items"]}
    assert by_id[str(items["quiz"].id)]["kind"] == "assessment" and by_id[str(items["quiz"].id)]["quiz_id"] == str(quiz.id)
    assert by_id[str(items["lab"].id)]["kind"] == "assignment" and by_id[str(items["lab"].id)]["assignment_id"] == str(assignment.id)
    assert [i["title"] for i in mod["items"]] == ["Intro video", "Reading", "Check", "Lab"]  # course order


async def test_overview_duration_counts_only_recorded_lengths(client, scene):
    _, _, learner, course, *_ = scene
    body = (await overview(client, learner, course)).json()
    assert body["course"]["duration_minutes"] == 17  # (420 + 600) s = 17 min; the unknown-length video adds nothing
    assert body["course"]["rating"] is None


async def test_overview_progress_and_resume_point(client, scene, db_session):
    _, _, learner, course, _, items, *_ = scene
    for item, pct, status in ((items["video"], 100, "completed"), (items["article"], 40, "in_progress")):
        await client.post(f"{API}/progress/content/{item.id}", headers=auth(learner),
                          json={"status": status, "progress_percent": pct, "time_spent_seconds": 10})
    body = (await overview(client, learner, course)).json()
    assert body["progress"]["completed_items"] == 1
    assert body["progress"]["percent"] == 25.0
    assert body["progress"]["resume_item_id"] == str(items["article"].id)
    assert body["progress"]["resume_item_title"] == "Reading"


async def test_overview_resume_for_a_new_learner_is_the_first_item(client, scene):
    _, _, learner, course, _, items, *_ = scene
    assert (await overview(client, learner, course)).json()["progress"]["resume_item_id"] == str(items["video"].id)


async def test_learners_do_not_see_unpublished_items_or_courses(client, scene, db_session):
    org, ld, learner, course, module, _, *_ = scene
    make_item(db_session, org, course, module, status="review", order_index=9, title="Not ready")
    draft_course = make_course(db_session, org, ld, status="draft")
    db_session.commit()

    titles = [i["title"] for m in (await overview(client, learner, course)).json()["modules"] for i in m["items"]]
    assert "Not ready" not in titles
    assert (await overview(client, learner, draft_course)).status_code == 404

    author_view = (await overview(client, ld, course)).json()
    assert "Not ready" in [i["title"] for m in author_view["modules"] for i in m["items"]]
    assert author_view["is_preview"] is True
    assert (await overview(client, ld, draft_course)).status_code == 200


async def test_competencies_developed_show_mastery_only_when_evidence_exists(client, scene, db_session):
    org, _, learner, course, *_ = scene
    joins = make_competency(db_session, org, "sql.joins", domain="sql")
    window = make_competency(db_session, org, "sql.window", domain="sql")
    for comp in (joins, window):
        db_session.add(CourseCompetency(course_id=course.id, competency_id=comp.id, target_mastery=0.8, is_primary=True))
    set_mastery(db_session, org, learner, joins, 0.42, confidence=0.7)
    db_session.commit()

    comps = {c["code"]: c for c in (await overview(client, learner, course)).json()["competencies"]}
    assert comps["sql.joins"]["mastery"] == 0.42 and comps["sql.joins"]["confidence"] == 0.7
    assert comps["sql.window"]["mastery"] is None  # no evidence -> unknown, not zero
    assert comps["sql.joins"]["target_mastery"] == 0.8


async def test_prerequisites_are_competencies_the_course_builds_on_but_does_not_teach(client, scene, db_session):
    org, ld, learner, course, *_ = scene
    taught = make_competency(db_session, org, "sql.joins", domain="sql")
    also_taught = make_competency(db_session, org, "sql.filtering", domain="sql")
    outside = make_competency(db_session, org, "sql.basics", domain="sql")
    for comp in (taught, also_taught):
        db_session.add(CourseCompetency(course_id=course.id, competency_id=comp.id, target_mastery=0.8))
    db_session.add_all([
        CompetencyPrerequisite(competency_id=taught.id, prerequisite_id=outside.id, org_id=org.id, min_mastery=0.6),
        CompetencyPrerequisite(competency_id=taught.id, prerequisite_id=also_taught.id, org_id=org.id, min_mastery=0.6),
    ])
    db_session.commit()

    [prereq] = (await overview(client, learner, course)).json()["prerequisites"]
    assert prereq["code"] == "sql.basics"  # sql.filtering is taught by the course itself, so it is not listed
    assert prereq["required_for"] == [taught.name]
    assert (prereq["mastery"], prereq["met"]) == (None, None)  # no evidence -> unknown

    set_mastery(db_session, org, learner, outside, 0.7)
    db_session.commit()
    [prereq] = (await overview(client, learner, course)).json()["prerequisites"]
    assert (prereq["mastery"], prereq["met"]) == (0.7, True)


async def test_objectives_come_from_content_analysis_else_competencies_else_nothing(client, scene, db_session):
    org, _, learner, course, module, items, *_ = scene
    assert (await overview(client, learner, course)).json()["objectives_source"] == "none"

    comp = make_competency(db_session, org, "sql.joins", domain="sql")
    comp.description = "Choose the right JOIN for a question."
    db_session.add(CourseCompetency(course_id=course.id, competency_id=comp.id))
    db_session.commit()
    body = (await overview(client, learner, course)).json()
    assert (body["objectives_source"], body["objectives"]) == ("competency_descriptions", ["Choose the right JOIN for a question."])

    items["article"].analysis = {"objectives": ["Explain INNER vs LEFT JOIN", "Explain INNER vs LEFT JOIN", " Read a join condition "]}
    db_session.commit()
    body = (await overview(client, learner, course)).json()
    assert body["objectives_source"] == "content_analysis"
    assert body["objectives"] == ["Explain INNER vs LEFT JOIN", "Read a join condition"]  # de-duplicated, trimmed


async def test_enrollment_flag_and_count(client, scene, db_session):
    org, _, learner, course, *_ = scene
    assert (await overview(client, learner, course)).json()["is_enrolled"] is False
    enroll(db_session, org, learner, course)
    db_session.commit()
    body = (await overview(client, learner, course)).json()
    assert body["is_enrolled"] is True and body["course"]["enrollment_count"] == 1


# --- player ---------------------------------------------------------------------------------
async def test_player_payload_for_a_youtube_video(client, scene):
    _, _, learner, course, _, items, *_ = scene
    body = (await client.get(f"{API}/learning/content/{items['video'].id}", headers=auth(learner))).json()
    assert body["item"]["media"] == {"provider": "youtube", "video_id": "aJc5MuJbOr0", "url": None, "mime_type": None}
    assert (body["position"], body["total"]) == (1, 4)
    assert body["previous_id"] is None and body["next_id"] == str(items["article"].id)
    assert body["course_title"] == course.title


async def test_player_payload_for_an_article_has_text_and_no_media(client, scene):
    _, _, learner, _, _, items, *_ = scene
    body = (await client.get(f"{API}/learning/content/{items['article'].id}", headers=auth(learner))).json()
    assert body["item"]["text_content"].startswith("# Notes")
    assert body["item"]["media"] is None
    assert body["previous_id"] == str(items["video"].id) and body["next_id"] == str(items["quiz"].id)


async def test_player_returns_the_resume_position(client, scene):
    _, _, learner, _, _, items, *_ = scene
    await client.post(f"{API}/progress/content/{items['video'].id}", headers=auth(learner),
                      json={"status": "in_progress", "progress_percent": 30, "time_spent_seconds": 5, "position_seconds": 137})
    body = (await client.get(f"{API}/learning/content/{items['video'].id}", headers=auth(learner))).json()
    assert body["progress"]["position_seconds"] == 137 and body["progress"]["progress_percent"] == 30.0


async def test_player_payload_links_quiz_and_assignment(client, scene, db_session):
    _, _, learner, _, _, items, quiz, assignment = scene
    quiz_body = (await client.get(f"{API}/learning/content/{items['quiz'].id}", headers=auth(learner))).json()
    assert quiz_body["item"]["quiz_id"] == str(quiz.id)

    lab = (await client.get(f"{API}/learning/content/{items['lab'].id}", headers=auth(learner))).json()["item"]["assignment"]
    assert lab["id"] == str(assignment.id) and lab["submission_status"] is None
    await client.post(f"{API}/assignments/{assignment.id}/submit", json={"submission_text": "done"}, headers=auth(learner))
    lab = (await client.get(f"{API}/learning/content/{items['lab'].id}", headers=auth(learner))).json()["item"]["assignment"]
    assert (lab["submission_status"], lab["submission_text"]) == ("SUBMITTED", "done")


async def test_player_never_exposes_quiz_answers(client, scene):
    _, _, learner, _, _, items, *_ = scene
    text = (await client.get(f"{API}/learning/content/{items['quiz'].id}", headers=auth(learner))).text
    assert "is_correct" not in text and "correct_option" not in text


async def test_player_hides_unpublished_items_from_learners(client, scene, db_session):
    org, ld, learner, course, module, *_ = scene
    hidden = make_item(db_session, org, course, module, status="draft", order_index=8)
    db_session.commit()
    assert (await client.get(f"{API}/learning/content/{hidden.id}", headers=auth(learner))).status_code == 404
    assert (await client.get(f"{API}/learning/content/{hidden.id}", headers=auth(ld))).status_code == 200


async def test_file_endpoint_only_serves_uploads(client, scene):
    _, _, learner, _, _, items, *_ = scene
    resp = await client.get(f"{API}/learning/content/{items['video'].id}/file", headers=auth(learner))
    assert resp.status_code == 404  # a YouTube item has no stored file


# --- home -------------------------------------------------------------------------------------
async def test_home_for_a_brand_new_learner_is_honestly_empty(client, db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    make_course(db_session, org, ld)
    db_session.commit()

    home = (await client.get(f"{API}/learning/home", headers=auth(learner))).json()
    assert home["continue_learning"] is None
    assert home["in_progress"] == [] and home["competencies"] == [] and home["recent_activity"] == []
    assert home["insight"] is None
    assert home["stats"] == {"enrolled_courses": 0, "completed_courses": 0, "completed_items": 0, "time_spent_seconds": 0}
    assert [r["reason_type"] for r in home["recommendations"]] == ["available"]  # a published course they have not started


async def test_home_continue_learning_points_at_the_resume_item(client, scene, db_session):
    org, _, learner, course, _, items, *_ = scene
    enroll(db_session, org, learner, course)
    db_session.commit()
    await client.post(f"{API}/progress/content/{items['video'].id}", headers=auth(learner),
                      json={"status": "completed", "progress_percent": 100, "time_spent_seconds": 5})

    home = (await client.get(f"{API}/learning/home", headers=auth(learner))).json()
    cont = home["continue_learning"]
    assert cont["course_id"] == str(course.id) and cont["item_title"] == "Reading" and cont["module_title"] == "Module 1"
    assert cont["progress_percent"] == 25.0
    assert [c["course_id"] for c in home["in_progress"]] == [str(course.id)]
    assert home["stats"]["enrolled_courses"] == 1 and home["stats"]["completed_items"] == 1
    assert [a["label"] for a in home["recent_activity"]][0] == f"Completed {items['video'].title}"


async def test_home_recommends_content_for_a_weak_competency_and_says_why(client, scene, db_session):
    org, _, learner, course, _, items, *_ = scene
    joins = make_competency(db_session, org, "sql.joins", domain="sql")
    strong = make_competency(db_session, org, "sql.basics", domain="sql")
    db_session.add_all([
        ContentCompetency(content_item_id=items["article"].id, competency_id=joins.id),
        ContentCompetency(content_item_id=items["video"].id, competency_id=strong.id),
    ])
    set_mastery(db_session, org, learner, joins, 0.42, evidence=7)
    set_mastery(db_session, org, learner, strong, 0.9)
    db_session.commit()

    recs = (await client.get(f"{API}/learning/home", headers=auth(learner))).json()["recommendations"]
    first = recs[0]
    assert first["reason_type"] == "weak_competency" and first["content_id"] == str(items["article"].id)
    assert first["competency_name"] == joins.name and first["mastery"] == 0.42
    assert "42%" in first["reason"]
    assert str(items["video"].id) not in {r["content_id"] for r in recs}  # the strong competency is not recommended


async def test_home_does_not_recommend_content_already_completed(client, scene, db_session):
    org, _, learner, _, _, items, *_ = scene
    joins = make_competency(db_session, org, "sql.joins", domain="sql")
    db_session.add(ContentCompetency(content_item_id=items["article"].id, competency_id=joins.id))
    set_mastery(db_session, org, learner, joins, 0.3)
    db_session.commit()
    await client.post(f"{API}/progress/content/{items['article'].id}", headers=auth(learner),
                      json={"status": "completed", "progress_percent": 100, "time_spent_seconds": 5})

    recs = (await client.get(f"{API}/learning/home", headers=auth(learner))).json()["recommendations"]
    assert str(items["article"].id) not in {r["content_id"] for r in recs}


async def test_home_lists_competencies_recent_activity_and_latest_insight(client, scene, db_session):
    org, _, learner, course, _, items, *_ = scene
    comp = make_competency(db_session, org, "python.basics", domain="python")
    set_mastery(db_session, org, learner, comp, 0.78, confidence=0.9, evidence=12)
    db_session.add(LearningEvent(
        id=uuid.uuid4(), org_id=org.id, user_id=learner.id, course_id=course.id, event_type="assessment_completed",
        payload={"score": 80.0}, timestamp=datetime.utcnow(),
    ))
    old, new = datetime.utcnow() - timedelta(days=3), datetime.utcnow()
    for created, text in ((old, "old insight"), (new, "You are progressing steadily in Python fundamentals. " * 20)):
        db_session.add(AIInsight(
            id=uuid.uuid4(), org_id=org.id, report_type="learner_progress", scope_type="learner", scope_id=learner.id,
            narrative_text=text, model_used="test-model", created_at=created,
        ))
    db_session.commit()

    home = (await client.get(f"{API}/learning/home", headers=auth(learner))).json()
    assert [(c["name"], c["mastery"], c["evidence_count"]) for c in home["competencies"]] == [(comp.name, 0.78, 12)]
    assert home["recent_activity"][0]["label"] == "Finished an assessment (score 80%)"
    assert home["recent_activity"][0]["course_title"] == course.title
    assert home["insight"]["narrative"].startswith("You are progressing steadily")  # the newest one
    assert home["insight"]["narrative"].endswith("…") and len(home["insight"]["narrative"]) <= 421


async def test_home_is_personal(client, scene, db_session):
    org, _, learner, course, _, items, *_ = scene
    other = make_user(db_session, org, ["learner"])
    enroll(db_session, org, learner, course)
    db_session.commit()
    await client.post(f"{API}/progress/content/{items['video'].id}", headers=auth(learner),
                      json={"status": "completed", "progress_percent": 100, "time_spent_seconds": 5})
    other_home = (await client.get(f"{API}/learning/home", headers=auth(other))).json()
    assert other_home["continue_learning"] is None and other_home["recent_activity"] == []


async def test_home_counts_completed_courses_from_lesson_records_not_stored_status(client, scene, db_session):
    """A stored 'completed' status that no lesson records support must not count."""
    org, _, learner, course, *_ = scene
    enrollment = enroll(db_session, org, learner, course)
    enrollment.status, enrollment.progress_pct = "completed", 100.0  # what an old demo script wrote
    db_session.commit()

    home = (await client.get(f"{API}/learning/home", headers=auth(learner))).json()
    assert home["stats"]["completed_courses"] == 0
    assert home["stats"]["completed_items"] == 0
    assert [c["course_id"] for c in home["in_progress"]] == [str(course.id)]  # still in progress
