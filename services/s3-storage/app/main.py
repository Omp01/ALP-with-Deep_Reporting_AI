"""
Lightweight S3-compatible Object Storage Service for Adaptive LMS.
Implements S3 REST API subsets needed for upload, download, presigning, and healthchecks.
"""

import os
import hashlib
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import FileResponse, PlainTextResponse

app = FastAPI(title="Adaptive LMS S3 Storage Service", version="1.0.0")

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/data"))
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
DEFAULT_BUCKET = os.getenv("MINIO_DEFAULT_BUCKETS", "adaptive-lms-content")
(STORAGE_ROOT / DEFAULT_BUCKET).mkdir(parents=True, exist_ok=True)


@app.get("/health")
@app.get("/minio/health/live")
@app.get("/minio/health/ready")
async def health():
    return {"status": "healthy", "service": "s3-storage"}


@app.head("/{bucket}")
async def head_bucket(bucket: str):
    bucket_path = STORAGE_ROOT / bucket
    if not bucket_path.exists():
        raise HTTPException(status_code=404, detail="NoSuchBucket")
    return Response(status_code=200)


@app.put("/{bucket}")
async def put_bucket(bucket: str):
    bucket_path = STORAGE_ROOT / bucket
    bucket_path.mkdir(parents=True, exist_ok=True)
    return Response(status_code=200)


@app.get("/{bucket}")
async def list_objects(bucket: str, prefix: Optional[str] = ""):
    bucket_path = STORAGE_ROOT / bucket
    if not bucket_path.exists():
        raise HTTPException(status_code=404, detail="NoSuchBucket")

    contents = []
    if bucket_path.is_dir():
        for file_path in bucket_path.glob("**/*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(bucket_path).as_posix()
                if not prefix or rel_path.startswith(prefix):
                    size = file_path.stat().st_size
                    contents.append(f"""
        <Contents>
            <Key>{rel_path}</Key>
            <Size>{size}</Size>
        </Contents>""")

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
    <Name>{bucket}</Name>
    <Prefix>{prefix or ''}</Prefix>
    {''.join(contents)}
</ListBucketResult>"""
    return Response(content=xml_response, media_type="application/xml")


@app.put("/{bucket}/{key:path}")
async def put_object(bucket: str, key: str, request: Request):
    bucket_path = STORAGE_ROOT / bucket
    bucket_path.mkdir(parents=True, exist_ok=True)
    
    file_path = bucket_path / key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    body = await request.body()
    with open(file_path, "wb") as f:
        f.write(body)
    
    etag = hashlib.md5(body).hexdigest()
    headers = {
        "ETag": f'"{etag}"',
        "Content-Length": "0",
    }
    return Response(status_code=200, headers=headers)


@app.get("/{bucket}/{key:path}")
async def get_object(bucket: str, key: str):
    file_path = STORAGE_ROOT / bucket / key
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="NoSuchKey")
    
    return FileResponse(path=str(file_path))


@app.head("/{bucket}/{key:path}")
async def head_object(bucket: str, key: str):
    file_path = STORAGE_ROOT / bucket / key
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="NoSuchKey")
    
    size = file_path.stat().st_size
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(size),
            "Accept-Ranges": "bytes",
        }
    )


@app.delete("/{bucket}/{key:path}")
async def delete_object(bucket: str, key: str):
    file_path = STORAGE_ROOT / bucket / key
    if file_path.exists() and file_path.is_file():
        file_path.unlink()
    return Response(status_code=204)
