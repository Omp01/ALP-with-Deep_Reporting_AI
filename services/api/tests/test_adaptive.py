"""
Automated tests for Adaptive Engine Integration, Competency Modelling, and Skill-Gap Detection.
"""

import pytest
import httpx
import uuid

BASE_URL = "http://localhost:8000/api/v1"


@pytest.mark.asyncio
async def test_adaptive_next_step_learner():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # 1. Login as Alice (learner)
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        assert login_res.status_code == 200
        alice = login_res.json()
        alice_token = alice["access_token"]
        alice_id = alice["user"]["id"]
        headers = {"Authorization": f"Bearer {alice_token}"}

        # 2. Get list of courses to select a course ID
        courses_res = await client.get("/courses", headers=headers)
        assert courses_res.status_code == 200
        courses = courses_res.json()
        assert len(courses) > 0
        course_id = courses[0]["id"]

        # 3. Request next adaptive recommendation
        payload = {
            "session_id": str(uuid.uuid4()),
            "course_id": course_id,
        }
        next_res = await client.post("/adaptive/next", json=payload, headers=headers)
        assert next_res.status_code == 200
        rec = next_res.json()

        assert "decision" in rec
        assert rec["decision"] in ["remediate", "continue", "advance", "skip", "change_modality", "revisit"]
        assert "reason" in rec
        assert "adaptation_type" in rec


@pytest.mark.asyncio
async def test_adaptive_decisions_audit():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Login as Alice
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        alice = login_res.json()
        headers = {"Authorization": f"Bearer {alice['access_token']}"}
        alice_id = alice["user"]["id"]

        # Fetch decisions
        decisions_res = await client.get(f"/adaptive/decisions/{alice_id}", headers=headers)
        assert decisions_res.status_code == 200
        decisions = decisions_res.json()
        assert isinstance(decisions, list)
        assert len(decisions) >= 1
        assert "decision" in decisions[0]
        assert "reason" in decisions[0]


@pytest.mark.asyncio
async def test_learner_competency_states():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Login as Alice
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        alice = login_res.json()
        headers = {"Authorization": f"Bearer {alice['access_token']}"}
        alice_id = alice["user"]["id"]

        # Query competencies
        res = await client.get(f"/adaptive/competencies/{alice_id}", headers=headers)
        assert res.status_code == 200
        comps = res.json()
        assert isinstance(comps, list)
        if len(comps) > 0:
            c = comps[0]
            assert "competency_id" in c
            assert "mastery" in c
            assert 0.0 <= c["mastery"] <= 1.0
            assert "confidence" in c


@pytest.mark.asyncio
async def test_learner_skill_gaps():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Login as Carol (archetype with skill deficits / declining risk)
        login_res = await client.post(
            "/auth/login",
            json={"email": "carol.learner@acme.com", "password": "Password123!"},
        )
        carol = login_res.json()
        headers = {"Authorization": f"Bearer {carol['access_token']}"}
        carol_id = carol["user"]["id"]

        res = await client.get(f"/adaptive/skill-gaps/{carol_id}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "skill_gaps" in data
        assert isinstance(data["skill_gaps"], list)


@pytest.mark.asyncio
async def test_rbac_learner_cannot_inspect_other_learner_adaptive():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Alice logs in
        alice_login = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}

        # Bob logs in to get his user_id
        bob_login = await client.post(
            "/auth/login",
            json={"email": "bob.learner@acme.com", "password": "Password123!"},
        )
        bob_id = bob_login.json()["user"]["id"]

        # Alice attempts to inspect Bob's adaptive decisions -> 403 Forbidden
        decisions_res = await client.get(f"/adaptive/decisions/{bob_id}", headers=alice_headers)
        assert decisions_res.status_code == 403

        # Alice attempts to inspect Bob's skill gaps -> 403 Forbidden
        gaps_res = await client.get(f"/adaptive/skill-gaps/{bob_id}", headers=alice_headers)
        assert gaps_res.status_code == 403


@pytest.mark.asyncio
async def test_cohort_skill_gaps_manager_role():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Marcus Manager logs in
        mgr_login = await client.post(
            "/auth/login",
            json={"email": "marcus.manager@acme.com", "password": "Password123!"},
        )
        assert mgr_login.status_code == 200
        mgr_headers = {"Authorization": f"Bearer {mgr_login.json()['access_token']}"}

        # Query teams to get a team_id
        teams_res = await client.get("/teams", headers=mgr_headers)
        assert teams_res.status_code == 200
        teams = teams_res.json()
        assert len(teams) > 0
        team_id = teams[0]["id"]

        # Query cohort skill gaps
        cohort_res = await client.get(f"/adaptive/cohort-gaps/{team_id}", headers=mgr_headers)
        assert cohort_res.status_code == 200
        data = cohort_res.json()
        assert "cohort_gaps" in data
        assert isinstance(data["cohort_gaps"], list)
