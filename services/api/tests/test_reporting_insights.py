"""
Automated tests for Grounded AI Reporting, Citation Verification, Multi-Surface Analytics, Digest, and BI Export.
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000/api/v1"


@pytest.mark.asyncio
async def test_generate_grounded_insight_learner():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Login as Alice
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        assert login_res.status_code == 200
        alice = login_res.json()
        headers = {"Authorization": f"Bearer {alice['access_token']}"}
        alice_id = alice["user"]["id"]

        # Generate insight
        req_payload = {
            "scope_type": "learner",
            "scope_id": alice_id,
            "question": "What is my current understanding of React components?",
        }
        res = await client.post("/insights/generate", json=req_payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "insight_id" in data
        assert "claims" in data
        assert len(data["claims"]) >= 1
        assert "summary" in data
        assert "recommendations" in data

        # Check citations
        first_claim = data["claims"][0]
        assert "confidence" in first_claim
        assert first_claim["confidence"] >= 0.70


@pytest.mark.asyncio
async def test_get_insight_and_evidence():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
        alice_id = login_res.json()["user"]["id"]

        # Generate insight first
        res = await client.post(
            "/insights/generate",
            json={"scope_type": "learner", "scope_id": alice_id, "question": "Provide summary"},
            headers=headers,
        )
        assert res.status_code == 200
        insight_id = res.json()["insight_id"]

        # Retrieve detail
        detail_res = await client.get(f"/insights/{insight_id}", headers=headers)
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["id"] == insight_id
        assert "citations" in detail
        assert "confidence_score" in detail

        # Retrieve evidence facts
        evidence_res = await client.get(f"/insights/{insight_id}/evidence", headers=headers)
        assert evidence_res.status_code == 200
        evidence = evidence_res.json()
        assert "evidence_package" in evidence


@pytest.mark.asyncio
async def test_learner_and_team_analytics():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Learner analytics
        alice_login = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        alice_headers = {"Authorization": f"Bearer {alice_login.json()['access_token']}"}
        alice_id = alice_login.json()["user"]["id"]

        learner_res = await client.get(f"/analytics/learner/{alice_id}", headers=alice_headers)
        assert learner_res.status_code == 200
        learner_metrics = learner_res.json()
        assert "average_mastery" in learner_metrics
        assert "mastery_distribution" in learner_metrics

        # Team analytics
        mgr_login = await client.post(
            "/auth/login",
            json={"email": "marcus.manager@acme.com", "password": "Password123!"},
        )
        mgr_headers = {"Authorization": f"Bearer {mgr_login.json()['access_token']}"}

        teams_res = await client.get("/teams", headers=mgr_headers)
        team_id = teams_res.json()[0]["id"]

        team_res = await client.get(f"/analytics/team/{team_id}", headers=mgr_headers)
        assert team_res.status_code == 200
        team_metrics = team_res.json()
        assert "total_members" in team_metrics
        assert "average_cohort_mastery" in team_metrics
        assert "at_risk_breakdown" in team_metrics


@pytest.mark.asyncio
async def test_scheduled_digest_lifecycle():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        admin_login = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        # Generate digest
        gen_res = await client.post("/reports/digest/generate", headers=admin_headers)
        assert gen_res.status_code == 200
        gen_data = gen_res.json()
        assert "digest_id" in gen_data
        assert "content" in gen_data

        # Query latest
        latest_res = await client.get("/reports/digest/latest", headers=admin_headers)
        assert latest_res.status_code == 200
        latest_data = latest_res.json()
        assert "content" in latest_data
        assert latest_data["status"] == "success"


@pytest.mark.asyncio
async def test_bi_export_apis():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        admin_login = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        # Export events as CSV
        csv_res = await client.get("/export/events?format=csv", headers=admin_headers)
        assert csv_res.status_code == 200
        assert "text/csv" in csv_res.headers.get("content-type", "")
        assert "id,user_id,course_id" in csv_res.text

        # Export competencies as JSON
        json_res = await client.get("/export/competencies?format=json", headers=admin_headers)
        assert json_res.status_code == 200
        data = json_res.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "mastery_score" in data[0]

        # Export risks as CSV
        risk_csv = await client.get("/export/risks?format=csv", headers=admin_headers)
        assert risk_csv.status_code == 200
        assert "text/csv" in risk_csv.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_embeddable_widget_html():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Get alice ID and tenant ID
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        user_info = login_res.json()["user"]
        alice_id = user_info["id"]
        org_id = user_info["org_id"]

        # Request HTML widget
        res = await client.get(f"/embed/report?learner_id={alice_id}&org_id={org_id}&format=html")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        assert "Adaptive Learning Progress" in res.text
        assert "Verified by Adaptive LMS Deep Reporting AI" in res.text
