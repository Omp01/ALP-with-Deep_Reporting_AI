"""
Reading the event store.

Every query is tenant-scoped, and scoped again by what the viewer may see:

    learner                     their own events and sessions
    manager                     their own, plus those of the members of teams they manage
    ld_admin / org_admin        everyone in the organisation
    super_admin                 the tenant they act in (X-Tenant-ID)

Pagination is keyset-based on (timestamp, id), so a page never repeats or skips an event
when new events arrive while someone is paging.
"""

import base64
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, has_any_role
from app.api.deps import effective_roles
from app.events.sessions import idle_limit
from app.models import LearningEvent, LearningSession, Team, User, UserTeam


class QueryError(ValueError):
    pass


# ------------------------------------------------------------------------------ visibility
async def visible_user_ids(db: AsyncSession, viewer: User, org_id: UUID) -> Optional[Set[UUID]]:
    """None = everyone in the organisation; otherwise the set of learners the viewer may see."""
    held = effective_roles(viewer)
    if has_any_role(held, [Role.LD_ADMIN, Role.ORG_ADMIN]):
        return None
    visible: Set[UUID] = {viewer.id}
    if Role.MANAGER in held:
        members = (await db.execute(
            select(UserTeam.user_id)
            .join(Team, Team.id == UserTeam.team_id)
            .where(Team.org_id == org_id, Team.manager_id == viewer.id, UserTeam.org_id == org_id)
        )).scalars().all()
        visible.update(members)
    return visible


def _restrict_to(column, visible: Optional[Set[UUID]], requested: Optional[UUID]):
    """A WHERE clause for the user column given who may be seen and who was asked for."""
    if requested is not None:
        if visible is not None and requested not in visible:
            return column.in_([])  # not visible: indistinguishable from "no events"
        return column == requested
    if visible is None:
        return None
    return column.in_(list(visible))


# -------------------------------------------------------------------------------- filters
@dataclass
class EventFilter:
    user_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    course_id: Optional[UUID] = None
    module_id: Optional[UUID] = None
    content_id: Optional[UUID] = None
    assessment_id: Optional[UUID] = None
    question_id: Optional[UUID] = None
    competency_id: Optional[UUID] = None
    event_types: Sequence[str] = field(default_factory=tuple)
    since: Optional[datetime] = None
    until: Optional[datetime] = None


def _conditions(org_id: UUID, visible: Optional[Set[UUID]], flt: EventFilter) -> List[Any]:
    conditions: List[Any] = [LearningEvent.org_id == org_id]
    who = _restrict_to(LearningEvent.user_id, visible, flt.user_id)
    if who is not None:
        conditions.append(who)
    for column, value in (
        (LearningEvent.session_id, flt.session_id), (LearningEvent.course_id, flt.course_id),
        (LearningEvent.module_id, flt.module_id), (LearningEvent.content_id, flt.content_id),
        (LearningEvent.assessment_id, flt.assessment_id), (LearningEvent.question_id, flt.question_id),
        (LearningEvent.competency_id, flt.competency_id),
    ):
        if value is not None:
            conditions.append(column == value)
    if flt.event_types:
        conditions.append(LearningEvent.event_type.in_(list(flt.event_types)))
    if flt.since is not None:
        conditions.append(LearningEvent.timestamp >= flt.since)
    if flt.until is not None:
        conditions.append(LearningEvent.timestamp < flt.until)
    return conditions


# ------------------------------------------------------------------------------- cursors
def encode_cursor(timestamp: datetime, event_id: UUID) -> str:
    raw = json.dumps({"t": timestamp.isoformat(), "i": str(event_id)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> Tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
        return datetime.fromisoformat(data["t"]), UUID(data["i"])
    except Exception as exc:
        raise QueryError("The cursor is not valid.") from exc


# ---------------------------------------------------------------------------------- events
def event_out(event: LearningEvent) -> Dict[str, Any]:
    def s(value: Optional[UUID]) -> Optional[str]:
        return str(value) if value else None

    return {
        "id": str(event.id), "event_type": event.event_type, "user_id": str(event.user_id),
        "session_id": s(event.session_id), "course_id": s(event.course_id), "module_id": s(event.module_id),
        "content_id": s(event.content_id), "assessment_id": s(event.assessment_id),
        "question_id": s(event.question_id), "competency_id": s(event.competency_id),
        "payload": event.payload, "timestamp": event.timestamp.isoformat(),
        "received_at": event.received_at.isoformat() if event.received_at else None,
    }


async def list_events(
    db: AsyncSession, org_id: UUID, visible: Optional[Set[UUID]], flt: EventFilter, *,
    limit: int = 50, cursor: Optional[str] = None, ascending: bool = False,
) -> Tuple[List[LearningEvent], Optional[str]]:
    conditions = _conditions(org_id, visible, flt)
    key = tuple_(LearningEvent.timestamp, LearningEvent.id)
    if cursor:
        at, event_id = decode_cursor(cursor)
        conditions.append(key > tuple_(at, event_id) if ascending else key < tuple_(at, event_id))
    order = (LearningEvent.timestamp.asc(), LearningEvent.id.asc()) if ascending else (LearningEvent.timestamp.desc(), LearningEvent.id.desc())
    rows = (await db.execute(select(LearningEvent).where(and_(*conditions)).order_by(*order).limit(limit + 1))).scalars().all()
    more = len(rows) > limit
    rows = list(rows[:limit])
    return rows, (encode_cursor(rows[-1].timestamp, rows[-1].id) if more and rows else None)


async def get_event(db: AsyncSession, org_id: UUID, visible: Optional[Set[UUID]], event_id: UUID) -> Optional[LearningEvent]:
    conditions = [LearningEvent.org_id == org_id, LearningEvent.id == event_id]
    who = _restrict_to(LearningEvent.user_id, visible, None)
    if who is not None:
        conditions.append(who)
    return (await db.execute(select(LearningEvent).where(and_(*conditions)))).scalar_one_or_none()


async def stats(db: AsyncSession, org_id: UUID, visible: Optional[Set[UUID]], flt: EventFilter) -> Dict[str, Any]:
    conditions = _conditions(org_id, visible, flt)
    by_type = dict((await db.execute(
        select(LearningEvent.event_type, func.count()).where(and_(*conditions)).group_by(LearningEvent.event_type)
    )).all())
    day = func.date(LearningEvent.timestamp)
    by_day = [
        {"date": d.isoformat() if isinstance(d, date) else str(d), "count": n}
        for d, n in (await db.execute(
            select(day, func.count()).where(and_(*conditions)).group_by(day).order_by(day.desc()).limit(90)
        )).all()
    ]
    learners = (await db.execute(select(func.count(distinct(LearningEvent.user_id))).where(and_(*conditions)))).scalar() or 0

    # Sessions are counted as records, under the same scope and filters, not inferred from events: a session in
    # which nothing was recorded yet is still a session, and this matches what the sessions list shows.
    session_conditions: List[Any] = [LearningSession.org_id == org_id]
    who = _restrict_to(LearningSession.user_id, visible, flt.user_id)
    if who is not None:
        session_conditions.append(who)
    if flt.course_id is not None:
        session_conditions.append(LearningSession.course_id == flt.course_id)
    if flt.since is not None:
        session_conditions.append(LearningSession.started_at >= flt.since)
    if flt.until is not None:
        session_conditions.append(LearningSession.started_at < flt.until)
    sessions = (await db.execute(select(func.count(LearningSession.id)).where(and_(*session_conditions)))).scalar() or 0
    return {
        "total_events": sum(by_type.values()), "breakdown": by_type, "by_day": list(reversed(by_day)),
        "learners": learners, "sessions": sessions,
    }


# -------------------------------------------------------------------------------- sessions
def _state(session: LearningSession, now: datetime) -> str:
    """ended | idle (open, but quiet long enough that the next activity starts a new session) | active."""
    if session.ended_at is not None:
        return "ended"
    return "idle" if now - session.last_activity_at > idle_limit() else "active"


def session_out(session: LearningSession, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.utcnow()
    end = session.ended_at or session.last_activity_at
    return {
        "session_id": str(session.id), "user_id": str(session.user_id),
        "course_id": str(session.course_id) if session.course_id else None,
        "started_at": session.started_at.isoformat(), "last_activity_at": session.last_activity_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "end_reason": session.end_reason, "state": _state(session, now),
        "duration_seconds": max(0, int((end - session.started_at).total_seconds())),
        "context": session.context,
    }


async def session_summary(db: AsyncSession, session: LearningSession) -> Dict[str, Any]:
    """What happened in a session, counted from its events."""
    base = and_(LearningEvent.org_id == session.org_id, LearningEvent.session_id == session.id)
    by_type = dict((await db.execute(select(LearningEvent.event_type, func.count()).where(base).group_by(LearningEvent.event_type))).all())
    items = (await db.execute(select(func.count(distinct(LearningEvent.content_id))).where(base, LearningEvent.content_id.is_not(None)))).scalar() or 0
    answered = (await db.execute(
        select(func.count(), func.count().filter(LearningEvent.payload["is_correct"].as_boolean().is_(True)))
        .where(base, LearningEvent.event_type == "question_answered")
    )).one()
    return {
        "events": sum(by_type.values()), "by_type": by_type, "content_items_touched": items,
        "questions_answered": answered[0], "questions_correct": answered[1],
    }


async def list_sessions(
    db: AsyncSession, org_id: UUID, visible: Optional[Set[UUID]], *, user_id: Optional[UUID] = None,
    course_id: Optional[UUID] = None, active: Optional[bool] = None, limit: int = 50, offset: int = 0,
) -> List[LearningSession]:
    conditions: List[Any] = [LearningSession.org_id == org_id]
    who = _restrict_to(LearningSession.user_id, visible, user_id)
    if who is not None:
        conditions.append(who)
    if course_id is not None:
        conditions.append(LearningSession.course_id == course_id)
    if active is True:
        conditions.append(LearningSession.ended_at.is_(None))
    elif active is False:
        conditions.append(LearningSession.ended_at.is_not(None))
    return list((await db.execute(
        select(LearningSession).where(and_(*conditions)).order_by(LearningSession.started_at.desc()).limit(limit).offset(offset)
    )).scalars().all())


async def get_session(db: AsyncSession, org_id: UUID, visible: Optional[Set[UUID]], session_id: UUID) -> Optional[LearningSession]:
    conditions = [LearningSession.org_id == org_id, LearningSession.id == session_id]
    who = _restrict_to(LearningSession.user_id, visible, None)
    if who is not None:
        conditions.append(who)
    return (await db.execute(select(LearningSession).where(and_(*conditions)))).scalar_one_or_none()
