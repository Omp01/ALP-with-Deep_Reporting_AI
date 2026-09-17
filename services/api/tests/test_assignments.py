"""
Tests for Assignments and Hands-on Labs API.
Verifies assignment creation, retrieval, student submissions, and instructor grading with rubrics.
"""

import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"


@pytest.mark.asyncio
async def test_assignments_workflow():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Login as Admin/Instructor
        admin_login = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Login as Learner
        learner_login = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        assert learner_login.status_code == 200
        learner_token = learner_login.json()["access_token"]
        learner_headers = {"Authorization": f"Bearer {learner_token}"}

        # 3. Fetch courses to get module_id
        res = await client.get("/courses", headers=admin_headers)
        assert res.status_code == 200
        courses = res.json()
        valid_courses = [c for c in courses if c.get("modules") and len(c["modules"]) > 0]
        assert len(valid_courses) > 0
        course = valid_courses[0]
        module = course["modules"][0]

        # 4. Create Assignment as Org Admin / Instructor
        assign_payload = {
            "course_id": course["id"],
            "module_id": module["id"],
            "title": "Build an Async Task Queue in Python",
            "instructions": "Implement a worker queue using asyncio.Queue with backpressure and graceful cancellation.",
            "difficulty": "advanced",
            "max_score": 100.0,
            "rubric": {
                "concurrency_handling": {"weight": 0.4, "max": 40},
                "error_resilience": {"weight": 0.3, "max": 30},
                "code_style": {"weight": 0.3, "max": 30},
            },
            "status": "published",
        }
        create_res = await client.post("/assignments", json=assign_payload, headers=admin_headers)
        assert create_res.status_code == 201
        assign_data = create_res.json()
        assign_id = assign_data["id"]
        assert assign_data["title"] == "Build an Async Task Queue in Python"

        # 5. List assignments as learner
        list_res = await client.get(f"/assignments?course_id={course['id']}", headers=learner_headers)
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1

        # 6. Learner submits practical work
        sub_payload = {
            "assignment_id": assign_id,
            "submission_text": "class WorkerPool:\n    def __init__(self):\n        self.queue = asyncio.Queue(maxsize=100)",
            "submission_url": "https://github.com/alice/async-worker-lab",
        }
        sub_res = await client.post(f"/assignments/{assign_id}/submit", json=sub_payload, headers=learner_headers)
        assert sub_res.status_code == 201
        sub_data = sub_res.json()
        sub_id = sub_data["id"]
        assert sub_data["status"] == "SUBMITTED"

        # 7. Instructor grades submission
        grade_payload = {
            "score": 92.5,
            "feedback": "Excellent async cancellation handling and worker pool isolation.",
            "rubric_scores": {
                "concurrency_handling": 38,
                "error_resilience": 28,
                "code_style": 26.5,
            },
            "is_ai_graded": False,
        }
        grade_res = await client.post(f"/assignments/submissions/{sub_id}/grade", json=grade_payload, headers=admin_headers)
        assert grade_res.status_code == 200
        graded_data = grade_res.json()
        assert graded_data["status"] == "GRADED"
        assert graded_data["score"] == 92.5
