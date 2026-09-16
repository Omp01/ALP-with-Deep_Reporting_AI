"""
Automated tests for Content Ingestion Pipeline: Upload, S3 persistence, Extraction, Chunking.
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
async def test_upload_and_process_document():
    instructor_token = await get_auth_token("sarah.instructor@acme.com")

    # Sample syllabus document
    sample_text = (
        "# Advanced Distributed Systems Engineering\n\n"
        "Distributed systems require robust mechanisms for state replication, consensus, and fault detection.\n\n"
        "## Part 1: Event-Driven Architectures\n"
        "Message-driven microservices decouple components in time and space. Message brokers like Redis Streams "
        "and Apache Kafka provide durable commit logs. Consumer groups allow horizontally scalable stream processing.\n\n"
        "## Part 2: Consensus & Quorums\n"
        "When nodes fail in an asynchronous network, consensus algorithms like Raft elect leaders and synchronize state logs. "
        "Each log entry is replicated across a majority quorum before commit."
    )

    files = {
        "file": ("distributed_systems_guide.md", sample_text.encode("utf-8"), "text/markdown"),
    }

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. Fetch existing module to attach content to
        courses_resp = await client.get("/courses", headers={"Authorization": f"Bearer {instructor_token}"})
        module_id = None
        for c in courses_resp.json():
            if c.get("modules"):
                module_id = c["modules"][0]["id"]
                break

        # 2. Upload file
        upload_resp = await client.post(
            "/ingestion/upload",
            headers={"Authorization": f"Bearer {instructor_token}"},
            files=files,
            data={"module_id": module_id} if module_id else {},
        )
        assert upload_resp.status_code == 201
        upload_data = upload_resp.json()
        job_id = upload_data["job_id"]
        assert upload_data["status"] == "pending"
        assert upload_data["file_type"] == "md"

        # 3. Process ingestion job
        process_resp = await client.post(
            f"/ingestion/jobs/{job_id}/process",
            headers={"Authorization": f"Bearer {instructor_token}"},
        )
        assert process_resp.status_code == 200
        process_data = process_resp.json()
        assert process_data["status"] == "completed"
        assert process_data["character_count"] > 200
        assert process_data["chunk_count"] >= 1
        assert process_data["content_item_id"] is not None

        # 4. Fetch job details
        job_resp = await client.get(
            f"/ingestion/jobs/{job_id}",
            headers={"Authorization": f"Bearer {instructor_token}"},
        )
        assert job_resp.status_code == 200
        assert job_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_rbac_learner_cannot_upload_content():
    learner_token = await get_auth_token("alice.learner@acme.com")
    files = {"file": ("malicious.txt", b"malicious content", "text/plain")}

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/ingestion/upload",
            headers={"Authorization": f"Bearer {learner_token}"},
            files=files,
        )
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]
