"""
Content administration: ingest, review, and publish learning content.

    POST /admin/content/ingest/file      upload a document, video or audio file
    POST /admin/content/ingest/youtube   add a YouTube video by link
    GET  /admin/content                  the content library (search and filters)
    GET  /admin/content/{id}             everything needed to review one item
    GET  /admin/content/jobs/{id}        job progress (polled by the UI)
    POST /admin/content/{id}/process     retry or re-analyse
    PUT  /admin/content/{id}/analysis    edit objectives and competency decisions
    ...  candidate questions: create, edit, approve/reject, delete
    POST /admin/content/{id}/publish     publish what was reviewed

Only L&D admins and organisation admins may use these endpoints, and every lookup is
tenant-scoped: another tenant's content, job, module or question is a 404.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, log_audit_action, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.storage import storage_client
from app.ingestion import pipeline
from app.ingestion.ai import ai_status
from app.ingestion.embeddings import get_embedder
from app.ingestion.errors import FileTooLarge, IngestionError
from app.ingestion.publish import publish_content, readiness
from app.ingestion.transcription import transcription_available
from app.ingestion.validation import allowed_extensions, sanitize_filename, storage_key, validate_upload
from app.ingestion.youtube import canonical_url, validate_youtube_url
from app.models import (
    Competency,
    ContentChunk,
    ContentItem,
    Course,
    IngestionJob,
    LearningEvent,
    Module,
    QuestionCandidate,
    User,
)
from app.schemas import content_admin as s

logger = logging.getLogger("api.content_admin")
router = APIRouter(prefix="/admin/content", tags=["Content Administration"])

_ADMINS = ["ld_admin", "org_admin"]
PREVIEW_CHARS = 3000
ANALYZABLE_TYPES = {"ARTICLE", "DOCUMENT", "VIDEO", "AUDIO"}


def _http(exc: IngestionError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": str(exc)})


# ---------------------------------------------------------------------------- loaders
async def _load_item(db: AsyncSession, org_id: UUID, content_id: UUID) -> ContentItem:
    item = (await db.execute(select(ContentItem).where(ContentItem.id == content_id, ContentItem.org_id == org_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Content not found")
    return item


async def _load_module(db: AsyncSession, org_id: UUID, module_id: UUID) -> Module:
    module = (await db.execute(select(Module).where(Module.id == module_id, Module.org_id == org_id))).scalar_one_or_none()
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


async def _load_candidate(db: AsyncSession, org_id: UUID, candidate_id: UUID) -> QuestionCandidate:
    candidate = (await db.execute(
        select(QuestionCandidate).where(QuestionCandidate.id == candidate_id, QuestionCandidate.org_id == org_id)
    )).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return candidate


async def _latest_job(db: AsyncSession, org_id: UUID, content_id: UUID) -> Optional[IngestionJob]:
    return (await db.execute(
        select(IngestionJob).where(IngestionJob.org_id == org_id, IngestionJob.content_item_id == content_id)
        .order_by(IngestionJob.created_at.desc()).limit(1)
        .execution_options(populate_existing=True)   # the pipeline updates the job from its own session
    )).scalar_one_or_none()


async def _check_competency(db: AsyncSession, org_id: UUID, competency_id: Optional[UUID]) -> None:
    if competency_id is None:
        return
    found = (await db.execute(select(Competency.id).where(Competency.id == competency_id, Competency.org_id == org_id))).first()
    if found is None:
        raise HTTPException(status_code=404, detail="Competency not found")


async def _next_order(db: AsyncSession, module_id: UUID) -> int:
    return ((await db.execute(select(func.coalesce(func.max(ContentItem.order_index), 0)).where(ContentItem.module_id == module_id))).scalar() or 0) + 1


# --------------------------------------------------------------------------- mappers
def _job_out(job: IngestionJob) -> s.JobOut:
    return s.JobOut(
        id=job.id, content_item_id=job.content_item_id, source_type=job.source_type, file_name=job.file_name,
        status=job.status, stage=job.stage, stages=[s.StageOut(**stage) for stage in (job.stages or [])],
        error_code=job.error_code, error_message=job.error_message, attempts=job.attempts,
        created_at=job.created_at, updated_at=job.updated_at,
    )


def _candidate_out(c: QuestionCandidate) -> s.CandidateOut:
    return s.CandidateOut(
        id=c.id, question_text=c.question_text, question_type=c.question_type or "multiple_choice", options=c.options or [],
        explanation=c.explanation, expected_answer=c.expected_answer, rubric=c.rubric, difficulty=c.difficulty,
        competency_id=c.competency_id, competency_name=c.competency_name, source_quote=c.source_quote, origin=c.origin,
        status=c.status, edited=c.edited, created_at=c.created_at,
    )


async def _detail(db: AsyncSession, item: ContentItem) -> s.ContentDetail:
    module = await db.get(Module, item.module_id)
    course = await db.get(Course, module.course_id) if module else None
    job = await _latest_job(db, item.org_id, item.id)
    candidates = (await db.execute(
        select(QuestionCandidate).where(QuestionCandidate.content_item_id == item.id).order_by(QuestionCandidate.created_at)
    )).scalars().all()
    text = item.transcript or item.raw_text or item.text_content or ""
    ready = await readiness(db, item)
    meta = item.item_metadata or {}
    return s.ContentDetail(
        id=item.id, title=item.title, description=item.description, content_type=item.content_type,
        source_type=item.source_type, source_url=item.source_url,
        original_filename=meta.get("original_filename") or (job.file_name if job and job.source_type == "upload" else None),
        status=item.status, course_id=course.id if course else None, course_title=course.title if course else None,
        module_id=item.module_id, module_title=module.title if module else None, duration_seconds=item.duration_seconds or 0,
        metadata=meta, text_preview=text[:PREVIEW_CHARS] or None, text_length=len(text), has_transcript=bool(item.transcript),
        analysis=item.analysis, job=_job_out(job) if job else None, candidates=[_candidate_out(c) for c in candidates],
        readiness=s.Readiness(can_publish=ready.can_publish, blockers=ready.blockers, warnings=ready.warnings),
        created_at=item.created_at, updated_at=item.updated_at,
    )


# ------------------------------------------------------------------------ capabilities
@router.get("/capabilities", response_model=s.Capabilities)
async def capabilities(
    current_user: User = Depends(require_roles(_ADMINS)),
):
    """What this deployment can do, so the UI can say so instead of failing later."""
    ai = ai_status()
    return s.Capabilities(
        file_types=allowed_extensions(settings.allowed_file_types), max_upload_mb=settings.max_upload_size_mb,
        ai_configured=ai.configured, ai_provider=ai.provider, ai_model=ai.model, ai_detail=ai.detail,
        transcription_available=transcription_available(), embeddings_enabled=get_embedder() is not None,
    )


# ---------------------------------------------------------------------------- ingest
async def _duplicate_of(db: AsyncSession, org_id: UUID, *, content_hash: Optional[str] = None, source_url: Optional[str] = None) -> Optional[ContentItem]:
    conditions = []
    if content_hash:
        conditions.append(ContentItem.content_hash == content_hash)
    if source_url:
        conditions.append(ContentItem.source_url == source_url)
    if not conditions:
        return None
    return (await db.execute(
        select(ContentItem).where(ContentItem.org_id == org_id, ContentItem.status != "failed", or_(*conditions)).limit(1)
    )).scalar_one_or_none()


def _duplicate_error(existing: ContentItem) -> HTTPException:
    return HTTPException(status_code=409, detail={
        "code": "duplicate_content",
        "message": f"This looks like content you already added: \"{existing.title}\".",
        "content_id": str(existing.id),
    })


@router.post("/ingest/file", response_model=s.IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_file(
    file: UploadFile = File(...),
    module_id: UUID = Form(...),
    title: Optional[str] = Form(None),
    allow_duplicate: bool = Form(False),
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Validate and store an uploaded file, then start processing it in the background."""
    org_id = tenant_ctx.org_id
    module = await _load_module(db, org_id, module_id)

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    try:
        upload = validate_upload(file.filename or "", data, max_bytes=max_bytes, allowed=allowed_extensions(settings.allowed_file_types))
    except IngestionError as exc:
        raise _http(exc)

    if not allow_duplicate:
        existing = await _duplicate_of(db, org_id, content_hash=upload.sha256)
        if existing is not None:
            raise _duplicate_error(existing)

    job_id = uuid4()
    key = storage_key(org_id, job_id, upload.safe_name)
    try:
        await storage_client.upload_file(key, data, upload.kind.mime)
    except Exception:
        logger.exception("storage upload failed")
        raise HTTPException(status_code=502, detail={"code": "storage_unavailable", "message": "The file could not be stored. Try again shortly."})

    try:
        stem = upload.safe_name.rpartition(".")[0].replace("_", " ").replace("-", " ").strip() or upload.safe_name
        item = ContentItem(
            org_id=org_id, course_id=module.course_id, module_id=module.id,
            title=(title or stem).strip()[:255], content_type=upload.kind.content_type, status="processing",
            source_type="upload", content_url=key, content_hash=upload.sha256, order_index=await _next_order(db, module.id),
            item_metadata={"original_filename": upload.safe_name, "size": upload.size, "mime": upload.kind.mime},
        )
        db.add(item)
        await db.flush()
        job = IngestionJob(
            id=job_id, org_id=org_id, module_id=module.id, content_item_id=item.id, source_type="upload",
            file_name=upload.safe_name, file_type=upload.extension, file_size=upload.size, storage_path=key,
            status="pending", created_by_id=current_user.id, stages=pipeline.initial_stages("upload", upload.kind.kind),
        )
        db.add(job)
        await log_audit_action(db, org_id, current_user.id, "CONTENT_INGEST_STARTED", "CONTENT", str(item.id),
                               {"source": "upload", "file": upload.safe_name, "size": upload.size})
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            await storage_client.delete_file(key)
        except Exception:
            logger.warning("could not remove orphaned upload %s", key)
        raise

    await pipeline.submit(job_id)
    return s.IngestResponse(content_id=item.id, job_id=job_id, status="processing")


@router.post("/ingest/youtube", response_model=s.IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_youtube(
    payload: s.IngestYouTubeRequest,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Add a YouTube video: validate the link, then fetch details and captions in the background."""
    org_id = tenant_ctx.org_id
    module = await _load_module(db, org_id, payload.module_id)
    try:
        video_id = validate_youtube_url(payload.url)
    except IngestionError as exc:
        raise _http(exc)
    url = canonical_url(video_id)

    if not payload.allow_duplicate:
        existing = await _duplicate_of(db, org_id, source_url=url)
        if existing is not None:
            raise _duplicate_error(existing)

    item = ContentItem(
        org_id=org_id, course_id=module.course_id, module_id=module.id,
        title=(payload.title or f"YouTube video {video_id}").strip()[:255], content_type="VIDEO", status="processing",
        source_type="youtube", source_url=url, content_url=url, order_index=await _next_order(db, module.id),
        item_metadata={"provider": "youtube", "video_id": video_id},
    )
    db.add(item)
    await db.flush()
    job = IngestionJob(
        org_id=org_id, module_id=module.id, content_item_id=item.id, source_type="youtube", source_url=url,
        file_name=url, file_type="youtube", file_size=0, storage_path=None, status="pending",
        created_by_id=current_user.id, stages=pipeline.initial_stages("youtube", "video"),
    )
    db.add(job)
    await db.flush()
    await log_audit_action(db, org_id, current_user.id, "CONTENT_INGEST_STARTED", "CONTENT", str(item.id), {"source": "youtube", "video_id": video_id})
    await db.commit()

    await pipeline.submit(job.id)
    return s.IngestResponse(content_id=item.id, job_id=job.id, status="processing")


# ------------------------------------------------------------------------------ library
@router.get("", response_model=s.ContentListResponse)
async def list_content(
    q: Optional[str] = Query(None, max_length=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    content_type: Optional[str] = Query(None, alias="type"),
    source: Optional[str] = None,
    course_id: Optional[UUID] = None,
    module_id: Optional[UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """The content library. Every filter is optional and combines with the others."""
    org_id = tenant_ctx.org_id
    conditions = [ContentItem.org_id == org_id]
    if q:
        conditions.append(ContentItem.title.ilike(f"%{q.strip()}%"))
    if status_filter:
        conditions.append(ContentItem.status == status_filter)
    if content_type:
        conditions.append(ContentItem.content_type == content_type.upper())
    if source:
        conditions.append(ContentItem.source_type == source)
    if course_id:
        conditions.append(ContentItem.course_id == course_id)
    if module_id:
        conditions.append(ContentItem.module_id == module_id)

    total = (await db.execute(select(func.count()).select_from(ContentItem).where(and_(*conditions)))).scalar() or 0
    rows = (await db.execute(
        select(ContentItem, Module.title, Course.id, Course.title)
        .join(Module, Module.id == ContentItem.module_id)
        .join(Course, Course.id == Module.course_id)
        .where(and_(*conditions)).order_by(ContentItem.created_at.desc()).limit(limit).offset(offset)
    )).all()

    ids = [item.id for item, *_ in rows]
    jobs: Dict[UUID, str] = {}
    counts: Dict[UUID, Dict[str, int]] = {}
    if ids:
        for job in (await db.execute(
            select(IngestionJob).where(IngestionJob.org_id == org_id, IngestionJob.content_item_id.in_(ids)).order_by(IngestionJob.created_at.asc())
        )).scalars():
            jobs[job.content_item_id] = job.status  # ascending order: the newest job wins
        for item_id, state, n in (await db.execute(
            select(QuestionCandidate.content_item_id, QuestionCandidate.status, func.count())
            .where(QuestionCandidate.content_item_id.in_(ids)).group_by(QuestionCandidate.content_item_id, QuestionCandidate.status)
        )).all():
            counts.setdefault(item_id, {})[state] = n

    return s.ContentListResponse(total=total, items=[
        s.ContentListItem(
            id=item.id, title=item.title, content_type=item.content_type, source_type=item.source_type, status=item.status,
            course_id=course_id_, course_title=course_title, module_id=item.module_id, module_title=module_title,
            duration_seconds=item.duration_seconds or 0, job_status=jobs.get(item.id),
            pending_questions=counts.get(item.id, {}).get("pending", 0), approved_questions=counts.get(item.id, {}).get("approved", 0),
            created_at=item.created_at, updated_at=item.updated_at,
        )
        for item, module_title, course_id_, course_title in rows
    ])


@router.get("/jobs/{job_id}", response_model=s.JobOut)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Job progress. The UI polls this while a job is running."""
    job = (await db.execute(select(IngestionJob).where(IngestionJob.id == job_id, IngestionJob.org_id == tenant_ctx.org_id).execution_options(populate_existing=True))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(job)


@router.get("/{content_id}", response_model=s.ContentDetail)
async def get_content(
    content_id: UUID,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await _detail(db, await _load_item(db, tenant_ctx.org_id, content_id))


# ------------------------------------------------------------------------------ actions
async def _start_job(db: AsyncSession, item: ContentItem, user: User, *, force: bool) -> IngestionJob:
    """Reuse the item's latest job (keeping its history) or create one for content that never had a job."""
    job = await _latest_job(db, item.org_id, item.id)
    if job is not None and job.status in ("pending", "processing"):
        raise HTTPException(status_code=409, detail={"code": "already_processing", "message": "This content is already being processed."})

    if job is None:
        if item.source_type == "youtube":
            job = IngestionJob(org_id=item.org_id, module_id=item.module_id, content_item_id=item.id, source_type="youtube",
                               source_url=item.source_url, file_name=item.source_url or item.title, file_type="youtube",
                               file_size=0, status="pending", created_by_id=user.id)
        elif (item.text_content or item.raw_text or item.transcript or "").strip():
            job = IngestionJob(org_id=item.org_id, module_id=item.module_id, content_item_id=item.id, source_type="text",
                               file_name=item.title[:255], file_type="text", file_size=0, status="pending", created_by_id=user.id)
        else:
            raise HTTPException(status_code=422, detail={"code": "nothing_to_analyse", "message": "This content has no text to analyse."})
        db.add(job)
        await db.flush()
    job.status = "pending"
    await db.commit()
    return job


@router.post("/{content_id}/process", response_model=s.JobOut, status_code=status.HTTP_202_ACCEPTED)
async def process_content(
    content_id: UUID,
    payload: s.ProcessRequest = s.ProcessRequest(),
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed or interrupted job, or re-analyse (force=true ignores the unchanged-content shortcut)."""
    item = await _load_item(db, tenant_ctx.org_id, content_id)
    if item.content_type not in ANALYZABLE_TYPES:
        raise HTTPException(status_code=422, detail={"code": "not_analysable", "message": "Only reading, document, video and audio content can be analysed."})
    job = await _start_job(db, item, current_user, force=payload.force)
    await log_audit_action(db, item.org_id, current_user.id, "CONTENT_REPROCESS", "CONTENT", str(item.id), {"force": payload.force})
    await db.commit()
    await pipeline.submit(job.id, force=payload.force)
    await db.refresh(job)
    return _job_out(job)


@router.put("/{content_id}", response_model=s.ContentDetail)
async def update_content(
    content_id: UUID,
    payload: s.ContentUpdate,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    item = await _load_item(db, tenant_ctx.org_id, content_id)
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"]:
        item.title = changes["title"].strip()
    if "description" in changes:
        item.description = (changes["description"] or "").strip() or None
    if changes.get("module_id"):
        module = await _load_module(db, item.org_id, changes["module_id"])
        item.module_id, item.course_id = module.id, module.course_id
        item.order_index = await _next_order(db, module.id)
    await db.flush()
    return await _detail(db, item)


@router.put("/{content_id}/transcript", response_model=s.ContentDetail)
async def set_transcript(
    content_id: UUID,
    payload: s.TranscriptUpdate,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Supply a transcript by hand (for media with no captions or no transcription engine), and optionally analyse it."""
    import hashlib

    item = await _load_item(db, tenant_ctx.org_id, content_id)
    if item.content_type not in ("VIDEO", "AUDIO"):
        raise HTTPException(status_code=422, detail={"code": "not_media", "message": "Only video and audio have transcripts."})
    item.transcript = payload.text.strip()
    item.content_hash = hashlib.sha256(item.transcript.encode()).hexdigest()
    item.item_metadata = {**(item.item_metadata or {}), "transcript_source": "manual"}
    await log_audit_action(db, item.org_id, current_user.id, "CONTENT_TRANSCRIPT_SET", "CONTENT", str(item.id), {"characters": len(item.transcript)})
    await db.commit()
    if payload.analyze:
        job = await _start_job(db, item, current_user, force=False)
        await pipeline.submit(job.id)
        await db.refresh(item)
    return await _detail(db, item)


@router.put("/{content_id}/analysis", response_model=s.ContentDetail)
async def update_analysis(
    content_id: UUID,
    payload: s.AnalysisUpdate,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Edit the objectives and the competency decisions (link / create / skip). Also how a hand-written analysis is entered."""
    item = await _load_item(db, tenant_ctx.org_id, content_id)
    analysis = dict(item.analysis or {"version": 1, "concepts": [], "competencies": [], "objectives": []})
    changes = payload.model_dump(exclude_unset=True)

    for key in ("summary", "level", "objectives"):
        if key in changes and changes[key] is not None:
            analysis[key] = changes[key]
    if changes.get("competencies") is not None:
        decisions: List[Dict[str, Any]] = []
        for decision in changes["competencies"]:
            if decision["action"] == "link":
                await _check_competency(db, item.org_id, decision["competency_id"])
                decision["competency_id"] = str(decision["competency_id"])
            else:
                decision["competency_id"] = None
            decisions.append(decision)
        analysis["competencies"] = decisions
    analysis["edited"] = True
    item.analysis = analysis
    await db.flush()
    return await _detail(db, item)


# ---------------------------------------------------------------------------- candidates
@router.post("/{content_id}/candidates", response_model=s.CandidateOut, status_code=status.HTTP_201_CREATED)
async def add_candidate(
    content_id: UUID,
    payload: s.CandidateCreate,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Write a question by hand. It starts approved: the author has, by definition, reviewed it."""
    item = await _load_item(db, tenant_ctx.org_id, content_id)
    await _check_competency(db, item.org_id, payload.competency_id)
    candidate = QuestionCandidate(
        org_id=item.org_id, content_item_id=item.id, question_text=" ".join(payload.question_text.split()),
        question_type=payload.question_type,
        options=[{"id": chr(97 + i), "text": o.text, "is_correct": o.is_correct} for i, o in enumerate(payload.options)],
        expected_answer=(payload.expected_answer or "").strip() or None,
        rubric=[c.model_dump() for c in payload.rubric] if payload.rubric else None,
        explanation=payload.explanation, difficulty=payload.difficulty, competency_id=payload.competency_id,
        competency_name=payload.competency_name, source_quote=payload.source_quote, origin="manual", status="approved",
        created_by_id=current_user.id, reviewed_by_id=current_user.id,
    )
    db.add(candidate)
    await db.flush()
    return _candidate_out(candidate)


@router.put("/candidates/{candidate_id}", response_model=s.CandidateOut)
async def edit_candidate(
    candidate_id: UUID,
    payload: s.CandidateUpdate,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    candidate = await _load_candidate(db, tenant_ctx.org_id, candidate_id)
    if candidate.status == "published":
        raise HTTPException(status_code=409, detail={"code": "already_published", "message": "Published questions cannot be edited here."})
    changes = payload.model_dump(exclude_unset=True)
    if "competency_id" in changes:
        await _check_competency(db, candidate.org_id, changes["competency_id"])
        candidate.competency_id = changes["competency_id"]
    if changes.get("question_text"):
        candidate.question_text = " ".join(changes["question_text"].split())
    written = candidate.question_type in s.WRITTEN_TYPES
    if written and changes.get("options") is not None:
        raise HTTPException(status_code=422, detail={"code": "written_has_no_options", "message": "A written question has no options."})
    if not written and (changes.get("expected_answer") is not None or changes.get("rubric") is not None):
        raise HTTPException(status_code=422, detail={"code": "not_written", "message": "Only written questions have an expected answer or a rubric."})
    if "expected_answer" in changes:
        candidate.expected_answer = (changes["expected_answer"] or "").strip() or None
    if changes.get("rubric") is not None:
        candidate.rubric = changes["rubric"]
    if written and not candidate.expected_answer and not candidate.rubric:
        raise HTTPException(status_code=422, detail={"code": "needs_grading_basis", "message": "A written question needs an expected answer or a rubric."})
    if changes.get("options") is not None:
        candidate.options = [{"id": chr(97 + i), "text": o["text"], "is_correct": o["is_correct"]} for i, o in enumerate(changes["options"])]
    for field in ("explanation", "difficulty", "competency_name"):
        if field in changes:
            setattr(candidate, field, changes[field])
    candidate.edited = True
    await db.flush()
    return _candidate_out(candidate)


@router.post("/candidates/{candidate_id}/status", response_model=s.CandidateOut)
async def set_candidate_status(
    candidate_id: UUID,
    payload: s.CandidateStatusUpdate,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime

    candidate = await _load_candidate(db, tenant_ctx.org_id, candidate_id)
    if candidate.status == "published":
        raise HTTPException(status_code=409, detail={"code": "already_published", "message": "This question is already published."})
    candidate.status = payload.status
    candidate.reviewed_by_id, candidate.reviewed_at = current_user.id, datetime.utcnow()
    await db.flush()
    return _candidate_out(candidate)


@router.post("/{content_id}/candidates/status", response_model=List[s.CandidateOut])
async def bulk_candidate_status(
    content_id: UUID,
    payload: s.BulkCandidateStatus,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject several questions at once (for example "approve all")."""
    from datetime import datetime

    item = await _load_item(db, tenant_ctx.org_id, content_id)
    rows = (await db.execute(
        select(QuestionCandidate).where(
            QuestionCandidate.content_item_id == item.id, QuestionCandidate.org_id == item.org_id,
            QuestionCandidate.id.in_(payload.ids), QuestionCandidate.status != "published",
        )
    )).scalars().all()
    for row in rows:
        row.status, row.reviewed_by_id, row.reviewed_at = payload.status, current_user.id, datetime.utcnow()
    await db.flush()
    return [_candidate_out(r) for r in rows]


@router.delete("/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: UUID,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    candidate = await _load_candidate(db, tenant_ctx.org_id, candidate_id)
    if candidate.status == "published":
        raise HTTPException(status_code=409, detail={"code": "already_published", "message": "Published questions cannot be deleted here."})
    await db.delete(candidate)


# ----------------------------------------------------------------------------- publish
@router.post("/{content_id}/publish", response_model=s.PublishResponse)
async def publish(
    content_id: UUID,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Publish the reviewed content: apply competency decisions and turn approved questions into a quiz."""
    item = await _load_item(db, tenant_ctx.org_id, content_id)
    ready = await readiness(db, item)
    if not ready.can_publish:
        raise HTTPException(status_code=409, detail={"code": "not_publishable", "message": " ".join(ready.blockers), "blockers": ready.blockers})

    module = await _load_module(db, item.org_id, item.module_id)
    result = await publish_content(db, item, module, current_user.id)
    await log_audit_action(db, item.org_id, current_user.id, "CONTENT_PUBLISHED", "CONTENT", str(item.id), {
        "competencies_created": result.competencies_created, "questions_published": result.questions_published,
    })
    return s.PublishResponse(
        content_id=item.id, status=item.status, competencies_created=result.competencies_created,
        competencies_linked=result.competencies_linked, questions_published=result.questions_published,
        quiz_content_id=result.quiz_item_id,
    )


@router.post("/{content_id}/unpublish", response_model=s.ContentDetail)
async def unpublish(
    content_id: UUID,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Take content away from learners (progress is kept). It returns to review."""
    item = await _load_item(db, tenant_ctx.org_id, content_id)
    if item.status != "published":
        raise HTTPException(status_code=409, detail={"code": "not_published", "message": "This content is not published."})
    item.status = "review"
    await log_audit_action(db, item.org_id, current_user.id, "CONTENT_UNPUBLISHED", "CONTENT", str(item.id), {})
    await db.flush()
    return await _detail(db, item)


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content(
    content_id: UUID,
    current_user: User = Depends(require_roles(_ADMINS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete unpublished content and its stored file. Published content must be unpublished first."""
    item = await _load_item(db, tenant_ctx.org_id, content_id)
    if item.status == "published":
        raise HTTPException(status_code=409, detail={"code": "published", "message": "Unpublish this content before deleting it."})
    if item.status == "processing":
        raise HTTPException(status_code=409, detail={"code": "already_processing", "message": "Wait for processing to finish."})

    activity = (await db.execute(select(func.count()).select_from(LearningEvent).where(LearningEvent.content_id == item.id))).scalar() or 0
    if activity:
        raise HTTPException(status_code=409, detail={
            "code": "has_learner_activity",
            "message": f"Learners have {activity} recorded events on this content, which are evidence and are never deleted. Unpublish it instead.",
        })

    key = item.content_url if item.source_type == "upload" else None
    await db.execute(delete(IngestionJob).where(IngestionJob.content_item_id == item.id, IngestionJob.org_id == item.org_id))
    await log_audit_action(db, item.org_id, current_user.id, "CONTENT_DELETED", "CONTENT", str(item.id), {"title": item.title})
    await db.delete(item)
    await db.flush()
    if key:
        try:
            await storage_client.delete_file(key)
        except Exception:
            logger.warning("could not delete stored file %s", key)
