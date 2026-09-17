"""
Learning Sessions Management API Endpoints.
Handles lifecycle of adaptive learning sessions, tracking start, heartbeats, and completion.
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.core.database import get_db
from app.models import AdaptiveSession, SessionSequenceStep, User, Course, Module
from app.api.deps import get_current_user, get_current_tenant, TenantContext

router = APIRouter(prefix="/learning/sessions", tags=["Learning Sessions"])


class StartSessionPayload(BaseModel):
    course_id: UUID
    module_id: Optional[UUID] = None
    device_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    initial_difficulty: Optional[float] = 0.5


class EndSessionPayload(BaseModel):
    summary_notes: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = Field(default_factory=dict)


@router.post("/start", status_code=status.HTTP_201_CREATED)
async def start_learning_session(
    payload: StartSessionPayload,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Starts a new learning session or returns an active existing session.
    """
    # 1. Check if course exists
    course_query = select(Course).where(
        and_(Course.id == payload.course_id, Course.org_id == tenant_ctx.org_id)
    )
    course_res = await db.execute(course_query)
    course = course_res.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course {payload.course_id} not found in this organization"
        )

    # 2. Check for an existing active session for this user and course
    existing_query = select(AdaptiveSession).where(
        and_(
            AdaptiveSession.user_id == current_user.id,
            AdaptiveSession.course_id == payload.course_id,
            AdaptiveSession.state == "active"
        )
    ).order_by(desc(AdaptiveSession.started_at))
    existing_res = await db.execute(existing_query)
    active_session = existing_res.scalars().first()

    if active_session:
        return {
            "session_id": str(active_session.id),
            "status": "resumed_active",
            "course_id": str(active_session.course_id),
            "started_at": active_session.started_at.isoformat(),
            "state": active_session.state,
            "current_difficulty": active_session.current_difficulty,
        }

    # 3. Create new adaptive session
    session_id = uuid.uuid4()
    new_session = AdaptiveSession(
        id=session_id,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        course_id=payload.course_id,
        current_module_id=payload.module_id,
        state="active",
        current_difficulty=payload.initial_difficulty or 0.5,
        session_metadata=payload.device_info or {},
        started_at=datetime.utcnow(),
    )
    db.add(new_session)
    await db.flush()

    return {
        "session_id": str(session_id),
        "status": "created",
        "course_id": str(payload.course_id),
        "started_at": new_session.started_at.isoformat(),
        "state": "active",
        "current_difficulty": new_session.current_difficulty,
    }


@router.get("/active")
async def get_active_session(
    course_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves the currently active learning session for the authenticated user.
    """
    query = select(AdaptiveSession).where(
        and_(
            AdaptiveSession.user_id == current_user.id,
            AdaptiveSession.org_id == tenant_ctx.org_id,
            AdaptiveSession.state == "active",
        )
    )
    if course_id:
        query = query.where(AdaptiveSession.course_id == course_id)

    query = query.order_by(desc(AdaptiveSession.started_at))
    res = await db.execute(query)
    session = res.scalars().first()

    if not session:
        return {"active": False, "session": None}

    return {
        "active": True,
        "session": {
            "session_id": str(session.id),
            "course_id": str(session.course_id),
            "current_module_id": str(session.current_module_id) if session.current_module_id else None,
            "state": session.state,
            "current_difficulty": session.current_difficulty,
            "started_at": session.started_at.isoformat(),
        }
    }


@router.post("/{session_id}/end")
async def end_learning_session(
    session_id: UUID,
    payload: Optional[EndSessionPayload] = None,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Terminates an active learning session and records end time & metadata.
    """
    query = select(AdaptiveSession).where(
        and_(
            AdaptiveSession.id == session_id,
            AdaptiveSession.org_id == tenant_ctx.org_id,
        )
    )
    res = await db.execute(query)
    session = res.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    if current_user.role == "learner" and session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot terminate another learner's session"
        )

    session.state = "completed"
    session.ended_at = datetime.utcnow()
    if payload and payload.metrics:
        existing_meta = dict(session.session_metadata or {})
        existing_meta.update(payload.metrics)
        session.session_metadata = existing_meta

    await db.flush()

    duration_seconds = (session.ended_at - session.started_at).total_seconds()

    return {
        "session_id": str(session.id),
        "status": "completed",
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
    }


@router.get("/{session_id}")
async def get_session_details(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches full details of a specific learning session.
    """
    query = select(AdaptiveSession).where(
        and_(
            AdaptiveSession.id == session_id,
            AdaptiveSession.org_id == tenant_ctx.org_id,
        )
    )
    res = await db.execute(query)
    session = res.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    if current_user.role == "learner" and session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another learner's session"
        )

    return {
        "session_id": str(session.id),
        "user_id": str(session.user_id),
        "course_id": str(session.course_id),
        "current_module_id": str(session.current_module_id) if session.current_module_id else None,
        "state": session.state,
        "current_difficulty": session.current_difficulty,
        "recommended_next_action": session.recommended_next_action,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "metadata": session.session_metadata,
    }
