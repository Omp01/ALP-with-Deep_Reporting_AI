"""
Automated tests for AI Competency Derivation and Assessment Item Generation.
"""

import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"


async def get_auth_token(email: str, password: str = "Password123!") -> str:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200
        return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_derive_competencies_from_text():
    instructor_token = await get_auth_token("sarah.instructor@acme.com")

    syllabus_text = (
        "In this advanced course on Distributed Systems, learners will master leader election, "
        "replicated state machines using the Raft consensus algorithm, and quorum consistency. "
        "Furthermore, students will design distributed event-streaming backbones using Redis Streams "
        "and Kafka consumer groups to guarantee fault tolerance."
    )

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        resp = await client.post(
            "/ai/derive-competencies",
            headers={"Authorization": f"Bearer {instructor_token}"},
            json={"text": syllabus_text, "save_to_course": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "derived_competencies" in data
        assert len(data["derived_competencies"]) >= 1
        first_comp = data["derived_competencies"][0]
        assert "name" in first_comp
        assert "code" in first_comp
        assert "taxonomy_level" in first_comp


@pytest.mark.asyncio
async def test_generate_assessments_and_review_workflow():
    instructor_token = await get_auth_token("sarah.instructor@acme.com")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Fetch existing course, module, and competency
        courses_resp = await client.get("/courses", headers={"Authorization": f"Bearer {instructor_token}"})
        course = [c for c in courses_resp.json() if c.get("modules") and len(c["modules"]) > 0][0]
        module_id = course["modules"][0]["id"]

        comp_resp = await client.get("/competencies", headers={"Authorization": f"Bearer {instructor_token}"})
        competency_id = comp_resp.json()[0]["id"]

        # 2. Generate assessment items
        gen_resp = await client.post(
            "/ai/generate-assessments",
            headers={"Authorization": f"Bearer {instructor_token}"},
            json={
                "module_id": module_id,
                "competency_id": competency_id,
                "count": 2,
                "auto_approve": False,
            },
        )
        assert gen_resp.status_code == 201
        items = gen_resp.json()
        assert len(items) == 2
        item = items[0]
        assert item["is_ai_generated"] is True
        assert item["quality_flag"] == "flagged"
        assert item["difficulty_score"] > 0
        assert item["discrimination_index"] > 0
        assert len(item["options"]) == 4

        # 3. Instructor review item (approve it)
        review_resp = await client.put(
            f"/ai/assessments/{item['id']}/review",
            headers={"Authorization": f"Bearer {instructor_token}"},
            json={"quality_flag": "approved"},
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["quality_flag"] == "approved"

        # 4. List items with filters
        list_resp = await client.get(
            f"/ai/assessments?is_ai_generated=true&quality_flag=approved",
            headers={"Authorization": f"Bearer {instructor_token}"},
        )
        assert list_resp.status_code == 200
        approved_items = list_resp.json()
        assert any(i["id"] == item["id"] for i in approved_items)
