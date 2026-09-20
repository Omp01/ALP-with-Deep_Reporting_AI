"""
Security tests for the storage service.

Run from services/s3-storage:   python -m pytest tests

The service is imported with a temporary storage root and a known token, then driven
in-process. Every test that matters here is a request that USED to succeed.
"""

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-storage-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def storage(monkeypatch):
    root = Path(tempfile.mkdtemp())
    (root / "outside.txt").write_text("secret outside the bucket")
    monkeypatch.setenv("STORAGE_ROOT", str(root / "data"))
    monkeypatch.setenv("STORAGE_TOKEN", TOKEN)
    monkeypatch.setenv("MAX_OBJECT_MB", "1")
    monkeypatch.setenv("MINIO_DEFAULT_BUCKETS", "content")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    return TestClient(module.app), root


def raw_request(module, method, raw_path, body=b"", token=TOKEN):
    """
    Send a request whose path reaches the app EXACTLY as written.

    HTTP client libraries normalise "/a/../b" to "/b" before sending, which would make the
    traversal tests vacuous. An attacker using `curl --path-as-is` gets no such
    protection, so these tests build the ASGI scope by hand.
    """
    import asyncio

    sent = []

    async def run():
        queue = [{"type": "http.request", "body": body, "more_body": False}]

        async def receive():
            return queue.pop(0) if queue else {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
            "scheme": "http", "path": raw_path, "raw_path": raw_path.encode(), "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode()), (b"content-length", str(len(body)).encode())],
            "server": ("test", 80), "client": ("test", 1234),
        }
        await module.app(scope, receive, send)

    asyncio.run(run())
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def test_service_refuses_to_start_without_a_token(monkeypatch):
    monkeypatch.delenv("STORAGE_TOKEN", raising=False)
    monkeypatch.delenv("MINIO_ROOT_PASSWORD", raising=False)
    monkeypatch.setenv("STORAGE_ROOT", tempfile.mkdtemp())
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.modules.pop("app.main", None)
    with pytest.raises(RuntimeError, match="no anonymous mode"):
        importlib.import_module("app.main")


def test_health_is_open_but_everything_else_needs_the_token(storage):
    client, _ = storage
    assert client.get("/health").status_code == 200
    assert client.put("/content/a.txt", content=b"x").status_code == 401
    assert client.get("/content/a.txt").status_code == 401
    assert client.get("/content").status_code == 401
    assert client.delete("/content/a.txt").status_code == 401


def test_a_wrong_token_is_rejected(storage):
    client, _ = storage
    assert client.get("/content/a.txt", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/content/a.txt", headers={"Authorization": TOKEN}).status_code == 401  # no scheme


def test_round_trip_with_the_token(storage):
    client, _ = storage
    assert client.put("/content/org/1/file.txt", content=b"hello", headers=AUTH).status_code == 200
    got = client.get("/content/org/1/file.txt", headers=AUTH)
    assert got.status_code == 200 and got.content == b"hello"
    assert client.head("/content/org/1/file.txt", headers=AUTH).headers["content-length"] == "5"
    assert "org/1/file.txt" in client.get("/content", headers=AUTH).text
    assert client.delete("/content/org/1/file.txt", headers=AUTH).status_code == 204
    assert client.get("/content/org/1/file.txt", headers=AUTH).status_code == 404


@pytest.mark.parametrize(
    "key",
    ["../outside.txt", "a/../../outside.txt", "..", "a/./b", "a//b", "a\\..\\b", "%2e%2e/outside.txt"],
)
def test_keys_cannot_escape_the_bucket_for_reads(storage, key):
    client, _ = storage
    resp = client.get(f"/content/{key}", headers=AUTH)
    assert resp.status_code in (400, 404), key
    assert b"secret outside the bucket" not in resp.content


@pytest.mark.parametrize("path", ["/content/../evil.txt", "/content/a/../../evil.txt", "/content/../../evil.txt"])
def test_raw_dot_dot_writes_cannot_escape_the_bucket(storage, path):
    client, root = storage
    status = raw_request(sys.modules["app.main"], "PUT", path, b"pwned")
    assert status == 400
    assert not list(root.rglob("evil.txt"))


def test_raw_dot_dot_reads_and_deletes_cannot_touch_files_outside(storage):
    client, root = storage
    module = sys.modules["app.main"]
    assert raw_request(module, "GET", "/content/../../outside.txt") == 400
    assert raw_request(module, "DELETE", "/content/../../outside.txt") == 400
    assert (root / "outside.txt").exists()


def test_bucket_names_are_validated(storage):
    client, _ = storage
    assert client.put("/BAD_NAME/x.txt", content=b"x", headers=AUTH).status_code == 400
    assert client.put("/a/x.txt", content=b"x", headers=AUTH).status_code == 400  # too short


def test_oversized_uploads_are_refused(storage):
    client, _ = storage
    resp = client.put("/content/big.bin", content=b"x" * (1024 * 1024 + 1), headers=AUTH)
    assert resp.status_code == 413
    assert client.get("/content/big.bin", headers=AUTH).status_code == 404


@pytest.mark.parametrize("key", ["<script>.txt", "a b.txt", "a:b.txt", "a*.txt"])
def test_keys_outside_the_safe_character_set_are_rejected(storage, key):
    client, _ = storage
    assert client.put(f"/content/{key}", content=b"x", headers=AUTH).status_code == 400
