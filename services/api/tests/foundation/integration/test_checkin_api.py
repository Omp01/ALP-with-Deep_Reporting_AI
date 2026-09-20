"""
The login check-in through the real API: an AI-written quiz on the learner's own course material, a self-report, scores and a
report. The model is a scripted double; what is tested is everything around it (what may be shown, what is verified, what is
scored, who may read it, what happens when the model is down or lies).
"""

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.checkin import service as checkin_service
from app.core.config import settings
from app.ingestion import ai as ingestion_ai
from app.models import Checkin, LearningEvent
from tests.foundation.conftest import (
    API, TEST_ASYNC_URL, auth, enroll, make_course, make_item, make_org, make_user, only_module,
)
from tests.foundation.fakes import ScriptedAI, faithful_items, outage

pytestmark = pytest.mark.integration

MATERIAL = (
    "A database index is a separate structure that lets the engine find rows without scanning the whole table. "
    "A composite index orders its entries by the first column and then by the following columns in turn. "
    "The query planner chooses an index only when it expects to read fewer pages than a sequential scan would. "
    "Every additional index makes writes slower because each insert must update every index on the table.\n\n"
    "A transaction groups statements so that either all of them take effect or none of them do. "
    "Isolation levels decide which changes made by concurrent transactions a statement is allowed to see. "
    "Deadlocks happen when two transactions each wait for a lock that the other one already holds."
)


@pytest_asyncio.fixture
async def env(test_database, monkeypatch):
    engine = create_async_engine(TEST_ASYNC_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(settings, "checkin_run_inline", True)
    monkeypatch.setattr(settings, "checkin_max_per_day", 20)
    checkin_service.set_session_factory(factory)
    ingestion_ai.set_provider_override(lambda task: ScriptedAI())

    class Env:
        @staticmethod
        def use(provider):
            ingestion_ai.set_provider_override(lambda task: provider)

    yield Env
    checkin_service.set_session_factory(None)
    ingestion_ai.set_provider_override(None)
    await engine.dispose()


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    other_org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    manager = make_user(db_session, org, ["manager"])
    learner = make_user(db_session, org, ["learner"])
    other = make_user(db_session, org, ["learner"])
    outsider = make_user(db_session, other_org, ["learner"])
    unenrolled = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    lesson = make_item(db_session, org, course, module, content_type="ARTICLE", order_index=0, title="Indexes and transactions", text_content=MATERIAL)
    enroll(db_session, org, learner, course)
    enroll(db_session, org, other, course)
    db_session.commit()
    return dict(org=org, ld=ld, manager=manager, learner=learner, other=other, outsider=outsider, unenrolled=unenrolled, course=course, module=module, lesson=lesson)


async def start(client, user, **body):
    resp = await client.post(f"{API}/checkins/start", headers=auth(user), json={"fresh": True, **body})
    assert resp.status_code == 202, resp.text
    return resp.json()


def answers_for(db_session, checkin_id, correct: bool = True, self_report: bool = True):
    """Answer from the stored key: what only the database (never the learner) knows."""
    row = db_session.query(Checkin).filter_by(id=checkin_id).one()
    db_session.refresh(row)
    quiz = {}
    for q in row.quiz:
        right = next(o for o in q["options"] if o["is_correct"])
        wrong = next(o for o in q["options"] if not o["is_correct"])
        quiz[q["id"]] = (right if correct else wrong)["id"]
    rating = {}
    if self_report:
        for item in row.psychometric:
            best = 1 if item["reverse"] else 5           # the most favourable answer, whichever way the statement is worded
            rating[item["id"]] = best
    return {"quiz": quiz, "self_report": rating}


async def submit(client, user, checkin_id, body):
    return await client.post(f"{API}/checkins/{checkin_id}/submit", headers=auth(user), json=body)


# ------------------------------------------------------------------------------------ the check-in
async def test_a_check_in_is_written_from_the_course_material_and_hides_the_answers(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    assert c["status"] == "ready" and c["course"]["title"] == scene["course"].title
    assert len(c["quiz"]) >= settings.checkin_min_questions
    assert len(c["self_report"]["statements"]) == 12 and c["self_report"]["scale"]["labels"][0] == "Strongly disagree"
    text = json.dumps(c)
    for hidden in ("is_correct", "explanation", "source_quote", "reverse", "construct"):
        assert hidden not in text

    row = db_session.query(Checkin).filter_by(id=c["id"]).one()
    plain = " ".join(MATERIAL.split()).lower()
    for q in row.quiz:                                       # every stored question is tied to a passage that really is in the course
        assert " ".join(q["source_quote"].split()).lower() in plain
        assert q["content_title"] == "Indexes and transactions"
        assert sum(o["is_correct"] for o in q["options"]) == 1
    assert row.provenance["prompt_version"] == "checkin_v1"


async def test_submitting_scores_the_quiz_and_the_self_report_and_reveals_the_review(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    resp = await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))
    assert resp.status_code == 200, resp.text
    report = resp.json()["report"]
    quiz = report["quiz"]
    assert quiz["correct"] == quiz["total"] and quiz["percent"] == 100.0 and quiz["unanswered"] == 0
    assert all(r["correct"] and r["source_quote"] and r["explanation"] for r in quiz["review"])
    assert {k: v["score"] for k, v in report["self_report"].items()} == {"self_efficacy": 100.0, "motivation": 100.0, "self_regulation": 100.0, "learning_anxiety": 100.0}
    assert report["self_report"]["self_efficacy"]["band"] == "high" and report["self_report_disclaimer"]
    assert report["coaching_note"]["status"] == "ok" and str(quiz["total"]) in report["coaching_note"]["note"]
    assert resp.json()["status"] == "completed"
    again = await submit(client, scene["learner"], c["id"], {"quiz": {}, "self_report": {}})
    assert again.status_code == 409                          # a check-in is scored once


async def test_wrong_answers_are_scored_as_wrong_and_unanswered_ones_are_named(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    body = answers_for(db_session, c["id"], correct=False)
    first = next(iter(body["quiz"]))
    body["quiz"].pop(first)                                  # leave one unanswered
    report = (await submit(client, scene["learner"], c["id"], body)).json()["report"]["quiz"]
    assert report["correct"] == 0 and report["unanswered"] == 1
    unanswered = [r for r in report["review"] if not r["answered"]]
    assert len(unanswered) == 1 and unanswered[0]["your_answer"] is None and unanswered[0]["correct"] is False


async def test_a_construct_with_too_few_answers_is_not_scored(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    body = answers_for(db_session, c["id"])
    keep = {sid: v for sid, v in body["self_report"].items() if sid.startswith("motivation")}
    only_one = {next(iter(keep)): 3}                          # one answer in one construct, nothing elsewhere
    report = (await submit(client, scene["learner"], c["id"], {"quiz": body["quiz"], "self_report": only_one})).json()["report"]
    assert all(v["scored"] is False for v in report["self_report"].values())


async def test_answers_that_do_not_belong_to_the_check_in_are_refused(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    body = answers_for(db_session, c["id"])
    assert (await submit(client, scene["learner"], c["id"], {**body, "quiz": {"q99": "a"}})).status_code == 422
    assert (await submit(client, scene["learner"], c["id"], {**body, "quiz": {"q1": "zzz"}})).status_code == 422
    assert (await submit(client, scene["learner"], c["id"], {**body, "self_report": {"self_efficacy_1": 9}})).status_code == 422
    assert (await submit(client, scene["learner"], c["id"], {**body, "self_report": {"nope_1": 3}})).status_code == 422
    assert db_session.query(Checkin).filter_by(id=c["id"]).one().status == "ready"      # nothing was scored


async def test_completing_a_check_in_is_recorded_as_an_event_without_the_self_report(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))
    events = db_session.query(LearningEvent).filter_by(user_id=scene["learner"].id, event_type="checkin_completed").all()
    assert len(events) == 1
    payload = events[0].payload
    assert payload["checkin_id"] == c["id"] and payload["quiz_percent"] == 100.0
    assert "self_report" not in json.dumps(payload) and "self_efficacy" not in json.dumps(payload)


# ----------------------------------------------------------------------------------- freshness
async def test_each_check_in_asks_the_model_to_avoid_what_the_learner_has_already_seen(client, env, scene, db_session):
    provider = ScriptedAI()
    env.use(provider)
    first = await start(client, scene["learner"])
    await submit(client, scene["learner"], first["id"], answers_for(db_session, first["id"]))
    asked = [q["text"] for q in db_session.query(Checkin).filter_by(id=first["id"]).one().quiz]

    second = await start(client, scene["learner"])
    prompts = [c["user"] for c in provider.calls if c["kind"] == "questions"]
    assert len(prompts) == 2 and "(none)" in prompts[0].split("do NOT repeat or rephrase them):")[1].split("MATERIAL")[0]
    assert all(question[:140] in prompts[1] for question in asked)
    statements = [i["text"] for i in db_session.query(Checkin).filter_by(id=first["id"]).one().psychometric]
    item_prompts = [c["user"] for c in provider.calls if c["kind"] == "items"]
    assert statements[0] in item_prompts[1]
    assert second["id"] != first["id"]


async def test_a_new_login_replaces_an_unfinished_check_in_but_a_reload_resumes_it(client, env, scene, db_session):
    first = await start(client, scene["learner"])
    resumed = (await client.post(f"{API}/checkins/start", headers=auth(scene["learner"]), json={"fresh": False})).json()
    assert resumed["id"] == first["id"]
    fresh = await start(client, scene["learner"])
    assert fresh["id"] != first["id"]
    assert db_session.query(Checkin).filter_by(id=first["id"]).one().status == "skipped"


async def test_a_learner_can_skip(client, env, scene):
    c = await start(client, scene["learner"])
    resp = await client.post(f"{API}/checkins/{c['id']}/skip", headers=auth(scene["learner"]))
    assert resp.status_code == 200 and resp.json()["status"] == "skipped"
    assert (await submit(client, scene["learner"], c["id"], {"quiz": {}, "self_report": {}})).status_code == 409


async def test_the_second_check_in_shows_the_change_since_the_first(client, env, scene, db_session):
    env.use(ScriptedAI())
    first = await start(client, scene["learner"])
    await submit(client, scene["learner"], first["id"], answers_for(db_session, first["id"]))
    second = await start(client, scene["learner"])
    body = answers_for(db_session, second["id"])
    body["self_report"] = {k: 3 for k in body["self_report"]}          # neutral everywhere, but reverse-keyed 3 stays 3: 50 points
    report = (await submit(client, scene["learner"], second["id"], body)).json()["report"]
    eff = report["self_report"]["self_efficacy"]
    assert eff["previous"] == 100.0 and eff["score"] == 50.0 and eff["change"] == -50.0 and eff["change_is_meaningful"] is True
    assert any("previous check-in" in o["text"] for o in report["observations"])


# ------------------------------------------------------------------------------------- honesty
async def test_a_learner_with_no_course_is_told_so(client, env, scene):
    c = await start(client, scene["unenrolled"])
    assert c["status"] == "failed" and c["error"]["code"] == "no_course" and "quiz" not in c


async def test_a_course_without_published_text_says_so(client, env, scene, db_session):
    other = make_course(db_session, scene["org"], scene["ld"], content_seconds=[])
    make_item(db_session, scene["org"], other, only_module(db_session, other), content_type="ARTICLE", title="Empty", text_content="")
    enroll(db_session, scene["org"], scene["unenrolled"], other)
    db_session.commit()
    c = await start(client, scene["unenrolled"])
    assert c["status"] == "failed" and c["error"]["code"] == "no_material"


async def test_when_the_model_is_down_nothing_is_invented(client, env, scene):
    env.use(outage())
    c = await start(client, scene["learner"])
    assert c["status"] == "failed" and c["error"]["code"] == "ai_unavailable"
    assert "quiz" not in c and "self_report" not in c


async def test_questions_that_quote_text_not_in_the_course_are_dropped_and_the_check_in_fails_honestly(client, env, scene, db_session):
    def invented(material):
        return {"questions": [{"question": f"Invented question number {i} about something else entirely?", "options": ["one", "two", "three"], "correct_index": 0,
                               "explanation": "made up", "difficulty": 0.5, "competency": "x", "source_quote": f"this passage number {i} does not exist anywhere in the course", "chunk_index": 0}
                              for i in range(5)]}
    env.use(ScriptedAI(questions=invented))
    c = await start(client, scene["learner"])
    assert c["status"] == "failed" and c["error"]["code"] == "ai_invalid" and "verification" in c["error"]["message"]


async def test_unusable_self_report_statements_fail_the_check_in(client, env, scene):
    env.use(ScriptedAI(items={"items": [{"dimension": "astrology", "text": "I feel that the stars are aligned for my learning today.", "reverse": False}]}))
    c = await start(client, scene["learner"])
    assert c["status"] == "failed" and c["error"]["code"] == "ai_invalid"


async def test_a_coaching_note_with_an_invented_number_is_discarded_and_the_report_stands(client, env, scene, db_session):
    env.use(ScriptedAI(note={"note": "You scored 97 out of 100 on this check-in, which is a strong result that puts you well ahead of your colleagues."}))
    c = await start(client, scene["learner"])
    report = (await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))).json()["report"]
    assert report["coaching_note"]["status"] == "invalid" and report["coaching_note"]["note"] is None
    assert report["quiz"]["percent"] == 100.0 and report["self_report"]["self_efficacy"]["scored"]


@pytest.mark.parametrize("note", [
    "Your answers may point to an anxiety disorder, so you should speak to a doctor about therapy.",
    "Your low score was caused by your low confidence, so build confidence first and everything will follow from it.",
])
async def test_a_coaching_note_with_diagnostic_or_causal_language_is_discarded(client, env, scene, db_session, note):
    env.use(ScriptedAI(note={"note": note}))
    c = await start(client, scene["learner"])
    report = (await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))).json()["report"]
    assert report["coaching_note"]["status"] == "invalid" and report["coaching_note"]["note"] is None


async def test_a_model_outage_at_report_time_leaves_the_scores_and_says_the_note_is_missing(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    env.use(outage())
    report = (await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))).json()["report"]
    assert report["coaching_note"]["status"] == "unavailable" and report["quiz"]["percent"] == 100.0


# ---------------------------------------------------------------------------------- privacy
async def test_nobody_but_the_learner_can_open_a_check_in(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))
    for who in (scene["other"], scene["manager"], scene["ld"], scene["outsider"]):
        assert (await client.get(f"{API}/checkins/{c['id']}", headers=auth(who))).status_code == 404
        assert (await submit(client, who, c["id"], {"quiz": {}, "self_report": {}})).status_code in (404, 409)
        assert (await client.post(f"{API}/checkins/{c['id']}/skip", headers=auth(who))).status_code == 404
        assert all(row["id"] != c["id"] for row in (await client.get(f"{API}/checkins", headers=auth(who))).json())
    assert (await client.get(f"{API}/checkins/{c['id']}", headers=auth(scene["learner"]))).status_code == 200


async def test_the_self_report_never_reaches_a_manager_report(client, env, scene, db_session):
    c = await start(client, scene["learner"])
    await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))
    resp = await client.post(f"{API}/reports/generate", headers=auth(scene["manager"]), json={"audience": "team", "use_ai": False})
    assert resp.status_code in (200, 404)
    text = resp.text.lower()
    for word in ("self_efficacy", "learning_anxiety", "self_regulation", "checkin"):
        assert word not in text


async def test_history_lists_only_your_own_check_ins_with_their_scores(client, env, scene, db_session):
    a = await start(client, scene["learner"])
    await submit(client, scene["learner"], a["id"], answers_for(db_session, a["id"]))
    await start(client, scene["other"])
    rows = (await client.get(f"{API}/checkins", headers=auth(scene["learner"]))).json()
    assert [r["id"] for r in rows] == [a["id"]]
    assert rows[0]["quiz_percent"] == 100.0 and rows[0]["self_report"]["self_efficacy"] == 100.0


async def test_the_daily_limit_protects_the_model_budget(client, env, scene, monkeypatch):
    monkeypatch.setattr(settings, "checkin_max_per_day", 2)
    await start(client, scene["learner"])
    await start(client, scene["learner"])
    resp = await client.post(f"{API}/checkins/start", headers=auth(scene["learner"]), json={"fresh": True})
    assert resp.status_code == 429 and resp.json()["detail"]["code"] == "rate_limited"


async def test_a_check_in_needs_a_login(client, env, scene):
    assert (await client.post(f"{API}/checkins/start", json={})).status_code in (401, 403)
    assert (await client.get(f"{API}/checkins/{uuid.uuid4()}")).status_code in (401, 403)


async def test_a_rejected_coaching_note_gets_one_correction_attempt(client, env, scene, db_session):
    calls = []

    def note(facts):
        calls.append(facts)
        if len(calls) == 1:
            return {"note": "You scored 97 out of 100 on this check-in, which is a strong result overall."}
        return {"note": f"You answered {facts['quiz']['correct']} of {facts['quiz']['total']} questions correctly. Review the lesson you missed and keep your sessions short."}

    provider = ScriptedAI(note=note)
    env.use(provider)
    c = await start(client, scene["learner"])
    report = (await submit(client, scene["learner"], c["id"], answers_for(db_session, c["id"]))).json()["report"]
    assert len(calls) == 2 and report["coaching_note"]["status"] == "ok"
    retry_prompt = [x for x in provider.calls if x["kind"] == "note"][1]["user"]
    assert "numbers that are not in the evidence: 97" in retry_prompt and "was rejected" in retry_prompt
