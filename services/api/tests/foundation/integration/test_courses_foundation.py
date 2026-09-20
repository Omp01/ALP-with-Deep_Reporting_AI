"""Course and content model: no fabricated values, real derived fields, complete persistence."""

import pytest

from app.models import Enrollment
from tests.foundation.conftest import API, auth, make_course, make_org, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def tenant(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    db_session.commit()
    return org, ld, learner


async def test_rating_is_null_when_no_ratings_exist(client, tenant, db_session):
    org, ld, learner = tenant
    course = make_course(db_session, org, ld)
    db_session.commit()
    body = (await client.get(f"{API}/courses/{course.id}", headers=auth(learner))).json()
    assert body["rating"] is None  # never a placeholder like 4.8


async def test_duration_is_computed_from_content_rounded_up(client, tenant, db_session):
    org, ld, learner = tenant
    course = make_course(db_session, org, ld, content_seconds=[600, 601])  # 1201 s -> 21 min
    db_session.commit()
    body = (await client.get(f"{API}/courses/{course.id}", headers=auth(learner))).json()
    assert body["duration_minutes"] == 21


async def test_duration_is_null_when_content_has_no_recorded_length(client, tenant, db_session):
    org, ld, learner = tenant
    course = make_course(db_session, org, ld, content_seconds=[0, 0])
    db_session.commit()
    body = (await client.get(f"{API}/courses/{course.id}", headers=auth(learner))).json()
    assert body["duration_minutes"] is None


async def test_explicit_author_duration_overrides_computed(client, tenant, db_session):
    org, ld, learner = tenant
    created = await client.post(
        f"{API}/courses", json={"title": "Timed", "code": "TIMED-1", "duration_minutes": 90}, headers=auth(ld)
    )
    assert created.status_code == 201 and created.json()["duration_minutes"] == 90


async def test_new_course_has_no_rating_and_ignores_client_supplied_one(client, tenant):
    _, ld, _ = tenant
    resp = await client.post(
        f"{API}/courses", json={"title": "Rated?", "code": "RATE-1", "rating": 5.0}, headers=auth(ld)
    )
    assert resp.status_code == 201
    assert resp.json()["rating"] is None


async def test_enrollment_count_is_real_and_drives_popular_sort(client, tenant, db_session):
    org, ld, learner = tenant
    quiet = make_course(db_session, org, ld)
    popular = make_course(db_session, org, ld)
    others = [make_user(db_session, org, ["learner"]) for _ in range(2)]
    for user in [learner, *others]:
        db_session.add(Enrollment(user_id=user.id, org_id=org.id, course_id=popular.id, status="active"))
    db_session.commit()

    listing = (await client.get(f"{API}/courses", params={"sort_by": "popular"}, headers=auth(learner))).json()
    counts = {c["id"]: c["enrollment_count"] for c in listing}
    assert counts[str(popular.id)] == 3
    assert counts[str(quiet.id)] == 0
    assert listing[0]["id"] == str(popular.id)


async def test_content_creation_persists_every_field_and_course_id(client, tenant, db_session):
    org, ld, _ = tenant
    course = make_course(db_session, org, ld, content_seconds=[])
    from app.models import Module

    module_id = db_session.query(Module).filter_by(course_id=course.id).one().id
    db_session.commit()

    resp = await client.post(
        f"{API}/modules/{module_id}/content",
        json={
            "title": "SQL Joins Explained", "description": "Visual walkthrough", "content_type": "video",
            "content_url": "https://www.youtube.com/watch?v=abc123", "duration_seconds": 754, "order_index": 3,
            "status": "review", "source_type": "youtube", "source_url": "https://www.youtube.com/watch?v=abc123",
        },
        headers=auth(ld),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["course_id"] == str(course.id)
    assert body["content_type"] == "VIDEO"  # normalised to the stored vocabulary
    assert (body["description"], body["duration_seconds"], body["order_index"]) == ("Visual walkthrough", 754, 3)
    assert (body["status"], body["source_type"]) == ("review", "youtube")
    assert body["analysis"] is None


@pytest.mark.parametrize("field, value", [("status", "bogus"), ("source_type", "carrier-pigeon"), ("duration_seconds", -5)])
async def test_content_creation_validates_fields(client, tenant, db_session, field, value):
    org, ld, _ = tenant
    course = make_course(db_session, org, ld, content_seconds=[])
    from app.models import Module

    module_id = db_session.query(Module).filter_by(course_id=course.id).one().id
    db_session.commit()
    resp = await client.post(
        f"{API}/modules/{module_id}/content",
        json={"title": "x", "content_type": "VIDEO", field: value},
        headers=auth(ld),
    )
    assert resp.status_code == 422


async def test_course_update_now_applies_category_difficulty_and_duration(client, tenant, db_session):
    org, ld, _ = tenant
    course = make_course(db_session, org, ld)
    db_session.commit()
    resp = await client.put(
        f"{API}/courses/{course.id}",
        json={"category": "Data", "difficulty": "advanced", "duration_minutes": 45},
        headers=auth(ld),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["category"], body["difficulty"], body["duration_minutes"]) == ("Data", "advanced", 45)
