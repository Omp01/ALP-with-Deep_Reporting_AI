"""
Lightweight S3-style object storage for Adaptive LMS.

Implements the small subset of the S3 REST API the platform needs (put, get, head,
delete, list). It stores objects as files under STORAGE_ROOT.

Security model (this service holds every uploaded course file):

  * Every request except the health checks must carry `Authorization: Bearer <token>`,
    where the token is STORAGE_TOKEN (or, failing that, MINIO_ROOT_PASSWORD). The
    service refuses to start without one; there is no anonymous mode.
  * Bucket names and object keys are validated, and every resolved path is checked to
    lie inside its bucket directory. Keys containing "..", backslashes, NUL bytes or a
    leading slash are rejected, so a key can never address a file outside the bucket.
  * Uploads are limited in size (MAX_OBJECT_MB, default 200).
"""

import hashlib
import hmac
import os
import re
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/data")).resolve()
DEFAULT_BUCKET = os.getenv("MINIO_DEFAULT_BUCKETS", "adaptive-lms-content")
MAX_OBJECT_BYTES = int(os.getenv("MAX_OBJECT_MB", "200")) * 1024 * 1024
TOKEN = os.getenv("STORAGE_TOKEN") or os.getenv("MINIO_ROOT_PASSWORD") or ""

if not TOKEN:
    raise RuntimeError("STORAGE_TOKEN (or MINIO_ROOT_PASSWORD) must be set: the storage service has no anonymous mode")

BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,62}$")
# Object keys use a conservative character set, which also keeps them valid file names on
# every platform (no "<", ">", ":", "?", "*", quotes, spaces or control characters).
OBJECT_KEY = re.compile(r"^[A-Za-z0-9._\-/]+$")
HEALTH_PATHS = {"/health", "/minio/health/live", "/minio/health/ready"}

app = FastAPI(title="Adaptive LMS Storage Service", version="2.0.0")

STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
(STORAGE_ROOT / DEFAULT_BUCKET).mkdir(parents=True, exist_ok=True)


@app.middleware("http")
async def require_token(request: Request, call_next):
    if request.url.path in HEALTH_PATHS:
        return await call_next(request)
    header = request.headers.get("authorization", "")
    supplied = header[7:] if header.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(supplied.encode(), TOKEN.encode()):
        return Response(status_code=401, content="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)


def _bucket_dir(bucket: str) -> Path:
    if not BUCKET_NAME.match(bucket):
        raise HTTPException(status_code=400, detail="InvalidBucketName")
    return STORAGE_ROOT / bucket


def _object_path(bucket: str, key: str) -> Path:
    """Resolve an object key to a file path that is guaranteed to be inside its bucket."""
    if not key or len(key) > 900 or not OBJECT_KEY.match(key):
        raise HTTPException(status_code=400, detail="InvalidKey")
    if any(part in (".", "..", "") for part in key.split("/")):
        raise HTTPException(status_code=400, detail="InvalidKey")
    root = _bucket_dir(bucket).resolve()
    path = (root / key).resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="InvalidKey")
    return path


@app.get("/health")
@app.get("/minio/health/live")
@app.get("/minio/health/ready")
async def health():
    return {"status": "healthy", "service": "s3-storage"}


@app.head("/{bucket}")
async def head_bucket(bucket: str):
    if not _bucket_dir(bucket).exists():
        raise HTTPException(status_code=404, detail="NoSuchBucket")
    return Response(status_code=200)


@app.put("/{bucket}")
async def put_bucket(bucket: str):
    _bucket_dir(bucket).mkdir(parents=True, exist_ok=True)
    return Response(status_code=200)


@app.get("/{bucket}")
async def list_objects(bucket: str, prefix: Optional[str] = ""):
    bucket_path = _bucket_dir(bucket)
    if not bucket_path.exists():
        raise HTTPException(status_code=404, detail="NoSuchBucket")

    root = bucket_path.resolve()
    contents = []
    for file_path in root.glob("**/*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(root).as_posix()
            if not prefix or rel_path.startswith(prefix):
                contents.append(
                    f"<Contents><Key>{escape(rel_path)}</Key><Size>{file_path.stat().st_size}</Size></Contents>"
                )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Name>{escape(bucket)}</Name><Prefix>{escape(prefix or '')}</Prefix>{''.join(contents)}"
        "</ListBucketResult>"
    )
    return Response(content=xml, media_type="application/xml")


@app.put("/{bucket}/{key:path}")
async def put_object(bucket: str, key: str, request: Request):
    path = _object_path(bucket, key)

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_OBJECT_BYTES:
        raise HTTPException(status_code=413, detail="EntityTooLarge")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_OBJECT_BYTES:
            raise HTTPException(status_code=413, detail="EntityTooLarge")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(body))
    etag = hashlib.md5(bytes(body)).hexdigest()  # noqa: S324 - S3 ETag convention, not a security use
    return Response(status_code=200, headers={"ETag": f'"{etag}"', "Content-Length": "0"})


@app.get("/{bucket}/{key:path}")
async def get_object(bucket: str, key: str):
    path = _object_path(bucket, key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="NoSuchKey")
    return FileResponse(path=str(path))


@app.head("/{bucket}/{key:path}")
async def head_object(bucket: str, key: str):
    path = _object_path(bucket, key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="NoSuchKey")
    return Response(status_code=200, headers={"Content-Length": str(path.stat().st_size), "Accept-Ranges": "bytes"})


@app.delete("/{bucket}/{key:path}")
async def delete_object(bucket: str, key: str):
    path = _object_path(bucket, key)
    if path.is_file():
        path.unlink()
    return Response(status_code=204)
