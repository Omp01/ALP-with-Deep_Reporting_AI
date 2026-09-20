"""
Learning sessions.

A session is one period of learning by one learner in one course. It starts when the
player opens (explicitly) or when the learner's first course event arrives with no open
session (implicitly), and it ends when the player says so or when it has been idle too
long. An idle session is closed AT ITS LAST ACTIVITY, not at the moment someone notices,
so a forgotten tab never counts as hours of learning.

The database allows one open session per learner per course, so concurrent starts cannot
create two. Starting and ending a session are themselves events (`session_started`,
`session_completed`).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import LearningSession


class SessionError(Exception):
    def __init__(self, message: str, code: str, status_code: int = 409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def idle_limit() -> timedelta:
    return timedelta(minutes=settings.session_idle_minutes)


async def open_session(db: AsyncSession, *, org_id: UUID, user_id: UUID, course_id: Optional[UUID]) -> Optional[LearningSession]:
    query = select(LearningSession).where(
        LearningSession.org_id == org_id, LearningSession.user_id == user_id, LearningSession.ended_at.is_(None)
    )
    query = query.where(LearningSession.course_id == course_id) if course_id is not None else query.where(LearningSession.course_id.is_(None))
    return (await db.execute(query.order_by(LearningSession.started_at.desc()).limit(1))).scalar_one_or_none()


def is_idle(session: LearningSession, now: datetime) -> bool:
    return session.ended_at is None and now - session.last_activity_at > idle_limit()


async def _emit(db: AsyncSession, session: LearningSession, event_type: str, payload: Dict[str, Any], when: datetime) -> None:
    from app.events import store  # late import: the store uses this module to attach sessions

    await store.record(
        db, org_id=session.org_id, user_id=session.user_id, event_type=event_type, course_id=session.course_id,
        session_id=session.id, payload=payload, timestamp=when, attach_session=False,
    )


async def end(
    db: AsyncSession, session: LearningSession, *, reason: str, now: Optional[datetime] = None, at: Optional[datetime] = None
) -> LearningSession:
    """Close a session. `at` is when it really ended (the last activity, for an idle session)."""
    if session.ended_at is not None:
        return session
    now = now or datetime.utcnow()
    ended = max(session.started_at, min(at or now, now))
    session.ended_at, session.end_reason = ended, reason
    await db.flush()
    await _emit(db, session, "session_completed", {"reason": reason, "duration_seconds": int((ended - session.started_at).total_seconds())}, ended)
    return session


async def close_if_idle(db: AsyncSession, session: LearningSession, now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    if not is_idle(session, now):
        return False
    await end(db, session, reason="idle", now=now, at=session.last_activity_at)
    return True


async def start(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, course_id: Optional[UUID], context: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None, first_activity: Optional[datetime] = None,
) -> Tuple[LearningSession, bool]:
    """
    Start a session, or resume the learner's open one for this course. Returns (session, created).

    `first_activity` is when the event that caused an implicit start happened; the session then begins one
    microsecond before it, so `session_started` always sorts ahead of the first event it contains.
    """
    now = now or datetime.utcnow()
    existing = await open_session(db, org_id=org_id, user_id=user_id, course_id=course_id)
    if existing is not None:
        if not await close_if_idle(db, existing, now):
            await touch(db, existing.id, now)
            await db.refresh(existing)
            return existing, False

    began = now if first_activity is None else min(first_activity, now) - timedelta(microseconds=1)
    session = LearningSession(
        org_id=org_id, user_id=user_id, course_id=course_id, started_at=began, last_activity_at=began, context=context or {},
    )
    try:
        async with db.begin_nested():
            db.add(session)
            await db.flush()
    except IntegrityError:  # a concurrent request opened one first
        if session in db:
            db.expunge(session)
        winner = await open_session(db, org_id=org_id, user_id=user_id, course_id=course_id)
        if winner is None:
            raise
        return winner, False

    await _emit(db, session, "session_started", {"source": (context or {}).get("source", "explicit")}, began)
    return session, True


async def for_activity(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, course_id: UUID, now: Optional[datetime] = None,
    first_activity: Optional[datetime] = None,
) -> LearningSession:
    """The session an event in this course belongs to; one is started (marked implicit) if none is open."""
    session, _ = await start(
        db, org_id=org_id, user_id=user_id, course_id=course_id, context={"source": "implicit"}, now=now, first_activity=first_activity,
    )
    return session


async def touch(db: AsyncSession, session_id: UUID, at: datetime) -> None:
    """Record activity. Never moves last_activity backwards."""
    await db.execute(
        update(LearningSession).where(LearningSession.id == session_id, LearningSession.ended_at.is_(None))
        .values(last_activity_at=func.greatest(LearningSession.last_activity_at, at))
        .execution_options(synchronize_session=False)  # a SQL expression: do not let it expire loaded rows
    )


async def require_open(
    db: AsyncSession, session_id: UUID, *, org_id: UUID, user_id: UUID, now: Optional[datetime] = None,
    happened_at: Optional[datetime] = None,
) -> LearningSession:
    """
    A session the caller owns that an event may join. A foreign or unknown id is refused, not repaired.

    An ended session is still joinable by an event that HAPPENED before it ended (`happened_at`): browsers report
    in batches, and on page close the last batch and the "end" request race. Anything later is refused
    (`session_ended`), so the browser starts a new session and sends the event again.
    """
    session = (await db.execute(
        select(LearningSession).where(LearningSession.id == session_id, LearningSession.org_id == org_id, LearningSession.user_id == user_id)
    )).scalar_one_or_none()
    if session is None:
        raise SessionError("Session not found.", "session_not_found", 404)
    if session.ended_at is None:
        await close_if_idle(db, session, now)
    if session.ended_at is not None and (happened_at is None or happened_at > session.ended_at):
        raise SessionError("That session has ended. Start a new one.", "session_ended", 409)
    return session
