"""
Learning sessions.

    POST /learning/sessions/start           start, or resume the open session for a course
    GET  /learning/sessions/active          the caller's open session (optionally for one course)
    POST /learning/sessions/{id}/heartbeat  record activity (a long video with no other events)
    POST /learning/sessions/{id}/end        end it
    GET  /learning/sessions                 list (own; team for managers; everyone for admins)
    GET  /learning/sessions/{id}            details and a summary counted from its events
    GET  /learning/sessions/{id}/events     its events, oldest first

A session is a real record (started_at, ended_at, context), and every course event the
learner produces while it is open carries its id. Course activity with no open session
starts one implicitly, so nothing is left outside a session.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, get_current_user, get_db
from app.events import queries, sessions
from app.models import Course, LearningSession, User

router = APIRouter(prefix="/learning/sessions", tags=["Learning Sessions"])


class StartSession(BaseModel):
    course_id: UUID
    # What the player knows about how learning began: where from, and the first item. Small and free-form.
    context: Dict[str, Any] = Field(default_factory=dict)


class EndSession(BaseModel):
    reason: str = Field("explicit", pattern="^explicit$")


def _detail(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


async def _own_session(db: AsyncSession, org_id: UUID, user: User, session_id: UUID) -> LearningSession:
    session = (await db.execute(
        select(LearningSession).where(LearningSession.id == session_id, LearningSession.org_id == org_id, LearningSession.user_id == user.id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/start", status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: StartSession,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Start a session for a course, or resume the one already open (quiet for under the idle limit)."""
    course = (await db.execute(select(Course.id).where(Course.id == payload.course_id, Course.org_id == tenant_ctx.org_id))).scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    context = {k: v for k, v in payload.context.items() if isinstance(k, str) and len(k) <= 40}
    if len(str(context)) > 2000:
        raise HTTPException(status_code=422, detail=_detail("context_too_large", "The session context is too large."))
    context.setdefault("source", "player")

    session, created = await sessions.start(db, org_id=tenant_ctx.org_id, user_id=current_user.id, course_id=payload.course_id, context=context)
    return {**queries.session_out(session), "status": "created" if created else "resumed"}


@router.get("/active")
async def active_session(
    course_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """The caller's open session, if any. One that has gone quiet is closed here, at its last activity."""
    session = await sessions.open_session(db, org_id=tenant_ctx.org_id, user_id=current_user.id, course_id=course_id) if course_id else (
        await db.execute(
            select(LearningSession).where(
                LearningSession.org_id == tenant_ctx.org_id, LearningSession.user_id == current_user.id, LearningSession.ended_at.is_(None)
            ).order_by(LearningSession.last_activity_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if session is not None and await sessions.close_if_idle(db, session):
        session = None
    return {"active": session is not None, "session": queries.session_out(session) if session else None}


@router.post("/{session_id}/heartbeat")
async def heartbeat(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Record that the learner is still here. 409 when the session has already ended: start a new one."""
    try:
        session = await sessions.require_open(db, session_id, org_id=tenant_ctx.org_id, user_id=current_user.id)
    except sessions.SessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=_detail(exc.code, str(exc)))
    await sessions.touch(db, session.id, datetime.utcnow())
    await db.refresh(session)
    return queries.session_out(session)


@router.post("/{session_id}/end")
async def end_session(
    session_id: UUID,
    payload: Optional[EndSession] = None,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """End a session. Ending one that already ended returns it unchanged."""
    session = await _own_session(db, tenant_ctx.org_id, current_user, session_id)
    if session.ended_at is None:
        await sessions.end(db, session, reason="explicit")
    return queries.session_out(session)


@router.get("")
async def list_sessions(
    user_id: Optional[UUID] = None,
    course_id: Optional[UUID] = None,
    active: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    visible = await queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    rows = await queries.list_sessions(db, tenant_ctx.org_id, visible, user_id=user_id, course_id=course_id, active=active, limit=limit, offset=offset)
    return {"items": [queries.session_out(s) for s in rows]}


@router.get("/{session_id}")
async def session_details(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    visible = await queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    session = await queries.get_session(db, tenant_ctx.org_id, visible, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {**queries.session_out(session), "summary": await queries.session_summary(db, session)}


@router.get("/{session_id}/events")
async def session_events(
    session_id: UUID,
    limit: int = Query(200, ge=1, le=500),
    cursor: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """A session's events in the order they happened."""
    visible = await queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    session = await queries.get_session(db, tenant_ctx.org_id, visible, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        rows, next_cursor = await queries.list_events(
            db, tenant_ctx.org_id, visible, queries.EventFilter(session_id=session.id), limit=limit, cursor=cursor, ascending=True
        )
    except queries.QueryError as exc:
        raise HTTPException(status_code=422, detail=_detail("invalid_cursor", str(exc)))
    return {"session": queries.session_out(session), "items": [queries.event_out(e) for e in rows], "next_cursor": next_cursor}
