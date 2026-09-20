"""
Grounded reports through the real API: evidence packages, claims, citation validation, the evidence drawer, audiences, scoping,
scheduled digests and the embeddable widget.
"""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.competency import service as competency_service
from app.models import ContentCompetency, ContentProgress, Report
from tests.foundation.conftest import API, TEST_ASYNC_URL, auth, enroll, make_competency, make_course, make_item, make_org, make_user, only_module
from tests.foundation.fakes import ScriptedAI, outage
from tests.foundation.integration.test_competency_engine import answer_mc, scene  # noqa: F401  (the fixture and the answering helper)

pytestmark = pytest.mark.integration


async def generate(client, user, audience, **body):
    return await client.post(f"{API}/reports/generate", headers=auth(user), json={"audience": audience, **body})


@pytest.fixture
async def weak(client, scene, db_session):  # noqa: F811
    """The learner (on the manager's team) has answered badly; `other` (on nobody's team) has answered well."""
    for _ in range(2):
        await answer_mc(client, scene, [1, 1, 1])
    await answer_mc(client, scene, [0, 0, 0], user=scene["other"])
    return scene


def claim_texts(report):
    return [c["claim"] for c in report["claims"]]


# ================================================================================================= learner
async def test_a_learner_report_is_built_from_their_evidence_and_every_claim_cites_it(client, weak, db_session):
    s = weak
    resp = await generate(client, s["learner"], "learner", use_ai=False)
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["generated_by"] == "deterministic" and report["ai_status"] == "skipped" and report["claims"] and report["rejected_claims"] == []
    kinds = {c["kind"] for c in report["claims"]}
    assert "weak" in kinds and "repeated_error" not in kinds        # multiple-choice errors are 'unknown': the report does not invent a cause
    weak_claim = next(c for c in report["claims"] if c["kind"] == "weak")
    assert weak_claim["claim_type"] == "OBSERVATION" and weak_claim["evidence_ids"] and weak_claim["metric_ids"] and weak_claim["confidence"] > 0
    state = next(m for m in report["metrics"] if m["name"].endswith(": mastery"))
    assert f"{round(state['value'] * 100)}%" in weak_claim["claim"]           # the number in the sentence is the stored figure
    assert all(cid.split("_")[0] in ("state", "evidence", "update", "decision", "session") for c in report["claims"] for cid in c["evidence_ids"])


async def test_the_evidence_drawer_opens_what_a_claim_cites(client, weak):
    s = weak
    report = (await generate(client, s["learner"], "learner", use_ai=False)).json()
    ids = [i for c in report["claims"] for i in c["evidence_ids"]]
    update_id = next(i for i in ids if i.startswith("update_") or i.startswith("evidence_"))
    drawer = await client.get(f"{API}/reports/{report['id']}/evidence/{update_id}", headers=auth(s["learner"]))
    assert drawer.status_code == 200
    body = drawer.json()
    assert body["id"] == update_id and body["org_id"] == str(s["org"].id) and body["data"] and body["cited_by"]
    state_id = next(i for i in ids if i.startswith("state_"))
    state = (await client.get(f"{API}/reports/{report['id']}/evidence/{state_id}", headers=auth(s["learner"]))).json()
    assert {"mastery", "confidence", "trend", "evidence_count", "target"} <= set(state["data"])
    assert (await client.get(f"{API}/reports/{report['id']}/evidence/evidence_{uuid.uuid4()}", headers=auth(s["learner"]))).status_code == 404


async def test_an_update_record_carries_previous_and_new_mastery(client, weak):
    s = weak
    package = (await client.get(f"{API}/reports/learner", headers=auth(s["learner"]))).json()
    updates = [r for r in package["records"].values() if r["type"] == "update"]
    assert updates and all({"previous_mastery", "new_mastery", "signal", "weight", "evidence_id"} <= set(u["data"]) for u in updates)
    assert all(r["org_id"] == str(s["org"].id) for r in package["records"].values())


async def test_a_learner_with_no_evidence_gets_an_honest_empty_report(client, scene):
    report = (await generate(client, scene["learner"], "learner", use_ai=True)).json()
    assert report["claims"] == [] and report["ai_status"] == "skipped" and report["notes"] and "No graded answers" in report["notes"][0]


async def test_a_learner_cannot_ask_about_another_learner_and_cannot_read_team_or_organization_reports(client, weak):
    s = weak
    assert (await generate(client, s["learner"], "learner", scope_id=str(s["other"].id))).status_code == 404
    for audience in ("team", "ld", "organization"):
        assert (await generate(client, s["learner"], audience)).status_code == 403
    assert (await generate(client, s["learner"], "everyone")).status_code == 422


# ============================================================================================ the reporting model
async def test_a_faithful_model_adds_cited_claims_and_a_summary(client, weak, grading_env, db_session):
    grading_env.use(ScriptedAI())
    report = (await generate(client, weak["learner"], "learner", force=True)).json()
    assert report["ai_status"] == "ok" and report["generated_by"] == "ai" and report["model"] == "scripted-model"
    sources = {c["source"] for c in report["claims"]}
    assert sources == {"deterministic", "ai"} and report["rejected_claims"] == []
    stored = db_session.get(Report, uuid.UUID(report["id"]))
    assert stored.prompt_version == "reporting_v1" and stored.package["records"]              # the evidence is stored with the report


async def test_when_the_model_is_down_the_findings_are_still_reported(client, weak, grading_env):
    grading_env.use(outage())
    report = (await generate(client, weak["learner"], "learner", force=True)).json()
    assert report["ai_status"] == "unavailable" and report["ai_note"] and report["generated_by"] == "deterministic" and report["claims"]


@pytest.mark.parametrize("scripted,status", [("not json", "invalid"), ({"summary": "x", "claims": "nope"}, "invalid")])
async def test_a_malformed_model_answer_is_reported_and_costs_nothing_but_the_interpretation(client, weak, grading_env, scripted, status):
    grading_env.use(ScriptedAI(reporting=scripted))
    report = (await generate(client, weak["learner"], "learner", force=True)).json()
    assert report["ai_status"] == status and report["claims"] and all(c["source"] == "deterministic" for c in report["claims"])


async def test_a_model_that_invents_evidence_numbers_or_causes_is_refused_claim_by_claim(client, weak, grading_env):
    def lying(package):
        real = package["patterns"][0]
        return {"summary": "Mastery is 91% and the video caused it.", "claims": [
            {"claim": "Mastery is 91%.", "claim_type": "OBSERVATION", "evidence_ids": real["evidence_ids"][:1], "metric_ids": real["metric_ids"], "confidence": 0.9},
            {"claim": "Everyone loves joins.", "claim_type": "OBSERVATION", "evidence_ids": ["evidence_00000000-0000-0000-0000-000000000000"], "metric_ids": [], "confidence": 0.9},
            {"claim": "The remediation video improved mastery.", "claim_type": "CAUSAL_CLAIM", "evidence_ids": real["evidence_ids"][:1], "metric_ids": [], "confidence": 0.9},
            {"claim": "Mastery improved.", "claim_type": "OBSERVATION", "evidence_ids": [], "metric_ids": [], "confidence": 0.9},
            {"claim": real["statement"], "claim_type": real["claim_type"], "evidence_ids": real["evidence_ids"][:2], "metric_ids": real["metric_ids"], "confidence": 0.7}]}
    grading_env.use(ScriptedAI(reporting=lying))
    report = (await generate(client, weak["learner"], "learner", force=True)).json()
    reasons = " | ".join(f for r in report["rejected_claims"] for f in r["flags"])
    assert len(report["rejected_claims"]) == 4 and all(r["status"] == "rejected" for r in report["rejected_claims"])
    assert "91" in reasons and "does not exist" in reasons and "causal" in reasons and "no evidence is cited" in reasons
    assert report["claims"] and "91%" not in " ".join(claim_texts(report))
    assert "91" not in (report["summary"] or "") and "replaced" in (report["ai_note"] or "")            # the unsupported summary was dropped


async def test_a_learners_own_words_cannot_steer_the_reporting_model_out_of_its_fence(client, weak, grading_env, db_session):
    scripted = grading_env.use(ScriptedAI())
    from app.models import EvidenceRecord
    evidence = db_session.query(EvidenceRecord).filter_by(user_id=weak["learner"].id).first()
    assert evidence is not None
    await generate(client, weak["learner"], "learner", force=True)
    prompt = scripted.calls[-1]["user"]
    assert prompt.count("<<<EVIDENCE_START") == 1 and prompt.count("<<<EVIDENCE_END") == 1 and "untrusted" in prompt.lower()


async def test_an_identical_request_reuses_the_stored_report_and_does_not_call_the_model_again(client, weak, grading_env):
    scripted = grading_env.use(ScriptedAI())
    first = (await generate(client, weak["learner"], "learner", force=True)).json()
    calls = len(scripted.calls)
    second = (await generate(client, weak["learner"], "learner")).json()
    assert second["cached"] is True and second["id"] == first["id"] and len(scripted.calls) == calls
    third = (await generate(client, weak["learner"], "learner", force=True)).json()
    assert third["id"] != first["id"] and len(scripted.calls) == calls + 1


async def test_no_model_call_is_made_when_there_is_nothing_to_interpret(client, scene, grading_env):
    scripted = grading_env.use(ScriptedAI())
    await generate(client, scene["learner"], "learner", force=True)
    assert scripted.calls == []


# ==================================================================================================== team
async def test_a_manager_sees_their_team_only_and_names_appear_only_where_they_are_needed(client, weak):
    s = weak
    report = (await generate(client, s["manager"], "team", use_ai=False)).json()
    text = " ".join(claim_texts(report))
    assert report["claims"] and any(c["kind"] == "cohort_gap" for c in report["claims"])
    learners = [m for m in report["metrics"] if m["name"] == "Learners with graded evidence"]
    assert learners[0]["value"] == 1                                       # `other` is on nobody's team
    admin = (await generate(client, s["org_admin"], "team", use_ai=False)).json()
    assert [m for m in admin["metrics"] if m["name"] == "Learners with graded evidence"][0]["value"] == 2
    package = (await client.get(f"{API}/reports/team", headers=auth(s["manager"]))).json()
    assert not any(r["type"] in ("session", "event") for r in package["records"].values())      # no raw activity for a manager
    assert s["other"].full_name not in json.dumps(package) and text


async def test_a_manager_cannot_reach_a_team_they_do_not_manage(client, weak, db_session):
    s = weak
    from app.models import Team
    stranger = Team(id=uuid.uuid4(), org_id=s["org"].id, name="Elsewhere", manager_id=s["ld"].id)
    db_session.add(stranger)
    db_session.commit()
    assert (await generate(client, s["manager"], "team", scope_id=str(stranger.id))).status_code == 404
    assert (await generate(client, s["manager"], "team", scope_id=str(s["team"].id), use_ai=False)).status_code == 200
    assert (await generate(client, s["org_admin"], "team", scope_id=str(stranger.id), use_ai=False)).status_code == 200


async def test_a_stuck_learner_is_named_to_their_manager_with_the_reason(client, weak, db_session):
    s = weak
    for _ in range(2):
        await answer_mc(client, s, [1, 1, 1])
    report = (await generate(client, s["manager"], "team", use_ai=False)).json()
    stuck = [c for c in report["claims"] if c["kind"] == "stuck"]
    assert stuck and s["learner"].full_name in stuck[0]["claim"] and stuck[0]["evidence_ids"]


# ============================================================================================ ld and org
async def test_ld_and_organization_reports_are_for_administrators_and_differ_from_each_other(client, weak):
    s = weak
    for user in (s["manager"], s["learner"]):
        for audience in ("ld", "organization"):
            assert (await generate(client, user, audience)).status_code == 403
    org = (await generate(client, s["ld"], "organization", use_ai=False)).json()
    ld = (await generate(client, s["ld"], "ld", use_ai=False)).json()
    assert org["scope"]["scope_type"] == "organization" and ld["audience"] == "ld" and org["audience"] == "organization"
    assert {c["kind"] for c in org["claims"]} & {"capability_gap", "capability_strength", "coverage_gap", "risk_concentration"}
    assert not {c["kind"] for c in ld["claims"]} & {"capability_gap"}


async def _evidence_at(scene, user, when, signal, org_id):
    engine = create_async_engine(TEST_ASYNC_URL, poolclass=NullPool)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await competency_service.apply(session, competency_service.EvidenceInput(org_id=org_id, user_id=user.id, competency_id=scene["competency"].id, source_type="seed_history",
                                                                                 signal=signal, occurred_at=when), emit_event=False)
        await session.commit()
    await engine.dispose()


async def test_content_effectiveness_is_calculated_reported_as_an_association_and_needs_enough_learners(client, scene, db_session):
    s = scene
    lesson = make_item(db_session, s["org"], s["course"], only_module(db_session, s["course"]), content_type="ARTICLE", title="Joins visual explanation", order_index=9)
    db_session.add(ContentCompetency(content_item_id=lesson.id, competency_id=s["competency"].id, weight=1.0))
    learners = [make_user(db_session, s["org"], ["learner"]) for _ in range(3)]
    for learner in learners:
        enroll(db_session, s["org"], learner, s["course"])
    db_session.commit()
    done_at = datetime.utcnow() - timedelta(days=5)
    for learner in learners:
        db_session.add(ContentProgress(id=uuid.uuid4(), org_id=s["org"].id, user_id=learner.id, content_item_id=lesson.id, status="completed", progress_percent=100.0,
                                       time_spent_seconds=300, completed_at=done_at))
        await _evidence_at(s, learner, done_at - timedelta(days=1), 0.0, s["org"].id)
        await _evidence_at(s, learner, done_at + timedelta(days=1), 1.0, s["org"].id)
        await _evidence_at(s, learner, done_at + timedelta(days=2), 1.0, s["org"].id)
    db_session.commit()
    report = (await generate(client, s["ld"], "ld", use_ai=False)).json()
    claim = next(c for c in report["claims"] if c["kind"] == "content_effectiveness")
    assert claim["claim_type"] == "CORRELATION" and "Joins visual explanation" in claim["claim"] and "higher subsequent mastery" in claim["claim"]
    assert "does not establish" in claim["claim"] and report["rejected_claims"] == []
    delta = next(m for m in report["metrics"] if m["name"].endswith("observed mastery change after completion"))
    assert delta["value"] > 0 and f"{delta['value']:+.2f}" in claim["claim"]

    # with only two exposed learners nothing is claimed about effect
    lone = make_item(db_session, s["org"], s["course"], only_module(db_session, s["course"]), content_type="ARTICLE", title="Rarely opened", order_index=10)
    db_session.add(ContentCompetency(content_item_id=lone.id, competency_id=s["competency"].id, weight=1.0))
    for learner in learners[:2]:
        db_session.add(ContentProgress(id=uuid.uuid4(), org_id=s["org"].id, user_id=learner.id, content_item_id=lone.id, status="completed", progress_percent=100.0,
                                       time_spent_seconds=30, completed_at=done_at))
    db_session.commit()
    again = (await generate(client, s["ld"], "ld", use_ai=False, force=True)).json()
    assert not any("Rarely opened" in c["claim"] for c in again["claims"])


async def test_tenant_isolation_of_reports(client, weak, db_session):
    s = weak
    report = (await generate(client, s["learner"], "learner", use_ai=False)).json()
    foreign = make_user(db_session, make_org(db_session), ["org_admin"])
    db_session.commit()
    assert (await client.get(f"{API}/reports/{report['id']}", headers=auth(foreign))).status_code == 404
    assert (await client.get(f"{API}/reports/{report['id']}/evidence/{report['claims'][0]['evidence_ids'][0]}", headers=auth(foreign))).status_code == 404
    assert (await generate(client, foreign, "learner", scope_id=str(s["learner"].id))).status_code == 404
    org = (await generate(client, foreign, "organization", use_ai=False)).json()
    assert org["claims"] == [] and str(s["org"].id) not in json.dumps(org)
    assert (await client.get(f"{API}/reports/risks", headers=auth(foreign))).status_code == 403 or (await client.get(f"{API}/reports/risks", headers=auth(foreign))).json()["risks"] == []


async def test_a_stored_report_is_visible_only_within_the_remit_that_could_have_asked_for_it(client, weak):
    s = weak
    report = (await generate(client, s["learner"], "learner", use_ai=False)).json()
    assert (await client.get(f"{API}/reports/{report['id']}", headers=auth(s["learner"]))).status_code == 200
    assert (await client.get(f"{API}/reports/{report['id']}", headers=auth(s["org_admin"]))).status_code == 200
    assert (await client.get(f"{API}/reports/{report['id']}", headers=auth(s["other"]))).status_code == 404
    listing = (await client.get(f"{API}/reports", headers=auth(s["learner"]))).json()["items"]
    assert report["id"] in [r["id"] for r in listing]


# ===================================================================================================== BI
async def test_bi_endpoints_return_structured_json_scoped_like_the_reports(client, weak):
    s = weak
    assert (await client.get(f"{API}/reports/organization", headers=auth(s["org_admin"]))).json()["report_scope"]["audience"] == "organization"
    assert (await client.get(f"{API}/reports/organization", headers=auth(s["manager"]))).status_code == 403
    gaps = (await client.get(f"{API}/reports/skill-gaps", headers=auth(s["manager"]))).json()
    assert gaps["learners_with_evidence"] == 1
    assert (await client.get(f"{API}/reports/skill-gaps", headers=auth(s["learner"]))).status_code == 403
    risks = (await client.get(f"{API}/reports/risks", headers=auth(s["manager"]))).json()
    assert "risks" in risks
    analytics = (await client.get(f"{API}/analytics/competencies", headers=auth(s["org_admin"]))).json()
    assert analytics["learners_with_evidence"] == 2
    events = (await client.get(f"{API}/analytics/events", headers=auth(s["learner"]))).json()
    assert events["total_events"] > 0
    org = (await client.get(f"{API}/analytics/organization", headers=auth(s["org_admin"]))).json()
    assert org["organization_mastery_index"] is not None and org["total_users"] >= 5


async def test_bi_evidence_lookup_is_scoped(client, weak, db_session):
    from app.models import EvidenceRecord
    s = weak
    mine = db_session.query(EvidenceRecord).filter_by(user_id=s["learner"].id).first()
    theirs = db_session.query(EvidenceRecord).filter_by(user_id=s["other"].id).first()
    ids = f"{mine.id},{theirs.id}"
    assert [e["id"] for e in (await client.get(f"{API}/reports/evidence", headers=auth(s["manager"]), params={"ids": ids})).json()["evidence"]] == [str(mine.id)]
    assert len((await client.get(f"{API}/reports/evidence", headers=auth(s["org_admin"]), params={"ids": ids})).json()["evidence"]) == 2
    assert (await client.get(f"{API}/reports/evidence", headers=auth(s["org_admin"]), params={"ids": "nope"})).status_code == 422


# ================================================================================================= digests
async def test_a_scheduled_digest_is_generated_from_real_data_and_stored(client, weak, grading_env):
    s = weak
    grading_env.use(ScriptedAI())
    created = await client.post(f"{API}/reports/schedules", headers=auth(s["manager"]), json={"title": "Weekly team digest", "audience": "team", "cadence": "weekly"})
    assert created.status_code == 201 and created.json()["cadence"] == "weekly"
    listed = (await client.get(f"{API}/reports/schedules", headers=auth(s["manager"]))).json()["items"]
    assert len(listed) == 1 and (await client.get(f"{API}/reports/schedules", headers=auth(s["org_admin"]))).json()["items"] == []
    ran = (await client.post(f"{API}/reports/schedules/{created.json()['id']}/run", headers=auth(s["manager"]))).json()
    assert ran["status"] == "success" and ran["report_id"]
    digests = (await client.get(f"{API}/reports/digests", headers=auth(s["manager"]))).json()["items"]
    assert digests and "Weekly team digest" in digests[0]["content"] and "below" in digests[0]["content"] and digests[0]["report_id"] == ran["report_id"]
    assert (await client.get(f"{API}/reports/digests", headers=auth(s["org_admin"]))).json()["items"] == []
    assert (await client.post(f"{API}/reports/schedules/{created.json()['id']}/run", headers=auth(s["org_admin"]))).status_code == 404
    latest = (await client.get(f"{API}/reports/digest/latest", headers=auth(s["manager"]))).json()
    assert latest["id"] == digests[0]["id"]


async def test_you_can_only_schedule_what_you_may_ask_for_and_due_schedules_run(client, weak, db_session):
    s = weak
    assert (await client.post(f"{API}/reports/schedules", headers=auth(s["manager"]), json={"title": "Org capability", "audience": "organization", "cadence": "monthly"})).status_code == 403
    assert (await client.post(f"{API}/reports/schedules", headers=auth(s["learner"]), json={"title": "Team digest", "audience": "team", "cadence": "weekly"})).status_code == 403
    made = (await client.post(f"{API}/reports/schedules", headers=auth(s["ld"]), json={"title": "Org capability", "audience": "organization", "cadence": "monthly"})).json()
    from app.models import ScheduledReport
    row = db_session.get(ScheduledReport, uuid.UUID(made["id"]))
    row.next_run_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()
    ran = (await client.post(f"{API}/reports/schedules/run-due", headers=auth(s["ld"]))).json()["ran"]
    assert [r["schedule_id"] for r in ran] == [made["id"]] and ran[0]["status"] == "success"
    assert (await client.post(f"{API}/reports/schedules/run-due", headers=auth(s["manager"]))).status_code == 403


# ================================================================================================== widget
async def test_the_embed_token_is_scoped_expiring_and_useless_as_a_login(client, weak, db_session):
    s = weak
    minted = await client.post(f"{API}/embed/tokens", headers=auth(s["manager"]), json={"report": "skill-gaps", "scope": "team", "scope_id": str(s["team"].id)})
    assert minted.status_code == 201 and "adaptive-reporting.js" in minted.json()["snippet"]
    token = minted.json()["token"]
    data = (await client.get(f"{API}/embed/data", params={"token": token})).json()
    assert data["report"] == "skill-gaps" and data["data"]["learners_with_evidence"] == 1
    assert (await client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await client.get(f"{API}/reports/organization", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": token})).status_code == 401
    assert (await client.get(f"{API}/embed/data", params={"token": token + "x"})).status_code == 401
    assert (await client.get(f"{API}/embed/data", params={"token": auth(s["manager"])["Authorization"].split()[1]})).status_code == 401      # an access token is not an embed token
    summary = (await client.post(f"{API}/embed/tokens", headers=auth(s["manager"]), json={"report": "summary", "scope": "team"})).json()["token"]
    findings = (await client.get(f"{API}/embed/data", params={"token": summary})).json()["data"]["findings"]
    assert findings and all("statement" in f and f["evidence"] >= 0 for f in findings)


async def test_embed_tokens_are_refused_beyond_the_issuers_remit_and_die_with_the_issuer(client, weak, db_session):
    s = weak
    assert (await client.post(f"{API}/embed/tokens", headers=auth(s["manager"]), json={"report": "summary", "scope": "organization"})).status_code == 403
    assert (await client.post(f"{API}/embed/tokens", headers=auth(s["learner"]), json={"report": "skill-gaps", "scope": "team"})).status_code in (403, 404)
    assert (await client.post(f"{API}/embed/tokens", headers=auth(s["learner"]), json={"report": "summary", "scope": "learner", "scope_id": str(s["other"].id)})).status_code == 404
    assert (await client.post(f"{API}/embed/tokens", headers=auth(s["manager"]), json={"report": "everything", "scope": "team"})).status_code == 422
    token = (await client.post(f"{API}/embed/tokens", headers=auth(s["org_admin"]), json={"report": "risks", "scope": "organization"})).json()["token"]
    assert (await client.get(f"{API}/embed/data", params={"token": token})).status_code == 200
    s["org_admin"].is_active = False
    db_session.merge(s["org_admin"])
    db_session.commit()
    assert (await client.get(f"{API}/embed/data", params={"token": token})).status_code == 401


async def test_the_widget_script_is_served_and_the_unauthenticated_legacy_endpoint_is_gone(client, weak):
    script = await client.get(f"{API}/embed/adaptive-reporting.js")
    assert script.status_code == 200 and "customElements.define('adaptive-report'" in script.text and "javascript" in script.headers["content-type"]
    legacy = await client.get(f"{API}/embed/report", params={"learner_id": str(weak["learner"].id), "org_id": str(weak["org"].id), "format": "json"})
    assert legacy.status_code in (404, 405)
