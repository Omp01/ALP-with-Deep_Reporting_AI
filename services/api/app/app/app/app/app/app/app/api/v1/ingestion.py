"""
Content Ingestion API endpoints.
Handles multipart document upload, S3 persistence, text extraction, semantic chunking, and database persistence.
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.core.storage import storage_client
from app.models import IngestionJob, ContentItem, ContentChunk, Module, User
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext, log_audit_action
from shared.parsers import TextExtractor, SemanticChunker

router = APIRouter(prefix="/ingestion", tags=["Content Ingestion"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    module_id: Optional[UUID] = Form(None),
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a course material file (PDF, DOCX, PPTX, MP3, MP4, TXT, MD).
    Stores binary in S3-compatible storage and creates an IngestionJob.
    """
    file_bytes = await file.read()
    file_size = len(file_bytes)
    job_id = uuid.uuid4()
    storage_key = f"{tenant_ctx.org_id}/{job_id}_{file.filename}"

    # Upload to S3
    await storage_client.upload_file(
        object_key=storage_key,
        data=file_bytes,
        content_type=file.content_type or "application/octet-stream",
    )

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")

    job = IngestionJob(
        id=job_id,
        org_id=tenant_ctx.org_id,
        module_id=module_id,
        file_name=file.filename,
        file_type=ext,
        file_size=file_size,
        storage_path=storage_key,
        status="pending",
        created_by_id=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    await db.flush()

    await log_audit_action(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        action="CONTENT_FILE_UPLOADED",
        resource_type="INGESTION_JOB",
        resource_id=str(job_id),
        changes={"filename": file.filename, "size": file_size},
    )

    return {
        "job_id": str(job.id),
        "file_name": job.file_name,
        "file_type": job.file_type,
        "file_size": job.file_size,
        "status": job.status,
        "storage_path": job.storage_path,
        "created_at": job.created_at.isoformat(),
    }


@router.post("/jobs/{job_id}/process")
async def process_ingestion_job(
    job_id: UUID,
    module_id: Optional[UUID] = None,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Process an uploaded file:
    1. Downloads file from S3.
    2. Extracts full text and structural metadata.
    3. Chunks text using SemanticChunker.
    4. Automatically creates ContentItem and ContentChunk records.
    5. Updates IngestionJob to completed.
    """
    result = await db.execute(
        select(IngestionJob).where(and_(IngestionJob.id == job_id, IngestionJob.org_id == tenant_ctx.org_id))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    job.status = "processing"
    await db.flush()

    target_module_id = module_id or job.module_id

    try:
        # Download file from S3
        file_bytes = await storage_client.download_file(job.storage_path)

        # Extract text
        extracted_text, metadata = TextExtractor.extract_from_bytes(file_bytes, job.file_name)

        # Chunk text
        chunker = SemanticChunker(target_chunk_size=350, overlap=50)
        chunks = chunker.chunk_text(extracted_text)

        content_item_id = None
        # If target module is designated, persist ContentItem and ContentChunks
        if target_module_id:
            content_type = "document"
            if job.file_type in ["mp3", "wav"]:
                content_type = "audio"
            elif job.file_type in ["mp4", "m4a"]:
                content_type = "video"
            elif job.file_type in ["pptx", "ppt"]:
                content_type = "slide"

            content_item = ContentItem(
                id=uuid.uuid4(),
                org_id=tenant_ctx.org_id,
                module_id=target_module_id,
                title=f"Resource: {job.file_name}",
                content_type=content_type,
                content_url=job.storage_path,
                raw_text=extracted_text,
                transcript=extracted_text if content_type in ["video", "audio"] else None,
                chunk_count=len(chunks),
                item_metadata=metadata,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(content_item)
            await db.flush()
            content_item_id = str(content_item.id)

            # Insert chunks
            for chunk in chunks:
                chunk_record = ContentChunk(
                    id=uuid.uuid4(),
                    org_id=tenant_ctx.org_id,
                    content_item_id=content_item.id,
                    chunk_index=chunk["chunk_index"],
                    text_content=chunk["text_content"],
                    token_count=chunk["token_count"],
                    created_at=datetime.utcnow(),
                )
                db.add(chunk_record)

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.result_summary = {
            "character_count": len(extracted_text),
            "chunk_count": len(chunks),
            "content_item_id": content_item_id,
            "metadata": metadata,
        }
        await db.flush()

        return {
            "job_id": str(job.id),
            "status": "completed",
            "character_count": len(extracted_text),
            "chunk_count": len(chunks),
            "content_item_id": content_item_id,
            "sample_snippet": extracted_text[:200] if extracted_text else "",
        }

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        await db.flush()
        raise HTTPException(status_code=500, detail=f"Ingestion processing failed: {str(e)}")


@router.get("/jobs")
async def list_ingestion_jobs(
    limit: int = 50,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List recent ingestion jobs for the tenant."""
    query = (
        select(IngestionJob)
        .where(IngestionJob.org_id == tenant_ctx.org_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    jobs = result.scalars().all()
    return [
        {
            "id": str(j.id),
            "file_name": j.file_name,
            "file_type": j.file_type,
            "file_size": j.file_size,
            "status": j.status,
            "error_message": j.error_message,
            "result_summary": j.result_summary,
            "created_at": j.created_at.isoformat(),
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_ingestion_job(
    job_id: UUID,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details and progress of a specific ingestion job."""
    result = await db.execute(
        select(IngestionJob).where(and_(IngestionJob.id == job_id, IngestionJob.org_id == tenant_ctx.org_id))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    return {
        "id": str(job.id),
        "file_name": job.file_name,
        "file_type": job.file_type,
        "file_size": job.file_size,
        "status": job.status,
        "error_message": job.error_message,
        "result_summary": job.result_summary,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
