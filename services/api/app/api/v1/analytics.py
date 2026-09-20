"""
Deterministic analytics (no model): counts and averages over stored data, scoped by who is asking.

    GET /analytics/learner/{id}        progress and evidence-based mastery for a learner        (self; manager: team; admin)
    GET /analytics/team/{team_id}      cohort figures for a team                                (manager of it; admin)
    GET /analytics/organization        headline figures for the organization                    (L&D, org admin)
    GET /analytics/events              event counts by type and day                             (scoped like the event store)
    GET /analytics/competencies        per-competency counts for BI tools                       (manager: team; admin)

Every figure is null when there is nothing behind it. The earlier versions proxied to a separate service; these read the same stores as
the rest of the platform.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, get_current_user, get_db, require_roles
from app.api.v1 import mastery as mastery_api
from app.competency import insight, service as competency_service
from app.events import queries as event_queries
from app.models import Course, Enrollment, LearnerCompetency, LearnerRisk, Team, User, UserTeam
from app.reporting import service as reporting_service

router = APIRouter(prefix="/analytics", tags=["Deterministic Analytics"])


def _avg(values) -> Optional[float]:
    values = list(values)
    return round(sum(values) / len(values), 4) if values else None


@router.get("/learner/{user_id}")
async def learner_analytics(user_id: UUID, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await mastery_api._visible_learner(db, current_user, tenant_ctx.org_id, user_id)
    states = await competency_service.list_states(db, tenant_ctx.org_id, user_id)
    enrolments = (await db.execute(select(Enrollment).where(Enrollment.org_id == tenant_ctx.org_id, Enrollment.user_id == user_id, Enrollment.status == "active"))).scalars().all()
    answers = sum(s["evidence_count"] for s in states)
    correct = sum(s["correct"] for s in states)
    return {
        "user_id": str(user_id), "competencies_evaluated": len(states), "average_mastery": _avg(s["mastery"] for s in states),
        "mastery_distribution": {b: sum(1 for s in states if s["status"] == b) for b in ("novice", "developing", "competent", "proficient", "expert")},
        "graded_answers": answers, "accuracy_rate": round(correct / answers, 4) if answers else None,
        "active_courses": len(enrolments), "average_course_progress_pct": _avg(e.progress_pct for e in enrolments),
    }


@router.get("/team/{team_id}")
async def team_analytics(team_id: UUID, current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
                         tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    try:
        members, label = await reporting_service.scope_members(db, tenant_ctx.org_id, current_user, team_id)
    except reporting_service.ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    ids = list(members or [])
    states = (await db.execute(select(LearnerCompetency).where(LearnerCompetency.org_id == tenant_ctx.org_id, LearnerCompetency.user_id.in_(ids or [UUID(int=0)]), LearnerCompetency.basis == "evidence",
                                                               LearnerCompetency.data_points_count > 0))).scalars().all()
    risks = (await db.execute(select(LearnerRisk).where(LearnerRisk.org_id == tenant_ctx.org_id, LearnerRisk.user_id.in_(ids or [UUID(int=0)]), LearnerRisk.is_resolved.is_(False)))).scalars().all()
    return {
        "team_id": str(team_id), "team_name": label, "total_members": len(ids), "evaluated_competencies": len({s.competency_id for s in states}), "average_cohort_mastery": _avg(s.mastery_score for s in states),
        "at_risk_breakdown": {level: sum(1 for r in risks if r.risk_level == level) for level in ("critical", "high", "medium", "low")}, "total_unresolved_risks": len(risks),
    }


@router.get("/organization")
async def organization_analytics(current_user: User = Depends(require_roles(["instructor", "org_admin", "super_admin"])), tenant_ctx: TenantContext = Depends(get_current_tenant),
                                 db: AsyncSession = Depends(get_db)):
    org = tenant_ctx.org_id
    users = (await db.execute(select(func.count()).select_from(User).where(User.org_id == org))).scalar() or 0
    courses = (await db.execute(select(func.count()).select_from(Course).where(Course.org_id == org, Course.status == "published"))).scalar() or 0
    enrolments = (await db.execute(select(Enrollment).where(Enrollment.org_id == org, Enrollment.status == "active"))).scalars().all()
    masteries = (await db.execute(select(LearnerCompetency.mastery_score).where(LearnerCompetency.org_id == org, LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0))).scalars().all()
    critical = (await db.execute(select(func.count(func.distinct(LearnerRisk.user_id))).where(LearnerRisk.org_id == org, LearnerRisk.is_resolved.is_(False), LearnerRisk.risk_level == "critical"))).scalar() or 0
    completion = _avg(e.progress_pct for e in enrolments)
    return {"org_id": str(org), "total_users": users, "total_courses": courses, "active_enrollments": len(enrolments),
            "overall_completion_rate_pct": round(completion, 1) if completion is not None else None,
            "organization_mastery_index": _avg(masteries), "critical_at_risk_learners": critical}


@router.get("/events")
async def event_analytics(course_id: Optional[UUID] = None, since: Optional[datetime] = None, until: Optional[datetime] = None, current_user: User = Depends(get_current_user),
                          tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    visible = await event_queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    return await event_queries.stats(db, tenant_ctx.org_id, visible, event_queries.EventFilter(course_id=course_id, since=since, until=until))


@router.get("/competencies")
async def competency_analytics(team_id: Optional[UUID] = None, course_id: Optional[UUID] = None, current_user: User = Depends(require_roles(["ld_admin", "org_admin", "manager"])),
                               tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await mastery_api.cohort_gaps(team_id, course_id, current_user, tenant_ctx, db)
