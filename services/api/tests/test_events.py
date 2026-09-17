"""
Automated tests for Learning Events Telemetry API.
Tests event ingestion (single & batch), Redis stream publishing, query filtering, learner isolation, and stats.
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000/api/v1"


@pytest.mark.asyncio
async def test_ingest_single_learning_event():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
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
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
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
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
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
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
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


@pytest.mark.asyncio
async def test_session_lifecycle_and_events_idempotency():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Login as learner
        login_res = await client.post(
            "/auth/login",
            json={"email": "alice.learner@acme.com", "password": "Password123!"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get available courses
        courses_res = await client.get("/courses", headers=headers)
        assert courses_res.status_code == 200
        courses = courses_res.json()
        assert len(courses) > 0
        course_id = courses[0]["id"]

        # 3. Start a learning session
        start_res = await client.post(
            "/learning/sessions/start",
            json={
                "course_id": course_id,
                "device_info": {"browser": "Chrome", "os": "Windows"},
                "initial_difficulty": 0.6,
            },
            headers=headers,
        )
        assert start_res.status_code in (200, 201)
        session_data = start_res.json()
        session_id = session_data["session_id"]
        assert "session_id" in session_data

        # 4. Check active session
        active_res = await client.get("/learning/sessions/active", headers=headers)
        assert active_res.status_code == 200
        active_data = active_res.json()
        assert active_data["active"] is True
        assert active_data["session"]["session_id"] == session_id

        # 5. Ingest event with specified event_id (idempotency test)
        import uuid
        custom_event_id = str(uuid.uuid4())
        event_payload = {
            "event_id": custom_event_id,
            "event_type": "video_play",
            "course_id": course_id,
            "session_id": session_id,
            "payload": {"playback_rate": 1.0, "current_time": 45.0},
        }
        ev1 = await client.post("/events", json=event_payload, headers=headers)
        assert ev1.status_code == 201
        assert ev1.json()["status"] == "ingested"

        # Duplicate submission with same event_id
        ev2 = await client.post("/events", json=event_payload, headers=headers)
        assert ev2.status_code in (200, 201)
        assert ev2.json()["status"] == "duplicate_ignored"

        # 6. End learning session
        end_res = await client.post(
            f"/learning/sessions/{session_id}/end",
            json={"metrics": {"final_completion_rate": 0.85}},
            headers=headers,
        )
        assert end_res.status_code == 200
        end_data = end_res.json()
        assert end_data["status"] == "completed"
        assert "duration_seconds" in end_data

