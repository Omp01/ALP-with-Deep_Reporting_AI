"""
Object Storage (S3-compatible) Client.
Provides fast async upload, download, and presence check for course files.
"""

import httpx
from app.core.config import settings


class StorageClient:
    """Async client for S3-compatible object storage."""

    def __init__(self):
        endpoint = settings.minio_endpoint
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            endpoint = f"http://{endpoint}"
        self.endpoint = endpoint
        self.bucket = settings.minio_bucket

    async def upload_file(self, object_key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload raw bytes to storage bucket."""
        url = f"{self.endpoint}/{self.bucket}/{object_key}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.put(url, content=data, headers={"Content-Type": content_type})
            if resp.status_code not in [200, 201, 204]:
                raise RuntimeError(f"Storage upload failed with status {resp.status_code}: {resp.text}")
        return url

    async def download_file(self, object_key: str) -> bytes:
        """Download raw bytes from storage bucket."""
        url = f"{self.endpoint}/{self.bucket}/{object_key}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Storage download failed with status {resp.status_code}: {resp.text}")
            return resp.content


storage_client = StorageClient()
