"""
Learning events: ingestion of learner interaction, and queries over the event store.

    POST /events           report one interaction event
    POST /events/batch     report several, all or nothing
    GET  /events           query (filters, keyset pagination)
    GET  /events/stats     counts by type and by day
    GET  /events/{id}      one event

What a browser may report is limited to interaction the server cannot observe (a lesson
opened, a video played, a question shown). Facts the server establishes (a graded answer,
a completed lesson, a grade) are recorded by server code and are refused here, so a
learner cannot write evidence about themselves. The tenant and the learner are taken from
the authenticated user; course, module and competency are derived from the referenced
item, never trusted from the request.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, get_current_user, get_db, require_roles
from app.core.config import settings
from app.events import queries, sessions, store
from app.events.vocabulary import LEARNER, VocabularyError, learner_types, normalise, spec_for
from app.models import Assignment, ContentItem, Quiz, QuizAttempt, QuizQuestion, User

router = APIRouter(prefix="/events", tags=["Learning Events"])


# ---------------------------------------------------------------------------- ingestion
class ClientEvent(BaseModel):
    event_type: str = Field(..., max_length=100)
    # Makes a retry harmless: the same key in the same tenant is recorded once. `event_id` is the
    # older name for the same thing; it is a key, never the event's primary key.
    idempotency_key: Optional[str] = Field(None, max_length=64)
    event_id: Optional[UUID] = None
    content_id: Optional[UUID] = None
    question_id: Optional[UUID] = None
    course_id: Optional[UUID] = Field(None, description="Optional; checked against the item, never used to override it")
    session_id: Optional[UUID] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = Field(None, description="When it happened in the browser; bounded by the server")


class ClientBatch(BaseModel):
    events: List[ClientEvent] = Field(..., min_length=1)


def _bad(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


def bound_client_time(claimed: Optional[datetime], now: datetime) -> datetime:
    """A browser's timestamp, unless it is impossible (in the future, or long ago): then the server's time."""
    if claimed is None:
        return now
    if claimed.tzinfo is not None:  # stored times are naive UTC
        claimed = claimed.astimezone(timezone.utc).replace(tzinfo=None)
    if claimed > now + timedelta(seconds=settings.event_client_clock_skew_seconds):
        return now
    if claimed < now - timedelta(hours=settings.event_client_max_age_hours):
        return now
    return claimed


async def _resolve(db: AsyncSession, org_id: UUID, user: User, item: ClientEvent, event_type: str) -> Dict[str, Any]:
    """The references an event really has, derived from the items it names (tenant-checked)."""
    refs: Dict[str, Any] = {"content_id": None, "assessment_id": None, "question_id": None, "competency_id": None,
                            "course_id": None, "module_id": None}
    payload = dict(item.payload)

    if event_type in ("question_shown", "hint_requested"):
        if item.question_id is None:
            raise _bad(422, "missing_reference", f"{event_type} needs question_id.")
        row = (await db.execute(
            select(QuizQuestion, Quiz).join(Quiz, Quiz.id == QuizQuestion.quiz_id)
            .where(QuizQuestion.id == item.question_id, Quiz.org_id == org_id)
        )).first()
        if row is None:
            raise _bad(404, "not_found", "Question not found.")
        question, quiz = row
        attempt_id = payload.get("attempt_id")
        attempt = None
        if attempt_id:
            try:
                attempt = (await db.execute(
                    select(QuizAttempt).where(QuizAttempt.id == UUID(str(attempt_id)), QuizAttempt.user_id == user.id, QuizAttempt.quiz_id == quiz.id)
                )).scalar_one_or_none()
            except ValueError:
                attempt = None
        if attempt is None:
            raise _bad(422, "invalid_attempt", "attempt_id does not name one of your attempts at this assessment.")
        if attempt.completed_at is not None:
            # Browsers report in batches, so the last question's "shown" can arrive just after the attempt was
            # submitted. Judge it by when it HAPPENED: before the submission it is genuine, after it is not.
            happened = bound_client_time(item.timestamp, datetime.utcnow()) if item.timestamp is not None else None
            if happened is None or happened > attempt.completed_at:
                raise _bad(409, "attempt_finished", "That attempt has already been submitted.")
        refs.update(assessment_id=quiz.id, question_id=question.id, competency_id=question.competency_id,
                    course_id=quiz.course_id, module_id=quiz.module_id, content_id=quiz.content_item_id)
    elif event_type == "assignment_opened":
        try:
            assignment_id = UUID(str(payload.get("assignment_id")))
        except ValueError:
            raise _bad(422, "invalid_payload", "assignment_opened needs a valid assignment_id.")
        assignment = (await db.execute(select(Assignment).where(Assignment.id == assignment_id, Assignment.org_id == org_id))).scalar_one_or_none()
        if assignment is None:
            raise _bad(404, "not_found", "Assignment not found.")
        refs.update(content_id=assignment.content_item_id, course_id=assignment.course_id, module_id=assignment.module_id,
                    competency_id=assignment.competency_id)
    else:
        if item.content_id is None:
            raise _bad(422, "missing_reference", f"{event_type} needs content_id.")
        content = (await db.execute(select(ContentItem).where(ContentItem.id == item.content_id, ContentItem.org_id == org_id))).scalar_one_or_none()
        if content is None:
            raise _bad(404, "not_found", "Content not found.")
        refs.update(content_id=content.id, course_id=content.course_id, module_id=content.module_id)

    if item.course_id is not None and refs["course_id"] is not None and item.course_id != refs["course_id"]:
        raise _bad(422, "reference_mismatch", "course_id does not match the item's course.")
    return refs


async def _ingest_one(db: AsyncSession, org_id: UUID, user: User, item: ClientEvent, now: datetime) -> Dict[str, Any]:
    event_type = normalise(item.event_type)
    try:
        spec = spec_for(event_type)
    except VocabularyError as exc:
        raise _bad(422, exc.code, str(exc), accepted=list(learner_types()))
    if spec.source != LEARNER:
        raise _bad(403, "server_only_event", f"'{event_type}' is recorded by the server; it cannot be reported by a client.")

    refs = await _resolve(db, org_id, user, item, event_type)
    raw_key = item.idempotency_key or (str(item.event_id) if item.event_id else None)
    # Keys are unique per tenant in the database; prefixing the learner makes them per learner, so one
    # learner's key can never suppress another's event.
    key = f"{user.id}:{raw_key}" if raw_key else None

    when = bound_client_time(item.timestamp, now)
    session_id = None
    if item.session_id is not None:
        try:
            session_id = (await sessions.require_open(db, item.session_id, org_id=org_id, user_id=user.id, now=now, happened_at=when)).id
        except sessions.SessionError as exc:
            raise _bad(exc.status_code, exc.code, str(exc))

    try:
        recorded = await store.record(
            db, org_id=org_id, user_id=user.id, event_type=event_type, course_id=refs["course_id"], module_id=refs["module_id"],
            content_id=refs["content_id"], assessment_id=refs["assessment_id"], question_id=refs["question_id"],
            competency_id=refs["competency_id"], session_id=session_id, payload=item.payload,
            timestamp=when, idempotency_key=key,
        )
    except VocabularyError as exc:
        raise _bad(422, exc.code, str(exc))

    event = recorded.event
    return {
        "status": "ingested" if recorded.created else "duplicate_ignored",
        "event_id": str(event.id), "event_type": event.event_type,
        "session_id": str(event.session_id) if event.session_id else None,
        "timestamp": event.timestamp.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def ingest_event(
    payload: ClientEvent,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Report one interaction event. Retrying with the same idempotency key records it once."""
    return await _ingest_one(db, tenant_ctx.org_id, current_user, payload, datetime.utcnow())


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def ingest_batch(
    batch: ClientBatch,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Report several events; all are recorded or none are (the error names the failing index)."""
    if len(batch.events) > settings.event_max_client_batch:
        raise _bad(422, "batch_too_large", f"At most {settings.event_max_client_batch} events per batch.")
    now = datetime.utcnow()
    results = []
    for index, item in enumerate(batch.events):
        try:
            results.append(await _ingest_one(db, tenant_ctx.org_id, current_user, item, now))
        except HTTPException as exc:
            detail = dict(exc.detail) if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            raise HTTPException(status_code=exc.status_code, detail={**detail, "index": index})
    return {"status": "batch_ingested", "count": len(results), "events": results}


# ------------------------------------------------------------------------------- queries
def _filter(
    user_id, session_id, course_id, module_id, content_id, assessment_id, question_id, competency_id, event_type, since, until,
) -> queries.EventFilter:
    types = [normalise(t) for t in event_type or [] if t]
    return queries.EventFilter(
        user_id=user_id, session_id=session_id, course_id=course_id, module_id=module_id, content_id=content_id,
        assessment_id=assessment_id, question_id=question_id, competency_id=competency_id, event_types=types, since=since, until=until,
    )


@router.get("")
async def query_events(
    user_id: Optional[UUID] = None,
    session_id: Optional[UUID] = None,
    course_id: Optional[UUID] = None,
    module_id: Optional[UUID] = None,
    content_id: Optional[UUID] = None,
    assessment_id: Optional[UUID] = None,
    question_id: Optional[UUID] = None,
    competency_id: Optional[UUID] = None,
    event_type: Optional[List[str]] = Query(None, description="Repeat to match several types"),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Events the caller may see: a learner's own; a manager's team as well; everyone's for L&D and
    org admins. Filters combine. `next_cursor` continues the listing; it is null on the last page.
    """
    visible = await queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    flt = _filter(user_id, session_id, course_id, module_id, content_id, assessment_id, question_id, competency_id, event_type, since, until)
    try:
        rows, next_cursor = await queries.list_events(db, tenant_ctx.org_id, visible, flt, limit=limit, cursor=cursor, ascending=order == "asc")
    except queries.QueryError as exc:
        raise _bad(422, "invalid_cursor", str(exc))
    return {"items": [queries.event_out(e) for e in rows], "next_cursor": next_cursor}


@router.get("/stats")
async def event_stats(
    user_id: Optional[UUID] = None,
    course_id: Optional[UUID] = None,
    event_type: Optional[List[str]] = Query(None),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    current_user: User = Depends(require_roles(["ld_admin", "org_admin", "manager"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Event volume by type and by day, for what the caller may see (managers: their team)."""
    visible = await queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    flt = _filter(user_id, None, course_id, None, None, None, None, None, event_type, since, until)
    return await queries.stats(db, tenant_ctx.org_id, visible, flt)


@router.get("/{event_id}")
async def get_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    visible = await queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    event = await queries.get_event(db, tenant_ctx.org_id, visible, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return queries.event_out(event)
