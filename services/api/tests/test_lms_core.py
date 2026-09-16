"""
Automated tests for LMS Core: Courses, Modules, Content, Competencies, and Enrollments.
"""

import pytest
import httpx
import uuid

BASE_URL = "http://localhost:8000/api/v1"


async def get_auth_token(email: str, password: str = "Password123!") -> str:
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200
        return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_courses():
    token = await get_auth_token("sarah.instructor@acme.com")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.get("/courses", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        courses = resp.json()
        assert len(courses) >= 1
        assert any(c["code"] == "PY-DIST-101" for c in courses)


@pytest.mark.asyncio
async def test_create_and_publish_course():
    token = await get_auth_token("sarah.instructor@acme.com")
    unique_code = f"TEST-{uuid.uuid4().hex[:6].upper()}"
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Create course
        create_resp = await client.post(
            "/courses",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Cloud-Native Microservices in Go",
                "code": unique_code,
                "description": "Architecting high-performance distributed systems in Go.",
                "status": "draft",
            },
        )
        assert create_resp.status_code == 201
        course = create_resp.json()
        course_id = course["id"]
        assert course["status"] == "draft"

        # Publish course
        publish_resp = await client.post(
            f"/courses/{course_id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert publish_resp.status_code == 200
        assert publish_resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_create_module_and_content_item():
    token = await get_auth_token("sarah.instructor@acme.com")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Get existing course
        courses_resp = await client.get("/courses", headers={"Authorization": f"Bearer {token}"})
        course_id = courses_resp.json()[0]["id"]

        # Add module
        mod_resp = await client.post(
            f"/courses/{course_id}/modules",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Introduction to Goroutines and Channels",
                "description": "CSP concurrency model fundamentals.",
                "sequence_order": 99,
                "estimated_duration_mins": 40,
            },
        )
        assert mod_resp.status_code == 201
        module_id = mod_resp.json()["id"]

        # Add content item
        content_resp = await client.post(
            f"/modules/{module_id}/content",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Channels vs Mutexes Deep Dive",
                "content_type": "text",
                "raw_text": "Do not communicate by sharing memory; instead, share memory by communicating.",
            },
        )
        assert content_resp.status_code == 201
        assert content_resp.json()["content_type"] == "text"


@pytest.mark.asyncio
async def test_competencies_and_course_mapping():
    token = await get_auth_token("admin@acme.com")
    unique_comp_code = f"COMP-{uuid.uuid4().hex[:6].upper()}"
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Create competency
        comp_resp = await client.post(
            "/competencies",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Distributed Consensus Algorithms",
                "code": unique_comp_code,
                "description": "Raft, Paxos, and quorum-based state machine replication.",
                "taxonomy_level": "evaluate",
            },
        )
        assert comp_resp.status_code == 201
        comp_id = comp_resp.json()["id"]

        # Map to course
        courses = (await client.get("/courses", headers={"Authorization": f"Bearer {token}"})).json()
        course_id = courses[0]["id"]

        map_resp = await client.post(
            f"/courses/{course_id}/competencies",
            headers={"Authorization": f"Bearer {token}"},
            json={"competency_id": comp_id, "target_mastery": 0.85, "is_primary": True},
        )
        assert map_resp.status_code == 201


@pytest.mark.asyncio
async def test_learner_enrollment_and_progress_flow():
    instructor_token = await get_auth_token("sarah.instructor@acme.com")
    learner_token = await get_auth_token("alice.learner@acme.com")

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Create a fresh course
        fresh_code = f"ENROLL-{uuid.uuid4().hex[:6].upper()}"
        course_resp = await client.post(
            "/courses",
            headers={"Authorization": f"Bearer {instructor_token}"},
            json={"title": "Interactive Systems", "code": fresh_code, "status": "published"},
        )
        course_id = course_resp.json()["id"]

        # Learner enrolls
        enroll_resp = await client.post(
            "/enrollments",
            headers={"Authorization": f"Bearer {learner_token}"},
            json={"course_id": course_id},
        )
        assert enroll_resp.status_code == 201
        enrollment_id = enroll_resp.json()["id"]
        assert enroll_resp.json()["progress_pct"] == 0.0

        # Learner updates progress
        progress_resp = await client.put(
            f"/enrollments/{enrollment_id}/progress",
            headers={"Authorization": f"Bearer {learner_token}"},
            json={"progress_pct": 100.0},
        )
        assert progress_resp.status_code == 200
        assert progress_resp.json()["progress_pct"] == 100.0
        assert progress_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_rbac_learner_cannot_create_course():
    learner_token = await get_auth_token("alice.learner@acme.com")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/courses",
            headers={"Authorization": f"Bearer {learner_token}"},
            json={"title": "Hacker Course", "code": "HACK-101"},
        )
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]
