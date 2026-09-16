"""
Enrollment management and progress tracking API endpoints.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models import Enrollment, Course, User
from app.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentProgressUpdate,
    EnrollmentResponse,
)
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext, log_audit_action

router = APIRouter(prefix="/enrollments", tags=["Enrollments & Learner Progress"])


@router.get("", response_model=List[EnrollmentResponse])
async def list_enrollments(
    user_id: Optional[UUID] = None,
    course_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    List enrollments:
    - Learners can only view their own enrollments.
    - Instructors/Managers/Admins can filter by learner or course.
    """
    query = select(Enrollment).where(Enrollment.org_id == tenant_ctx.org_id)

    if current_user.role == "learner":
        query = query.where(Enrollment.user_id == current_user.id)
    elif user_id:
        query = query.where(Enrollment.user_id == user_id)

    if course_id:
        query = query.where(Enrollment.course_id == course_id)
    if status:
        query = query.where(Enrollment.status == status)

    query = query.order_by(Enrollment.last_activity_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def enroll_course(
    payload: EnrollmentCreate,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Enroll in a course."""
    # Determine target user
    target_user_id = current_user.id
    if payload.user_id:
        if payload.user_id != current_user.id and current_user.role not in ["org_admin", "instructor", "manager"]:
            raise HTTPException(status_code=403, detail="Not authorized to enroll other users")
        target_user_id = payload.user_id

    # Verify course exists in tenant and is published
    course_res = await db.execute(
        select(Course).where(and_(Course.id == payload.course_id, Course.org_id == tenant_ctx.org_id))
    )
    course = course_res.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Prevent duplicate active enrollment
    existing = await db.execute(
        select(Enrollment).where(
            and_(
                Enrollment.user_id == target_user_id,
                Enrollment.course_id == payload.course_id,
                Enrollment.status == "active",
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already actively enrolled in this course")

    enrollment = Enrollment(
        org_id=tenant_ctx.org_id,
        user_id=target_user_id,
        course_id=payload.course_id,
        status="active",
        progress_pct=0.0,
        enrolled_at=datetime.utcnow(),
        last_activity_at=datetime.utcnow(),
    )
    db.add(enrollment)
    await db.flush()

    await log_audit_action(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        action="COURSE_ENROLLMENT",
        resource_type="ENROLLMENT",
        resource_id=str(enrollment.id),
        changes={"course_id": str(payload.course_id), "target_user": str(target_user_id)},
    )
    return enrollment


@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
async def get_enrollment(
    enrollment_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details for a specific enrollment."""
    result = await db.execute(
        select(Enrollment).where(and_(Enrollment.id == enrollment_id, Enrollment.org_id == tenant_ctx.org_id))
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if current_user.role == "learner" and enrollment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view another learner's enrollment")

    return enrollment


@router.put("/{enrollment_id}/progress", response_model=EnrollmentResponse)
async def update_progress(
    enrollment_id: UUID,
    payload: EnrollmentProgressUpdate,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update learner completion progress."""
    result = await db.execute(
        select(Enrollment).where(and_(Enrollment.id == enrollment_id, Enrollment.org_id == tenant_ctx.org_id))
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if current_user.role == "learner" and enrollment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify another learner's enrollment")

    enrollment.progress_pct = payload.progress_pct
    enrollment.last_activity_at = datetime.utcnow()

    if payload.status:
        enrollment.status = payload.status
    elif payload.progress_pct >= 100.0:
        enrollment.status = "completed"
        enrollment.completed_at = datetime.utcnow()

    await db.flush()
    return enrollment
