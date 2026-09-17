"""
Learning Events Ingestion and Query API Endpoints.
Persists immutable telemetry events in PostgreSQL and streams to Redis via XADD.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.core.database import get_db
from app.core.events import event_publisher
from app.models import LearningEvent, User, Course, Module
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext
from shared.events.types import EventType

router = APIRouter(prefix="/events", tags=["Learning Events Tracking"])


class EventPayload(BaseModel):
    event_id: Optional[UUID] = None
    event_type: str = Field(..., description="Canonical event type")
    course_id: Optional[UUID] = None
    module_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class BatchEventsPayload(BaseModel):
    events: List[EventPayload] = Field(..., min_length=1, max_length=100)


@router.post("", status_code=status.HTTP_201_CREATED)
async def ingest_event(
    payload: EventPayload,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingests an atomic learning telemetry event.
    Persists to relational database with idempotency and broadcasts to Redis Stream.
    """
    event_id = payload.event_id or uuid.uuid4()
    event_time = payload.timestamp or datetime.utcnow()

    # Check for duplicate event_id if supplied
    if payload.event_id:
        existing_check = await db.execute(
            select(LearningEvent).where(LearningEvent.id == payload.event_id)
        )
        if existing_check.scalar_one_or_none():
            return {
                "status": "duplicate_ignored",
                "event_id": str(payload.event_id),
                "redis_message_id": "duplicate_skipped",
                "event_type": payload.event_type,
                "timestamp": event_time.isoformat(),
            }

    # 1. Persist to PostgreSQL
    event_record = LearningEvent(
        id=event_id,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        session_id=payload.session_id,
        course_id=payload.course_id,
        module_id=payload.module_id,
        event_type=payload.event_type,
        payload=payload.payload,
        timestamp=event_time,
        processed=False,
    )
    db.add(event_record)
    await db.flush()

    # 2. Publish to Redis Stream
    stream_data = {
        "event_id": str(event_id),
        "org_id": str(tenant_ctx.org_id),
        "user_id": str(current_user.id),
        "event_type": payload.event_type,
        "session_id": str(payload.session_id) if payload.session_id else "",
        "course_id": str(payload.course_id) if payload.course_id else "",
        "module_id": str(payload.module_id) if payload.module_id else "",
        "timestamp": event_time.isoformat(),
        "payload": payload.payload,
    }
    
    redis_msg_id = "stream_unavailable"
    try:
        redis_msg_id = await event_publisher.publish_event(stream_data)
    except Exception:
        pass

    return {
        "status": "ingested",
        "event_id": str(event_id),
        "redis_message_id": redis_msg_id,
        "event_type": payload.event_type,
        "timestamp": event_time.isoformat(),
    }


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def ingest_batch_events(
    batch: BatchEventsPayload,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingests a batch of learning telemetry events atomically.
    """
    results = []
    for item in batch.events:
        event_id = uuid.uuid4()
        event_time = item.timestamp or datetime.utcnow()

        event_record = LearningEvent(
            id=event_id,
            org_id=tenant_ctx.org_id,
            user_id=current_user.id,
            session_id=item.session_id,
            course_id=item.course_id,
            module_id=item.module_id,
            event_type=item.event_type,
            payload=item.payload,
            timestamp=event_time,
            processed=False,
        )
        db.add(event_record)

        stream_data = {
            "event_id": str(event_id),
            "org_id": str(tenant_ctx.org_id),
            "user_id": str(current_user.id),
            "event_type": item.event_type,
            "timestamp": event_time.isoformat(),
            "payload": item.payload,
        }
        try:
            await event_publisher.publish_event(stream_data)
        except Exception:
            pass

        results.append({"event_id": str(event_id), "event_type": item.event_type})

    await db.flush()
    return {"status": "batch_ingested", "count": len(results), "events": results}


@router.get("")
async def query_events(
    user_id: Optional[UUID] = None,
    course_id: Optional[UUID] = None,
    event_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Query telemetry events for audit and analytics.
    Learners can only view their own events.
    """
    query = select(LearningEvent).where(LearningEvent.org_id == tenant_ctx.org_id)

    if current_user.role == "learner":
        query = query.where(LearningEvent.user_id == current_user.id)
    elif user_id:
        query = query.where(LearningEvent.user_id == user_id)

    if course_id:
        query = query.where(LearningEvent.course_id == course_id)
    if event_type:
        query = query.where(LearningEvent.event_type == event_type)

    query = query.order_by(desc(LearningEvent.timestamp)).limit(limit).offset(offset)
    res = await db.execute(query)
    events = res.scalars().all()

    return [
        {
            "id": str(e.id),
            "user_id": str(e.user_id),
            "session_id": str(e.session_id) if e.session_id else None,
            "course_id": str(e.course_id) if e.course_id else None,
            "module_id": str(e.module_id) if e.module_id else None,
            "event_type": e.event_type,
            "payload": e.payload,
            "timestamp": e.timestamp.isoformat(),
            "processed": e.processed,
        }
        for e in events
    ]


@router.get("/stats")
async def get_events_stats(
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Summary event telemetry volume broken down by canonical event type."""
    query = (
        select(LearningEvent.event_type, func.count(LearningEvent.id))
        .where(LearningEvent.org_id == tenant_ctx.org_id)
        .group_by(LearningEvent.event_type)
    )
    res = await db.execute(query)
    breakdown = {event_type: count for event_type, count in res.all()}
    total = sum(breakdown.values())
    return {"total_events": total, "breakdown": breakdown}
