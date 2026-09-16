"""
Automated tests for Authentication, Role-Based Access Control, and Multi-Tenancy.
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000/api/v1"


@pytest.mark.asyncio
async def test_login_success_admin():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["role"] == "org_admin"
        assert data["user"]["organization"]["slug"] == "acme-corp"


@pytest.mark.asyncio
async def test_login_success_learner():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["role"] == "learner"
        assert "Frontend Engineering Team" in data["user"]["teams"]


@pytest.mark.asyncio
async def test_login_invalid_password():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "WrongPassword123!"},
        )
        assert resp.status_code == 401
        assert "Incorrect email or password" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_user():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/auth/login",
            json={"email": "ghost@doesnotexist.com", "password": "Password123!"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_requires_token():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.get("/auth/me")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_valid_token():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        login_resp = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        token = login_resp.json()["access_token"]

        me_resp = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "admin@acme.com"


@pytest.mark.asyncio
async def test_rbac_learner_forbidden_from_admin_route():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login as learner
        login_resp = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        token = login_resp.json()["access_token"]

        # Attempt to access user management endpoint
        resp = await client.get(
            "/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cross_tenant_isolation():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login as TechNova Admin
        tn_login = await client.post(
            "/auth/login",
            json={"email": "admin@technova.com", "password": "Password123!"},
        )
        tn_token = tn_login.json()["access_token"]

        # Fetch users in TechNova tenant
        resp = await client.get(
            "/users",
            headers={"Authorization": f"Bearer {tn_token}"},
        )
        assert resp.status_code == 200
        users = resp.json()
        
        # Verify strict isolation: NO Acme users exist in TechNova response
        for u in users:
            assert "@technova.com" in u["email"]
            assert "@acme.com" not in u["email"]


@pytest.mark.asyncio
async def test_audit_log_created_on_login():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login
        login_resp = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        token = login_resp.json()["access_token"]

        # Check audit logs
        logs_resp = await client.get(
            "/organizations/audit-logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logs_resp.status_code == 200
        logs = logs_resp.json()
        assert len(logs) > 0
        assert any(l["action"] == "AUTH_LOGIN_SUCCESS" for l in logs)
