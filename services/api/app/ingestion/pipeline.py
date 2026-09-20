"""
The ingestion pipeline: turns a stored file or a YouTube link into reviewable course content.

    acquire text   extract (documents) | transcribe (audio/video) | metadata + captions (YouTube)
    chunk          split into overlapping passages
    analyze        objectives, concepts, competencies        (AI, verified)
    questions      grounded multiple-choice candidates       (AI, verified)
    embed          vectors for later retrieval               (optional)

Design rules:

  * Every stage is recorded on the job (status, timing, detail, error) and committed as it
    finishes, so the admin UI can show real progress by polling.
  * A failure is contained to its stage and named. Extraction failing is a hard failure
    (the job is `failed`). AI failing, or a missing transcript, leaves the content in
    review with the job `needs_attention`: the administrator can retry, paste a
    transcript, or author objectives and questions by hand. No stage ever substitutes
    invented output.
  * Unchanged content is not re-analysed (its hash and the prompt version are compared),
    which avoids repeat AI calls.
  * Jobs that a crash left in `processing` are marked interrupted on the next startup.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.storage import storage_client
from app.ingestion import prompts
from app.ingestion.analysis import ExistingCompetency, analyze_content, generate_questions
from app.ingestion.embeddings import get_embedder
from app.ingestion.errors import (
    EmptyContent,
    IngestionError,
    NoTranscript,
    TranscriptionUnavailable,
)
from app.ingestion.transcription import get_transcriber
from app.ingestion.youtube import YouTubeClient
from app.models import (
    Competency,
    ContentChunk,
    ContentItem,
    IngestionJob,
    QuestionCandidate,
)
from shared.parsers import ExtractionError, SemanticChunker, TextExtractor

logger = logging.getLogger("api.ingestion")

DOC_STAGES = ["extract", "chunk", "analyze", "questions", "embed"]
MEDIA_STAGES = ["transcribe", "chunk", "analyze", "questions", "embed"]
YOUTUBE_STAGES = ["metadata", "chunk", "analyze", "questions", "embed"]
TEXT_STAGES = ["chunk", "analyze", "questions", "embed"]  # analysing text already stored on the item

# A missing or private video cannot be repaired by the administrator; a missing transcript can.
HARD_YOUTUBE_ERRORS = {"video_unavailable", "invalid_url"}

# Stages whose failure leaves the content usable but incomplete (job = needs_attention).
SOFT_STAGES = {"analyze", "questions", "embed", "transcribe", "metadata"}


def stages_for(source_type: str, kind: str) -> List[str]:
    if source_type == "youtube":
        return YOUTUBE_STAGES
    if source_type == "text":
        return TEXT_STAGES
    return MEDIA_STAGES if kind in ("video", "audio") else DOC_STAGES


def initial_stages(source_type: str, kind: str) -> List[Dict[str, Any]]:
    return [{"name": n, "status": "pending"} for n in stages_for(source_type, kind)]


# --------------------------------------------------------------------- injectable pieces
_youtube_override: Optional[YouTubeClient] = None
_session_factory: Callable[[], Any] = AsyncSessionLocal


def set_youtube_override(client: Optional[YouTubeClient]) -> None:
    global _youtube_override
    _youtube_override = client


def set_session_factory(factory: Optional[Callable[[], Any]]) -> None:
    """Tests give the pipeline the same engine the request handlers use."""
    global _session_factory
    _session_factory = factory or AsyncSessionLocal


def get_youtube_client() -> YouTubeClient:
    return _youtube_override or YouTubeClient()


def _count(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


# ------------------------------------------------------------------------ stage tracking
class Tracker:
    """Reads and writes the per-stage log stored on the job, committing after every change."""

    def __init__(self, db: AsyncSession, job: IngestionJob, item: Optional[ContentItem] = None):
        self.db, self.job, self.item = db, job, item

    async def rollback(self) -> None:
        """Discard a failed stage's uncommitted work; a rollback expires loaded rows, so reload the ones still in use."""
        await self.db.rollback()
        await self.db.refresh(self.job)
        if self.item is not None:
            await self.db.refresh(self.item)

    def _mutate(self, name: str, **changes: Any) -> None:
        stages = [dict(s) for s in (self.job.stages or [])]
        for stage in stages:
            if stage["name"] == name:
                stage.update(changes)
                break
        else:
            stages.append({"name": name, **changes})
        self.job.stages = stages  # reassign so SQLAlchemy sees the change
        self.job.stage = name
        self.job.updated_at = datetime.utcnow()

    async def begin(self, name: str) -> None:
        self._mutate(name, status="running", started_at=datetime.utcnow().isoformat(), error=None, detail=None)
        await self.db.commit()
        _log("ingestion_stage_started", job_id=self.job.id, stage=name)

    async def done(self, name: str, detail: Optional[str] = None, status: str = "done") -> None:
        self._mutate(name, status=status, finished_at=datetime.utcnow().isoformat(), detail=detail)
        await self.db.commit()
        _log("ingestion_stage_finished", job_id=self.job.id, stage=name, status=status, detail=detail)

    async def failed(self, name: str, error: IngestionError | Exception) -> None:
        code = getattr(error, "code", "internal_error")
        message = str(error) if isinstance(error, IngestionError) else "An unexpected error occurred. See the server log."
        self._mutate(name, status="failed", finished_at=datetime.utcnow().isoformat(), error={"code": code, "message": message})
        await self.db.commit()
        _log("ingestion_stage_failed", job_id=self.job.id, stage=name, code=code, message=message)

    async def skipped(self, name: str, reason: str) -> None:
        await self.done(name, detail=reason, status="skipped")

    def status_of(self, name: str) -> Optional[str]:
        return next((s["status"] for s in (self.job.stages or []) if s["name"] == name), None)


# ----------------------------------------------------------------------------- the runner
async def run_job(job_id: UUID, *, force: bool = False) -> None:
    async with _session_factory() as db:
        job = await db.get(IngestionJob, job_id)
        if job is None:
            return
        item = await db.get(ContentItem, job.content_item_id) if job.content_item_id else None
        if item is None:
            job.status, job.error_code, job.error_message = "failed", "content_missing", "The content item no longer exists."
            await db.commit()
            return

        job.status, job.attempts, job.started_at = "processing", job.attempts + 1, datetime.utcnow()
        job.error_code = job.error_message = None
        job.stages = initial_stages(job.source_type, _kind_of(job))
        item.status = "processing"
        await db.commit()
        _log("ingestion_started", job_id=job.id, org_id=job.org_id, source=job.source_type, attempt=job.attempts, force=force)

        try:
            await _run(db, job, item, force)
        except Exception:  # last-resort: never leave a job stuck in "processing"
            logger.exception("ingestion job %s crashed", job_id)
            await db.rollback()
            job = await db.get(IngestionJob, job_id)
            item = await db.get(ContentItem, job.content_item_id)
            job.status, job.error_code = "failed", "internal_error"
            job.error_message = "An unexpected error stopped processing. See the server log."
            item.status = "failed"
            await db.commit()


def _kind_of(job: IngestionJob) -> str:
    return "video" if job.file_type in ("mp4", "mov", "webm") else "audio" if job.file_type in ("mp3", "wav", "m4a") else "document"


async def _run(db: AsyncSession, job: IngestionJob, item: ContentItem, force: bool) -> None:
    tracker = Tracker(db, job, item)
    text: Optional[str] = None

    # ---- 1. acquire text --------------------------------------------------------------------
    if job.source_type == "text":
        text = (item.text_content or item.raw_text or item.transcript or "").strip() or None
        if text:
            item.content_hash = _sha256(text)
    elif job.source_type == "youtube":
        text = await _acquire_youtube(db, job, item, tracker)
        failure = next((st.get("error") or {} for st in (job.stages or []) if st["status"] == "failed"), {})
        if text is None and failure.get("code") in HARD_YOUTUBE_ERRORS:  # nothing can be learned from it
            await _skip_remaining(tracker, ["chunk", "analyze", "questions", "embed"], "Skipped because the video cannot be used.")
            await _fail_hard(db, job, item)
            return
    elif _kind_of(job) in ("video", "audio"):
        text = await _acquire_media(db, job, item, tracker)
    else:
        text = await _acquire_document(db, job, item, tracker)
        if text is None:  # extraction is a hard requirement for documents
            await _skip_remaining(tracker, ["chunk", "analyze", "questions", "embed"], "Skipped because the text could not be extracted.")
            await _fail_hard(db, job, item)
            return

    if not text:
        await _skip_remaining(tracker, ["chunk", "analyze", "questions", "embed"], "There is no text to analyse yet.")
        await _finish(db, job, item, tracker)
        return

    # ---- 2. chunk ---------------------------------------------------------------------------
    chunks = await _stage(tracker, "chunk", lambda: _chunk(db, item, text), lambda c: f"{_count(len(c), 'passage')}.")
    if not chunks:
        await _skip_remaining(tracker, ["analyze", "questions", "embed"], "The text could not be split into passages.")
        await _finish(db, job, item, tracker)
        return

    text_hash = _sha256(text)
    input_hash = f"{text_hash}:{prompts.PROMPT_VERSION}"

    # ---- 3. analyse -------------------------------------------------------------------------
    analysis = await _stage(tracker, "analyze", lambda: _analyze(db, item, chunks, input_hash, force, tracker))

    # ---- 4. questions -----------------------------------------------------------------------
    if analysis is None:
        await tracker.skipped("questions", "Skipped because the analysis did not complete.")
    else:
        await _stage(tracker, "questions", lambda: _questions(db, item, chunks, analysis, input_hash, force, tracker))

    # ---- 5. embeddings (optional) -----------------------------------------------------------
    await _stage(tracker, "embed", lambda: _embed(db, item, chunks, tracker))

    await _finish(db, job, item, tracker)


async def _stage(
    tracker: Tracker, name: str, fn: Callable[[], Awaitable[Any]], describe: Optional[Callable[[Any], str]] = None
) -> Any:
    """
    Run one stage, recording success or the specific failure. Never raises for a stage's own errors.

    A stage that finishes without calling `tracker.done/skipped` itself is marked done here,
    with `describe(result)` as its detail.
    """
    await tracker.begin(name)
    try:
        result = await fn()
        if tracker.status_of(name) == "running":
            await tracker.done(name, detail=describe(result) if describe and result else None)
        return result
    except IngestionError as exc:
        await tracker.rollback()
        await tracker.failed(name, exc)
    except Exception as exc:
        logger.exception("ingestion stage %s crashed", name)
        await tracker.rollback()
        await tracker.failed(name, exc)
    return None


async def _skip_remaining(tracker: Tracker, names: List[str], reason: str) -> None:
    for name in names:
        if tracker.status_of(name) == "pending":
            await tracker.skipped(name, reason)


async def _finish(db: AsyncSession, job: IngestionJob, item: ContentItem, tracker: Tracker) -> None:
    stages = job.stages or []
    failed = [s for s in stages if s["status"] == "failed"]
    job.stage = None
    job.completed_at = None
    item.status = "review"
    if failed:
        first = failed[0]["error"] or {}
        job.status = "needs_attention"
        job.error_code, job.error_message = first.get("code"), first.get("message")
    else:
        job.status = "ready_for_review"
    job.result_summary = {
        **(job.result_summary or {}),
        "stages": {s["name"]: s["status"] for s in stages},
        "chunks": len(await _chunk_rows(db, item)),
    }
    await db.commit()
    _log("ingestion_finished", job_id=job.id, status=job.status, error_code=job.error_code)


async def _fail_hard(db: AsyncSession, job: IngestionJob, item: ContentItem) -> None:
    """Nothing usable was produced: the item is marked failed and the reason is taken from the failed stage."""
    first = next((s for s in (job.stages or []) if s["status"] == "failed"), None)
    error = (first or {}).get("error") or {}
    job.stage = None
    job.status, job.completed_at = "failed", datetime.utcnow()
    job.error_code, job.error_message = error.get("code"), error.get("message")
    item.status = "failed"
    await db.commit()
    _log("ingestion_failed", job_id=job.id, error_code=job.error_code)


async def _chunk_rows(db: AsyncSession, item: ContentItem) -> List[ContentChunk]:
    return list((await db.execute(select(ContentChunk).where(ContentChunk.content_item_id == item.id))).scalars())


# --------------------------------------------------------------------------- acquisition
async def _acquire_document(db, job, item, tracker) -> Optional[str]:
    async def extract() -> str:
        try:
            data = await storage_client.download_file(job.storage_path)
        except Exception as exc:
            raise IngestionError(f"The stored file could not be retrieved: {exc}", code="storage_unavailable") from exc
        try:
            text, meta = TextExtractor.extract_from_bytes(data, job.file_name)
        except ExtractionError as exc:
            raise IngestionError(str(exc), code=exc.code) from exc
        if len(text) < settings.ingestion_min_text_chars:
            raise EmptyContent(
                f"Only {len(text)} characters of text were found. Scanned or image-only documents cannot be read; "
                f"at least {settings.ingestion_min_text_chars} characters are needed."
            )
        item.raw_text = text
        item.text_content = text if item.content_type == "ARTICLE" else item.text_content
        item.content_hash = _sha256(text)
        item.item_metadata = {**(item.item_metadata or {}), **meta}
        await db.commit()
        return text

    return await _stage(tracker, "extract", extract, lambda t: f"{len(t):,} characters of text extracted.")


async def _acquire_media(db, job, item, tracker) -> Optional[str]:
    async def transcribe() -> str:
        if item.transcript and (item.item_metadata or {}).get("transcript_source") == "manual":
            return item.transcript  # an administrator supplied it; do not overwrite
        transcriber = get_transcriber()  # raises TranscriptionUnavailable with an actionable message
        try:
            data = await storage_client.download_file(job.storage_path)
        except Exception as exc:
            raise IngestionError(f"The stored file could not be retrieved: {exc}", code="storage_unavailable") from exc
        text = (await transcriber.transcribe(data, job.file_type)).strip()
        if len(text) < settings.ingestion_min_text_chars:
            raise NoTranscript("The recording produced almost no speech, so there is nothing to analyse.")
        item.transcript = text
        item.item_metadata = {**(item.item_metadata or {}), "transcript_source": transcriber.name}
        item.content_hash = _sha256(text)
        await db.commit()
        return text

    return await _stage(tracker, "transcribe", transcribe, lambda t: f"{len(t):,} characters transcribed.")


async def _acquire_youtube(db, job, item, tracker) -> Optional[str]:
    async def metadata() -> Optional[str]:
        from app.ingestion.youtube import validate_youtube_url

        video_id = validate_youtube_url(job.source_url or "")
        video = await get_youtube_client().fetch(video_id)

        if item.title.startswith("YouTube video") or not item.title:
            item.title = video.title[:255]
        if video.duration_seconds:
            item.duration_seconds = video.duration_seconds
        if video.description and not item.description:
            item.description = video.description[:1000]
        meta = {
            **(item.item_metadata or {}),
            "provider": "youtube", "video_id": video_id, "author": video.author,
            "thumbnail_url": video.thumbnail_url, "warnings": video.warnings,
        }
        manual = (item.item_metadata or {}).get("transcript_source") == "manual" and item.transcript
        if video.transcript and not manual:
            item.transcript = video.transcript
            meta.update(transcript_source="youtube_captions", transcript_language=video.transcript_language,
                        transcript_kind=video.transcript_kind)
        item.item_metadata = meta
        text = item.transcript
        if text:
            item.content_hash = _sha256(text)
        await db.commit()
        if not text:
            raise NoTranscript(
                "This video has no captions, so there is no transcript to analyse. "
                "Paste a transcript to continue, or add objectives and questions by hand."
            )
        if len(text) < settings.ingestion_min_text_chars:
            raise NoTranscript("The video's transcript is too short to analyse.")
        return text

    return await _stage(tracker, "metadata", metadata, lambda t: f"Video details and a {len(t):,}-character transcript retrieved.")


# ------------------------------------------------------------------------------- stages
async def _chunk(db: AsyncSession, item: ContentItem, text: str) -> List[Dict[str, Any]]:
    chunks = SemanticChunker(target_chunk_size=350, overlap=50).chunk_text(text)
    await db.execute(delete(ContentChunk).where(ContentChunk.content_item_id == item.id))
    for chunk in chunks:
        db.add(ContentChunk(
            org_id=item.org_id, content_item_id=item.id, chunk_index=chunk["chunk_index"],
            text_content=chunk["text_content"], token_count=chunk["token_count"],
        ))
    item.chunk_count = len(chunks)
    await db.commit()
    return chunks


async def _existing_competencies(db: AsyncSession, org_id: UUID) -> List[ExistingCompetency]:
    rows = (
        await db.execute(select(Competency).where(Competency.org_id == org_id).order_by(Competency.name).limit(200))
    ).scalars().all()
    return [ExistingCompetency(id=str(c.id), code=c.code, name=c.name) for c in rows]


async def _analyze(db, item, chunks, input_hash, force, tracker) -> Optional[Dict[str, Any]]:
    current = item.analysis or {}
    if not force and current.get("input_hash") == input_hash and current.get("objectives"):
        await tracker.skipped("analyze", "Content unchanged since the last analysis; reused it.")
        return current

    outcome = await analyze_content(item.title, chunks, await _existing_competencies(db, item.org_id), input_hash)
    item.analysis = outcome.analysis
    await db.commit()
    await tracker.done(
        "analyze",
        f"{_count(len(outcome.analysis['objectives']), 'objective')}, {_count(len(outcome.analysis['competencies']), 'competency', 'competencies')} "
        f"({outcome.provider}).",
    )
    return outcome.analysis


async def _questions(db, item, chunks, analysis, input_hash, force, tracker) -> None:
    if not force and analysis.get("questions_input_hash") == input_hash:
        await tracker.skipped("questions", "Content unchanged since questions were last generated; reused them.")
        return

    competencies = [c for c in analysis.get("competencies", []) if c.get("action") != "skip"]
    outcome = await generate_questions(item.title, chunks, [c["name"] for c in competencies])

    # Replace earlier machine-generated, undecided questions. Anything an administrator approved,
    # rejected, edited or wrote is left alone.
    await db.execute(
        delete(QuestionCandidate).where(
            QuestionCandidate.content_item_id == item.id,
            QuestionCandidate.origin == "generated",
            QuestionCandidate.status == "pending",
            QuestionCandidate.edited.is_(False),
        )
    )
    by_name = {c["name"]: c for c in competencies}
    for q in outcome.accepted:
        match = by_name.get(q.competency_name or "")
        db.add(QuestionCandidate(
            org_id=item.org_id, content_item_id=item.id, question_text=q.question_text, options=q.options,
            explanation=q.explanation or None, difficulty=q.difficulty, source_quote=q.source_quote,
            chunk_index=q.chunk_index, origin="generated", status="pending",
            competency_id=UUID(match["competency_id"]) if match and match.get("competency_id") else None,
            competency_name=(match["name"] if match else q.competency_name),
        ))
    item.analysis = {**analysis, "questions_input_hash": input_hash, "question_rejections": outcome.rejected}
    await db.commit()

    detail = f"{len(outcome.accepted)} accepted, {len(outcome.rejected)} rejected ({outcome.provider})."
    if not outcome.accepted:
        detail = "No question passed verification against the material. " + detail
    await tracker.done("questions", detail)


async def _embed(db, item, chunks, tracker) -> None:
    embedder = get_embedder()
    if embedder is None:
        await tracker.skipped("embed", "No embedding model is configured (AI_EMBEDDING_MODEL).")
        return
    try:
        vectors = await embedder.embed([c["text_content"] for c in chunks])
    except Exception as exc:
        raise IngestionError(f"Embeddings could not be computed: {exc}", code="embedding_failed") from exc
    rows = await _chunk_rows(db, item)
    by_index = {r.chunk_index: r for r in rows}
    for chunk, vector in zip(chunks, vectors):
        row = by_index.get(chunk["chunk_index"])
        if row is not None:
            row.embedding, row.embedding_model = vector, embedder.model
    await db.commit()
    await tracker.done("embed", f"{len(vectors)} vectors ({embedder.model}).")


# ------------------------------------------------------------------------------- runner
_semaphore = asyncio.Semaphore(2)
_tasks: set = set()


async def submit(job_id: UUID, *, force: bool = False) -> None:
    """Start a job. Inline mode (tests) runs it now; otherwise it runs in the background."""
    if settings.ingestion_run_inline:
        await run_job(job_id, force=force)
        return

    async def guarded() -> None:
        async with _semaphore:
            await run_job(job_id, force=force)

    task = asyncio.create_task(guarded())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def recover_stale_jobs() -> int:
    """Mark jobs a crash or restart left in `processing` as interrupted, so nobody waits on them forever."""
    cutoff = datetime.utcnow() - timedelta(minutes=settings.ingestion_stale_minutes)
    async with _session_factory() as db:
        result = await db.execute(
            update(IngestionJob)
            .where(IngestionJob.status.in_(["processing", "pending"]), IngestionJob.updated_at < cutoff)
            .values(
                status="needs_attention", error_code="interrupted", stage=None,
                error_message="Processing was interrupted (the server restarted). Use Retry to run it again.",
            )
        )
        await db.commit()
        count = result.rowcount or 0
    if count:
        _log("ingestion_stale_jobs_recovered", count=count)
    return count
