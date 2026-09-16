"""
Automated tests for Learning Events Telemetry API.
Tests event ingestion (single & batch), Redis stream publishing, query filtering, learner isolation, and stats.
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000/api/v1"


@pytest.mark.asyncio
async def test_ingest_single_learning_event():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login as learner
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Ingest question_answered event
        event_payload = {
            "event_type": "question_answered",
            "payload": {
                "question_id": "q-101",
                "correct": True,
                "duration_ms": 3200,
                "attempt_number": 1,
            },
        }
        res = await client.post("/events", json=event_payload, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "ingested"
        assert "event_id" in data
        assert data["event_type"] == "question_answered"
        assert "redis_message_id" in data


@pytest.mark.asyncio
async def test_ingest_batch_learning_events():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login as learner
        login_res = await client.post(
            "/auth/login",
            json={"email": "bob.learner@acme.com", "password": "Password123!"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        batch_payload = {
            "events": [
                {
                    "event_type": "content_started",
                    "payload": {"content_title": "React Architecture Overview"},
                },
                {
                    "event_type": "content_completed",
                    "payload": {"duration_ms": 14000, "scroll_depth": 1.0},
                },
            ]
        }
        res = await client.post("/events/batch", json=batch_payload, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "batch_ingested"
        assert data["count"] == 2
        assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_query_events_learner_isolation():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login as learner Alice
        alice_login = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        assert alice_login.status_code == 200
        alice_data = alice_login.json()
        alice_token = alice_data["access_token"]
        alice_id = alice_data["user"]["id"]
        alice_headers = {"Authorization": f"Bearer {alice_token}"}

        # Query events
        res = await client.get("/events", headers=alice_headers)
        assert res.status_code == 200
        events = res.json()
        assert isinstance(events, list)
        for ev in events:
            # All events retrieved by learner must belong strictly to this learner
            assert ev["user_id"] == alice_id


@pytest.mark.asyncio
async def test_events_stats_role_permissions():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Learner cannot access stats
        learner_login = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        learner_token = learner_login.json()["access_token"]
        learner_headers = {"Authorization": f"Bearer {learner_token}"}

        forbidden_res = await client.get("/events/stats", headers=learner_headers)
        assert forbidden_res.status_code == 403

        # Admin can access stats
        admin_login = await client.post(
            "/auth/login",
            json={"email": "admin@acme.com", "password": "Password123!"},
        )
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        stats_res = await client.get("/events/stats", headers=admin_headers)
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert "total_events" in stats
        assert "breakdown" in stats
        assert isinstance(stats["breakdown"], dict)
