"""
The event store: the one place an event is validated and appended.

    record()            append one event (vocabulary, references and payload validated;
                        idempotent per tenant when an idempotency key is given)
    dispatch_pending()  publish committed events to the stream, retrying failures

Rules that hold here, and are tested:

  * Events are only ever inserted. The database rejects UPDATE and DELETE.
  * The tenant and the learner always come from the authenticated caller, never from the
    request body.
  * Anything belonging to a course is attached to a learning session, so a session is a
    complete account of what happened in it.
  * An event and its stream-delivery obligation (the outbox row) are written in the same
    transaction. If the stream is down, delivery is retried; nothing is lost or silently
    dropped.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events import sessions
from app.events.vocabulary import (
    VocabularyError, check_references, normalise, published_to_stream, spec_for, validate_payload,
)
from app.models import EventOutbox, LearningEvent

logger = logging.getLogger("api.events")

RETRY_BACKOFF_CAP_SECONDS = 300
MAX_ERROR_CHARS = 500


@dataclass
class Recorded:
    event: LearningEvent
    created: bool  # False when an event with the same idempotency key already existed


async def record(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    event_type: str,
    course_id: Optional[UUID] = None,
    module_id: Optional[UUID] = None,
    content_id: Optional[UUID] = None,
    assessment_id: Optional[UUID] = None,
    question_id: Optional[UUID] = None,
    competency_id: Optional[UUID] = None,
    session_id: Optional[UUID] = None,
    payload: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None,
    idempotency_key: Optional[str] = None,
    attach_session: bool = True,
) -> Recorded:
    """
    Append one event.

    When the event belongs to a course and no session is named, it joins the learner's
    open session for that course, starting one (marked implicit) if there is none. Pass
    `attach_session=False` for the session lifecycle events themselves.
    """
    event_type = normalise(event_type)
    spec = spec_for(event_type)
    refs = {"content_id": content_id, "assessment_id": assessment_id, "question_id": question_id, "competency_id": competency_id}
    check_references(event_type, refs)
    stored_payload = validate_payload(event_type, payload)

    now = datetime.utcnow()
    when = timestamp or now

    if session_id is None and attach_session and spec.needs_course and course_id is not None:
        session = await sessions.for_activity(db, org_id=org_id, user_id=user_id, course_id=course_id, now=now, first_activity=when)
        session_id = session.id

    values = dict(
        id=uuid.uuid4(), org_id=org_id, user_id=user_id, session_id=session_id, course_id=course_id,
        module_id=module_id, content_id=content_id, assessment_id=assessment_id, question_id=question_id,
        competency_id=competency_id, event_type=event_type, payload=stored_payload, timestamp=when,
        received_at=now, idempotency_key=idempotency_key, processed=False,
    )

    if idempotency_key:
        statement = (
            pg_insert(LearningEvent).values(**values)
            .on_conflict_do_nothing(
                index_elements=[LearningEvent.org_id, LearningEvent.idempotency_key],
                index_where=text("idempotency_key IS NOT NULL"),
            )
            .returning(LearningEvent.id)
        )
        inserted = (await db.execute(statement)).first()
        if inserted is None:
            existing = (await db.execute(
                select(LearningEvent).where(LearningEvent.org_id == org_id, LearningEvent.idempotency_key == idempotency_key)
            )).scalar_one()
            return Recorded(existing, False)
        event = await db.get(LearningEvent, values["id"])
    else:
        event = LearningEvent(**values)
        db.add(event)
        await db.flush()

    if published_to_stream(event_type):
        db.add(EventOutbox(event_id=event.id, org_id=org_id, created_at=now, next_attempt_at=now))
    if session_id is not None:
        await sessions.touch(db, session_id, when if when <= now else now)
    await db.flush()
    return Recorded(event, True)


def stream_message(event: LearningEvent) -> Dict[str, Any]:
    """The stream representation of an event (a superset of what consumers already read)."""
    return {
        "event_id": str(event.id),
        "org_id": str(event.org_id),
        "user_id": str(event.user_id),
        "event_type": event.event_type,
        "session_id": str(event.session_id) if event.session_id else "",
        "course_id": str(event.course_id) if event.course_id else "",
        "module_id": str(event.module_id) if event.module_id else "",
        "content_id": str(event.content_id) if event.content_id else "",
        "assessment_id": str(event.assessment_id) if event.assessment_id else "",
        "question_id": str(event.question_id) if event.question_id else "",
        "competency_id": str(event.competency_id) if event.competency_id else "",
        "timestamp": event.timestamp.isoformat(),
        "payload": event.payload,
    }


@dataclass
class DispatchResult:
    published: int = 0
    failed: int = 0


async def dispatch_pending(
    session_factory: async_sessionmaker, publisher: Any, *, batch: int = 100, now: Optional[datetime] = None
) -> DispatchResult:
    """
    Publish events that were committed but not yet delivered. Safe to run from several
    processes (rows are claimed with SKIP LOCKED). A failure schedules a retry with
    exponential backoff and keeps the error for inspection.
    """
    result = DispatchResult()
    now = now or datetime.utcnow()
    async with session_factory() as db:
        rows = (await db.execute(
            select(EventOutbox, LearningEvent)
            .join(LearningEvent, LearningEvent.id == EventOutbox.event_id)
            .where(EventOutbox.published_at.is_(None), EventOutbox.next_attempt_at <= now)
            .order_by(EventOutbox.created_at)
            .limit(batch)
            .with_for_update(of=EventOutbox, skip_locked=True)
        )).all()
        for outbox, event in rows:
            try:
                message_id = await publisher.publish_event(stream_message(event))
            except Exception as exc:  # the stream is unavailable or rejected the message
                outbox.attempts += 1
                outbox.last_error = str(exc)[:MAX_ERROR_CHARS]
                outbox.next_attempt_at = now + timedelta(seconds=min(2 ** outbox.attempts, RETRY_BACKOFF_CAP_SECONDS))
                result.failed += 1
                logger.warning(json.dumps({"event": "event_publish_failed", "event_id": str(event.id), "attempts": outbox.attempts, "error": outbox.last_error}))
            else:
                outbox.published_at = datetime.utcnow()
                outbox.stream_message_id = str(message_id)[:64]
                outbox.last_error = None
                result.published += 1
        await db.commit()
    return result
