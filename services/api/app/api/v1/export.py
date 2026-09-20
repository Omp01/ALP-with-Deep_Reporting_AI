"""
BI Export and Data Warehouse Streaming Endpoints.
Provides tenant-isolated exports for learning events, competencies, and risk metrics in CSV and JSON formats.
"""

import io
import csv
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.models import LearningEvent, LearnerCompetency, LearnerRisk, User
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext

router = APIRouter(prefix="/export", tags=["BI & Analytics Export"])


@router.get("/events")
async def export_learning_events(
    format: str = Query("json", regex="^(json|csv)$"),
    limit: int = Query(500, ge=1, le=5000),
    current_user: User = Depends(require_roles(["org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Exports raw learning telemetry events for BI warehousing."""
    q = (
        select(LearningEvent)
        .where(LearningEvent.org_id == tenant_ctx.org_id)
        .order_by(desc(LearningEvent.timestamp))
        .limit(limit)
    )
    res = await db.execute(q)
    events = res.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "user_id", "course_id", "module_id", "event_type", "timestamp"])
        for e in events:
            writer.writerow([
                str(e.id),
                str(e.user_id),
                str(e.course_id) if e.course_id else "",
                str(e.module_id) if e.module_id else "",
                e.event_type,
                e.timestamp.isoformat(),
            ])
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=events.csv"})

    return [
        {
            "id": str(e.id),
            "user_id": str(e.user_id),
            "course_id": str(e.course_id) if e.course_id else None,
            "module_id": str(e.module_id) if e.module_id else None,
            "event_type": e.event_type,
            "payload": e.payload,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]


@router.get("/competencies")
async def export_competency_mastery(
    format: str = Query("json", regex="^(json|csv)$"),
    limit: int = Query(500, ge=1, le=5000),
    current_user: User = Depends(require_roles(["org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Exports live competency mastery states for analytics."""
    q = (
        select(LearnerCompetency)
        .where(LearnerCompetency.org_id == tenant_ctx.org_id, LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0)
        .order_by(desc(LearnerCompetency.updated_at))
        .limit(limit)
    )
    res = await db.execute(q)
    competencies = res.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "user_id", "competency_id", "mastery_score", "confidence_score", "status", "updated_at"])
        for c in competencies:
            writer.writerow([
                str(c.id),
                str(c.user_id),
                str(c.competency_id),
                c.mastery_score,
                c.confidence_score,
                c.status,
                c.updated_at.isoformat(),
            ])
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=competencies.csv"})

    return [
        {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "competency_id": str(c.competency_id),
            "mastery_score": c.mastery_score,
            "confidence_score": c.confidence_score,
            "data_points_count": c.data_points_count,
            "status": c.status,
            "updated_at": c.updated_at.isoformat(),
        }
        for c in competencies
    ]


@router.get("/risks")
async def export_risk_records(
    format: str = Query("json", regex="^(json|csv)$"),
    limit: int = Query(500, ge=1, le=5000),
    current_user: User = Depends(require_roles(["org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Exports at-risk learner evaluations."""
    q = (
        select(LearnerRisk)
        .where(LearnerRisk.org_id == tenant_ctx.org_id)
        .order_by(desc(LearnerRisk.detected_at))
        .limit(limit)
    )
    res = await db.execute(q)
    risks = res.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "user_id", "course_id", "risk_level", "risk_score", "is_resolved", "detected_at"])
        for r in risks:
            writer.writerow([
                str(r.id),
                str(r.user_id),
                str(r.course_id),
                r.risk_level,
                r.risk_score,
                r.is_resolved,
                r.detected_at.isoformat(),
            ])
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=risks.csv"})

    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id),
            "course_id": str(r.course_id),
            "risk_level": r.risk_level,
            "risk_score": r.risk_score,
            "is_resolved": r.is_resolved,
            "detected_at": r.detected_at.isoformat(),
        }
        for r in risks
    ]
