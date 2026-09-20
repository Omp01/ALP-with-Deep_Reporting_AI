"""
Tenant isolation (spec §35): Organization A cannot reach Organization B's data.

Method: two fully populated tenants exist (see the `world` fixture). Every request
below is made by the MOST privileged non-platform user of tenant A (an org admin),
so a 404 can only come from tenant scoping, never from a missing role.

A request for another tenant's resource must look identical to a request for a
resource that does not exist (404), so identifiers cannot be probed across tenants.

Covered here: users, roles, courses, modules, content, competencies, prerequisites,
the skill graph, enrollments, progress, the learner overview/player/home, quizzes
(assessments) and events.

Not covered yet, because the features do not exist in the API service: competency
states, evidence records and reports are served by the adaptive/reporting services
and are rebuilt in Phases 5 and 7 — their isolation tests ship with them.
"""

import uuid
from datetime import datetime

import pytest

from app.models import LearningEvent, Quiz
from tests.foundation.conftest import API, auth, make_user, token_for

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Every write or read of a foreign resource by id is a 404
# ---------------------------------------------------------------------------
def _foreign_resource_requests(b):
    """(label, method, path, json) — all address tenant B's resources."""
    comp_b = b.competencies[0]
    other_comp_b = b.competencies[1]
    return [
        ("get course", "GET", f"/courses/{b.course.id}", None),
        ("update course", "PUT", f"/courses/{b.course.id}", {"title": "hijacked"}),
        ("publish course", "POST", f"/courses/{b.course.id}/publish", None),
        ("enroll in course", "POST", f"/courses/{b.course.id}/enroll", None),
        ("list course modules", "GET", f"/courses/{b.course.id}/modules", None),
        ("create module", "POST", f"/courses/{b.course.id}/modules", {"title": "injected"}),
        ("get module", "GET", f"/modules/{b.module.id}", None),
        ("create content", "POST", f"/modules/{b.module.id}/content", {"title": "injected", "content_type": "VIDEO"}),
        ("get content", "GET", f"/content/{b.content.id}", None),
        ("get competency", "GET", f"/competencies/{comp_b.id}", None),
        ("update competency", "PUT", f"/competencies/{comp_b.id}", {"name": "hijacked"}),
        ("list prerequisites", "GET", f"/competencies/{comp_b.id}/prerequisites", None),
        ("add prerequisite (both foreign)", "POST", f"/competencies/{comp_b.id}/prerequisites",
         {"prerequisite_id": str(other_comp_b.id)}),
        ("remove prerequisite", "DELETE", f"/competencies/{comp_b.id}/prerequisites/{other_comp_b.id}", None),
        ("map course competency", "POST", f"/courses/{b.course.id}/competencies", {"competency_id": str(comp_b.id)}),
        ("get user", "GET", f"/users/{b.learner.id}", None),
        ("get user roles", "GET", f"/users/{b.learner.id}/roles", None),
        ("set user roles", "PUT", f"/users/{b.learner.id}/roles", {"roles": ["org_admin"]}),
        ("learning course overview", "GET", f"/learning/courses/{b.course.id}", None),
        ("learning player payload", "GET", f"/learning/content/{b.content.id}", None),
        ("learning content file", "GET", f"/learning/content/{b.content.id}/file", None),
        ("record progress", "POST", f"/progress/content/{b.content.id}",
         {"status": "in_progress", "progress_percent": 10, "time_spent_seconds": 5}),
        ("course progress", "GET", f"/progress/course/{b.course.id}", None),
    ]


def _labels(b_factory):
    return [item[0] for item in b_factory]


@pytest.mark.parametrize("index", range(23))
async def test_foreign_resources_are_not_found(client, world, index):
    requests = _foreign_resource_requests(world.b)
    assert len(requests) == 23, "update the parametrize range when adding cases"
    label, method, path, body = requests[index]
    resp = await client.request(method, f"{API}{path}", json=body, headers=auth(world.a.org_admin))
    assert resp.status_code == 404, f"{label}: expected 404, got {resp.status_code} {resp.text[:200]}"


async def test_cannot_attach_a_foreign_competency_as_prerequisite_of_your_own(client, world):
    own, foreign = world.a.competencies[0], world.b.competencies[0]
    for competency, prerequisite in ((own, foreign), (foreign, own)):
        resp = await client.post(
            f"{API}/competencies/{competency.id}/prerequisites",
            json={"prerequisite_id": str(prerequisite.id)},
            headers=auth(world.a.org_admin),
        )
        assert resp.status_code == 404


async def test_cannot_map_a_foreign_competency_onto_your_own_course(client, world):
    resp = await client.post(
        f"{API}/courses/{world.a.course.id}/competencies",
        json={"competency_id": str(world.b.competencies[0].id)},
        headers=auth(world.a.org_admin),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Listings never leak the other tenant's rows
# ---------------------------------------------------------------------------
async def test_course_listing_contains_only_own_tenant(client, world):
    ids = {c["id"] for c in (await client.get(f"{API}/courses", headers=auth(world.a.learner))).json()}
    assert str(world.a.course.id) in ids
    assert str(world.b.course.id) not in ids


async def test_user_listing_contains_only_own_tenant(client, world):
    users = (await client.get(f"{API}/users", params={"limit": 100}, headers=auth(world.a.org_admin))).json()
    assert users, "sanity: tenant A has users"
    assert {u["org_id"] for u in users} == {str(world.a.org.id)}
    assert str(world.b.learner.id) not in {u["id"] for u in users}


async def test_competency_listing_and_graph_contain_only_own_tenant(client, world):
    headers = auth(world.a.learner)
    listed = {c["id"] for c in (await client.get(f"{API}/competencies", headers=headers)).json()}
    graph = {n["id"] for n in (await client.get(f"{API}/competencies/graph", headers=headers)).json()["nodes"]}
    foreign = {str(c.id) for c in world.b.competencies}
    assert listed and graph
    assert not (listed & foreign) and not (graph & foreign)


async def test_learner_home_never_recommends_another_tenants_course(client, world):
    home = (await client.get(f"{API}/learning/home", headers=auth(world.a.learner))).json()
    recommended = {r["course_id"] for r in home["recommendations"]}
    assert str(world.a.course.id) in recommended  # sanity: own tenant's course is offered
    assert str(world.b.course.id) not in recommended


async def test_foreign_progress_rows_never_appear_in_own_progress(client, world, db_session):
    """Reporting progress in tenant B must not change anything tenant A can see."""
    resp = await client.post(
        f"{API}/progress/content/{world.b.content.id}",
        json={"status": "completed", "progress_percent": 100, "time_spent_seconds": 5},
        headers=auth(world.b.learner),
    )
    assert resp.status_code == 200
    home = (await client.get(f"{API}/learning/home", headers=auth(world.a.learner))).json()
    assert home["stats"]["completed_items"] == 0 and home["recent_activity"] == []


async def test_role_filtered_user_listing_stays_in_tenant(client, world):
    resp = await client.get(f"{API}/users", params={"role": "learner"}, headers=auth(world.a.org_admin))
    assert str(world.b.learner.id) not in {u["id"] for u in resp.json()}


# ---------------------------------------------------------------------------
# Tenant identity comes from the authenticated user, never from the client
# ---------------------------------------------------------------------------
async def test_x_tenant_id_header_is_ignored_for_ordinary_users(client, world):
    headers = {**auth(world.a.org_admin), "X-Tenant-ID": str(world.b.org.id)}
    ids = {c["id"] for c in (await client.get(f"{API}/courses", headers=headers)).json()}
    assert str(world.a.course.id) in ids and str(world.b.course.id) not in ids
    assert (await client.get(f"{API}/courses/{world.b.course.id}", headers=headers)).status_code == 404


async def test_x_tenant_id_header_is_honoured_only_for_super_admin(client, world):
    headers = {**auth(world.super_admin), "X-Tenant-ID": str(world.b.org.id)}
    ids = {c["id"] for c in (await client.get(f"{API}/courses", headers=headers)).json()}
    assert str(world.b.course.id) in ids and str(world.a.course.id) not in ids


async def test_forged_org_claim_in_the_token_is_ignored(client, world):
    """The org_id claim in a JWT is informational; the database row decides the tenant."""
    from app.core.security import create_access_token

    forged = create_access_token(
        subject=str(world.a.org_admin.id), claims={"org_id": str(world.b.org.id), "role": "system_admin"}
    )
    resp = await client.get(f"{API}/courses/{world.b.course.id}", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 404
    listing = (await client.get(f"{API}/courses", headers={"Authorization": f"Bearer {forged}"})).json()
    assert str(world.b.course.id) not in {c["id"] for c in listing}


async def test_forged_role_claim_in_the_token_grants_nothing(client, world):
    from app.core.security import create_access_token

    forged = create_access_token(subject=str(world.a.learner.id), claims={"role": "org_admin"})
    resp = await client.put(
        f"{API}/users/{world.a.manager.id}/roles", json={"roles": ["org_admin"]},
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Assessments and events
# ---------------------------------------------------------------------------
@pytest.fixture
def foreign_quiz(db_session, world):
    quiz = Quiz(org_id=world.b.org.id, course_id=world.b.course.id, module_id=world.b.module.id, title="B's quiz")
    db_session.add(quiz)
    db_session.commit()
    return quiz


@pytest.mark.parametrize("method, suffix", [("GET", ""), ("GET", "/questions"), ("POST", "/attempts"), ("GET", "/attempts")])
async def test_foreign_quiz_is_not_reachable(client, world, foreign_quiz, method, suffix):
    resp = await client.request(method, f"{API}/quizzes/{foreign_quiz.id}{suffix}", headers=auth(world.a.learner))
    if suffix == "/attempts" and method == "GET":
        assert resp.status_code == 200 and resp.json() == []  # own attempts only; there are none
    else:
        assert resp.status_code == 404


async def test_quiz_summary_never_lists_foreign_quizzes(client, world, foreign_quiz):
    rows = (await client.get(f"{API}/quizzes/learner/summary", headers=auth(world.a.learner))).json()
    assert str(foreign_quiz.id) not in {r["quiz_id"] for r in rows}


@pytest.fixture
def foreign_event(db_session, world):
    event = LearningEvent(
        id=uuid.uuid4(), org_id=world.b.org.id, user_id=world.b.learner.id, course_id=world.b.course.id,
        event_type="content_started", payload={}, timestamp=datetime.utcnow(),
    )
    db_session.add(event)
    db_session.commit()
    return event


async def test_events_query_never_returns_foreign_events(client, world, foreign_event):
    for user in (world.a.org_admin, world.a.manager, world.a.learner):
        resp = await client.get(f"{API}/events", params={"user_id": str(world.b.learner.id)}, headers=auth(user))
        assert resp.status_code == 200
        assert str(foreign_event.id) not in {e["id"] for e in resp.json()["items"]}


async def test_event_stats_are_scoped_to_the_tenant(client, world, foreign_event):
    resp = await client.get(f"{API}/events/stats", headers=auth(world.a.org_admin))
    assert resp.status_code == 200
    assert resp.json()["breakdown"].get("content_started", 0) == 0


async def test_event_keys_do_not_collide_across_tenants(client, world, db_session):
    """Audit R7 (fixed in Phase 4): another tenant holding the same idempotency key must not suppress this tenant's event."""
    key = f"shared-key-{uuid.uuid4()}"
    db_session.add(LearningEvent(
        id=uuid.uuid4(), org_id=world.b.org.id, user_id=world.b.learner.id, course_id=world.b.course.id,
        event_type="content_started", payload={}, timestamp=datetime.utcnow(), idempotency_key=f"{world.b.learner.id}:{key}",
    ))
    db_session.add(LearningEvent(
        id=uuid.uuid4(), org_id=world.b.org.id, user_id=world.b.learner.id, course_id=world.b.course.id,
        event_type="content_started", payload={}, timestamp=datetime.utcnow(), idempotency_key=key,
    ))
    db_session.commit()
    resp = await client.post(
        f"{API}/events",
        json={"idempotency_key": key, "event_type": "lesson_opened", "content_id": str(world.a.content.id)},
        headers=auth(world.a.learner),
    )
    assert resp.status_code == 201 and resp.json()["status"] == "ingested"


async def test_a_foreign_event_id_is_not_readable(client, world, foreign_event):
    for user in (world.a.org_admin, world.a.learner):
        assert (await client.get(f"{API}/events/{foreign_event.id}", headers=auth(user))).status_code == 404


# ---------------------------------------------------------------------------
# Role-based limits inside a tenant still hold
# ---------------------------------------------------------------------------
async def test_learner_cannot_read_other_learners_profile_or_roles(client, world, db_session):
    peer = make_user(db_session, world.a.org, ["learner"])
    db_session.commit()
    assert (await client.get(f"{API}/users/{peer.id}", headers=auth(world.a.learner))).status_code == 403
    assert (await client.get(f"{API}/users/{peer.id}/roles", headers=auth(world.a.learner))).status_code == 403


async def test_unauthenticated_requests_are_rejected_everywhere(client, world):
    for path in ("/courses", "/users", "/competencies", "/competencies/graph", "/roles"):
        assert (await client.get(f"{API}{path}")).status_code == 401, path


async def test_token_for_a_deactivated_user_is_rejected(client, world, db_session):
    victim = make_user(db_session, world.a.org, ["learner"])
    victim.is_active = False
    db_session.commit()
    resp = await client.get(f"{API}/courses", headers={"Authorization": f"Bearer {token_for(victim)}"})
    assert resp.status_code == 403
