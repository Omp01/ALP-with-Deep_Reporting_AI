"""
Risk Management and Early Warning API Endpoints.
Guaranteed tenant-isolated and RBAC-protected.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import LearnerRisk, User, Course
from app.services.risk_service import evaluate_learner_risk, scan_organization_risks
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext

router = APIRouter(prefix="/risks", tags=["Risk Early Warning"])


class RiskRecordResponse(BaseModel):
    id: UUID
    org_id: UUID
    user_id: UUID
    learner_name: Optional[str] = None
    learner_email: Optional[str] = None
    course_id: UUID
    course_title: Optional[str] = None
    risk_level: str
    risk_score: float
    risk_factors: List[str]
    recommended_actions: List[str]
    is_resolved: bool
    detected_at: str
    updated_at: str


@router.get("", response_model=List[RiskRecordResponse])
async def list_at_risk_learners(
    risk_level: Optional[str] = None,
    course_id: Optional[UUID] = None,
    resolved: Optional[bool] = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    List at-risk learners across the organization.
    Filtered by risk_level (critical, high, medium, low), course_id, and resolution status.
    """
    query = (
        select(LearnerRisk)
        .where(LearnerRisk.org_id == tenant_ctx.org_id)
        .options(selectinload(LearnerRisk.user), selectinload(LearnerRisk.course))
        .order_by(desc(LearnerRisk.risk_score), desc(LearnerRisk.updated_at))
    )

    if risk_level:
        query = query.where(LearnerRisk.risk_level == risk_level)
    if course_id:
        query = query.where(LearnerRisk.course_id == course_id)
    if resolved is not None:
        query = query.where(LearnerRisk.is_resolved == resolved)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    records = result.scalars().all()

    return [
        RiskRecordResponse(
            id=r.id,
            org_id=r.org_id,
            user_id=r.user_id,
            learner_name=r.user.full_name if r.user else "Unknown Learner",
            learner_email=r.user.email if r.user else "unknown@domain.com",
            course_id=r.course_id,
            course_title=r.course.title if r.course else "Unknown Course",
            risk_level=r.risk_level,
            risk_score=r.risk_score,
            risk_factors=r.risk_factors,
            recommended_actions=r.recommended_actions,
            is_resolved=r.is_resolved,
            detected_at=r.detected_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
        )
        for r in records
    ]


@router.get("/{learner_id}", response_model=List[RiskRecordResponse])
async def get_learner_risk_history(
    learner_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Detailed risk analysis for a specific learner.
    Learners can view their own profile; managers and admins can view subordinate learners.
    """
    if current_user.role == "learner" and learner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only view their own risk profile",
        )

    query = (
        select(LearnerRisk)
        .where(
            and_(
                LearnerRisk.org_id == tenant_ctx.org_id,
                LearnerRisk.user_id == learner_id,
            )
        )
        .options(selectinload(LearnerRisk.user), selectinload(LearnerRisk.course))
        .order_by(desc(LearnerRisk.updated_at))
    )
    result = await db.execute(query)
    records = result.scalars().all()

    return [
        RiskRecordResponse(
            id=r.id,
            org_id=r.org_id,
            user_id=r.user_id,
            learner_name=r.user.full_name if r.user else "Unknown Learner",
            learner_email=r.user.email if r.user else "unknown@domain.com",
            course_id=r.course_id,
            course_title=r.course.title if r.course else "Unknown Course",
            risk_level=r.risk_level,
            risk_score=r.risk_score,
            risk_factors=r.risk_factors,
            recommended_actions=r.recommended_actions,
            is_resolved=r.is_resolved,
            detected_at=r.detected_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
        )
        for r in records
    ]


@router.post("/scan")
async def trigger_organization_risk_scan(
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    On-demand trigger to run the risk engine across all active enrollments.
    """
    scan_summary = await scan_organization_risks(db=db, org_id=tenant_ctx.org_id)
    return {
        "status": "completed",
        "org_id": str(tenant_ctx.org_id),
        "summary": scan_summary,
    }


@router.put("/{risk_id}/resolve")
async def resolve_at_risk_alert(
    risk_id: UUID,
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Marks an at-risk alert as resolved after teacher/manager intervention.
    """
    query = select(LearnerRisk).where(
        and_(
            LearnerRisk.id == risk_id,
            LearnerRisk.org_id == tenant_ctx.org_id,
        )
    )
    res = await db.execute(query)
    risk_rec = res.scalars().first()

    if not risk_rec:
        raise HTTPException(status_code=404, detail="Risk record not found")

    risk_rec.is_resolved = True
    await db.commit()

    return {"status": "resolved", "risk_id": str(risk_id), "is_resolved": True}
