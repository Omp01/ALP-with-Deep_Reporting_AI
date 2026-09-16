"""
Automated tests for Risk Engine, Early Warning Anomaly Detection, and Intervention Workflow.
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000/api/v1"


@pytest.mark.asyncio
async def test_trigger_organization_risk_scan():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # 1. Login as Admin
        admin_login = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Trigger risk scan
        scan_res = await client.post("/risks/scan", headers=headers)
        assert scan_res.status_code == 200
        data = scan_res.json()
        assert data["status"] == "completed"
        assert "summary" in data
        assert data["summary"]["evaluated_enrollments"] >= 1


@pytest.mark.asyncio
async def test_list_risks_manager():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Login as Marcus Manager
        mgr_login = await client.post(
            "/auth/login",
            json={"email": "marcus.manager@acme.com", "password": "Password123!"},
        )
        assert mgr_login.status_code == 200
        mgr_token = mgr_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {mgr_token}"}

        # List risks
        res = await client.get("/risks", headers=headers)
        assert res.status_code == 200
        risks = res.json()
        assert isinstance(risks, list)
        assert len(risks) >= 1
        r = risks[0]
        assert "risk_level" in r
        assert "risk_score" in r
        assert "risk_factors" in r
        assert "recommended_actions" in r
        assert "is_resolved" in r


@pytest.mark.asyncio
async def test_filter_risks_by_level():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        mgr_login = await client.post(
            "/auth/login",
            json={"email": "marcus.manager@acme.com", "password": "Password123!"},
        )
        headers = {"Authorization": f"Bearer {mgr_login.json()['access_token']}"}

        res = await client.get("/risks?risk_level=critical", headers=headers)
        assert res.status_code == 200
        records = res.json()
        for rec in records:
            assert rec["risk_level"] == "critical"


@pytest.mark.asyncio
async def test_learner_risk_detail_and_rbac():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        # Dan is disengaged/critical risk archetype
        dan_login = await client.post(
            "/auth/login",
            json={"email": "dan.learner@acme.com", "password": "Password123!"},
        )
        assert dan_login.status_code == 200
        dan = dan_login.json()
        dan_token = dan["access_token"]
        dan_id = dan["user"]["id"]
        dan_headers = {"Authorization": f"Bearer {dan_token}"}

        # Dan can inspect his own risk detail
        detail_res = await client.get(f"/risks/{dan_id}", headers=dan_headers)
        assert detail_res.status_code == 200
        dan_risks = detail_res.json()
        assert isinstance(dan_risks, list)
        if len(dan_risks) > 0:
            assert dan_risks[0]["user_id"] == dan_id

        # Dan cannot query the organization-wide risks list (403)
        forbidden_res = await client.get("/risks", headers=dan_headers)
        assert forbidden_res.status_code == 403


@pytest.mark.asyncio
async def test_resolve_risk_alert():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        admin_login = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        # Get first unresolved risk
        list_res = await client.get("/risks?resolved=false", headers=headers)
        assert list_res.status_code == 200
        unresolved = list_res.json()
        assert len(unresolved) > 0
        target_risk_id = unresolved[0]["id"]

        # Resolve the alert
        resolve_res = await client.put(f"/risks/{target_risk_id}/resolve", headers=headers)
        assert resolve_res.status_code == 200
        data = resolve_res.json()
        assert data["status"] == "resolved"
        assert data["is_resolved"] is True
