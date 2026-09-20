"""
Competency state, its explanation, skill gaps and evidence.

    GET /mastery/parameters                                the constants of the deterministic update
    GET /mastery/me                                        the caller's competency states
    GET /mastery/me/gaps                                   the caller's skill gaps, with reasons
    GET /mastery/learners/{id}                             a learner's states (learner: self; manager: team; admin: tenant)
    GET /mastery/learners/{id}/gaps
    GET /mastery/learners/{id}/competencies/{cid}/explain  "why is mastery this?": the evidence chain, previous -> new
    GET /mastery/learners/{id}/competencies/{cid}/verify  recompute the chain and compare with the stored state
    GET /mastery/cohort-gaps                               team-level gaps as counts (managers and admins)
    GET /mastery/evidence/{id}                             one piece of evidence and where it came from

Only evidence-based state is shown. A learner with no graded evidence for a competency has no mastery for it, not a default.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, get_current_user, get_db, require_roles
from app.competency import bkt, insight, service
from app.events import queries as event_queries
from app.models import EvidenceRecord, Team, User, UserTeam

router = APIRouter(prefix="/mastery", tags=["Competency State & Evidence"])

METHOD_NOTES = {
    "method": bkt.METHOD,
    "description": "Bayesian Knowledge Tracing with soft evidence. A language model may produce the signal for a written answer; it never produces mastery.",
    "confidence": "evidence weight / (evidence weight + confidence_k): how much evidence stands behind the estimate, not how high it is",
    "not_evidence": "Watching or reading. Lessons add time on task but never move mastery.",
}


async def _visible_learner(db: AsyncSession, viewer: User, org_id: UUID, user_id: UUID) -> None:
    visible = await event_queries.visible_user_ids(db, viewer, org_id)
    if visible is not None and user_id not in visible:
        raise HTTPException(status_code=404, detail="Learner not found")
    if visible is None:   # admins may see anyone in the tenant, but the id must exist there
        exists = (await db.execute(select(User.id).where(User.id == user_id, User.org_id == org_id))).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="Learner not found")


@router.get("/parameters")
async def parameters(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return {**METHOD_NOTES, "parameters": service.params_from_settings().as_dict()}


@router.get("/me")
async def my_states(current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    return {"user_id": str(current_user.id), "competencies": await service.list_states(db, tenant_ctx.org_id, current_user.id)}


@router.get("/me/gaps")
async def my_gaps(course_id: Optional[UUID] = None, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                  db: AsyncSession = Depends(get_db)):
    found = await insight.learner_gaps(db, tenant_ctx.org_id, current_user.id, course_id)
    return {"user_id": str(current_user.id), "gaps": [g.as_dict() for g in found if g.is_gap], "not_enough_evidence": [g.as_dict() for g in found if g.note and not g.is_gap]}


@router.get("/learners/{user_id}")
async def learner_states(user_id: UUID, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                         db: AsyncSession = Depends(get_db)):
    await _visible_learner(db, current_user, tenant_ctx.org_id, user_id)
    return {"user_id": str(user_id), "competencies": await service.list_states(db, tenant_ctx.org_id, user_id)}


@router.get("/learners/{user_id}/gaps")
async def learner_gaps(user_id: UUID, course_id: Optional[UUID] = None, current_user: User = Depends(get_current_user),
                       tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await _visible_learner(db, current_user, tenant_ctx.org_id, user_id)
    found = await insight.learner_gaps(db, tenant_ctx.org_id, user_id, course_id)
    return {"user_id": str(user_id), "gaps": [g.as_dict() for g in found if g.is_gap], "not_enough_evidence": [g.as_dict() for g in found if g.note and not g.is_gap]}


@router.get("/learners/{user_id}/competencies/{competency_id}/explain")
async def explain(user_id: UUID, competency_id: UUID, current_user: User = Depends(get_current_user),
                  tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    """Why is this learner's mastery what it is? The evidence chain, in order, each link traceable to a stored answer or grade."""
    await _visible_learner(db, current_user, tenant_ctx.org_id, user_id)
    result = await service.explain(db, tenant_ctx.org_id, user_id, competency_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No evidence has been recorded for this competency yet")
    return result


@router.get("/learners/{user_id}/competencies/{competency_id}/verify")
async def verify(user_id: UUID, competency_id: UUID, current_user: User = Depends(get_current_user),
                 tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    """Recompute the state from the stored evidence chain and compare it with what is stored."""
    await _visible_learner(db, current_user, tenant_ctx.org_id, user_id)
    return await service.verify(db, tenant_ctx.org_id, user_id, competency_id)


@router.get("/cohort-gaps")
async def cohort_gaps(
    team_id: Optional[UUID] = None, course_id: Optional[UUID] = None,
    current_user: User = Depends(require_roles(["ld_admin", "org_admin", "manager"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    """For each competency, how many assessed learners are below the target. Counts, so nobody hides behind an average."""
    visible = await event_queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    members = visible
    if team_id is not None:
        team = (await db.execute(select(Team).where(Team.id == team_id, Team.org_id == tenant_ctx.org_id))).scalar_one_or_none()
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        ids = set((await db.execute(select(UserTeam.user_id).where(UserTeam.team_id == team_id, UserTeam.org_id == tenant_ctx.org_id))).scalars())
        if visible is not None and not ids <= visible and team.manager_id != current_user.id:
            raise HTTPException(status_code=404, detail="Team not found")
        members = ids if visible is None else ids & visible
    return await insight.cohort_gaps(db, tenant_ctx.org_id, members, course_id)


@router.get("/evidence/{evidence_id}")
async def evidence_detail(evidence_id: UUID, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                          db: AsyncSession = Depends(get_db)):
    """One piece of evidence with its inputs and source. Citations in reports point here."""
    record = (await db.execute(select(EvidenceRecord).where(EvidenceRecord.id == evidence_id, EvidenceRecord.org_id == tenant_ctx.org_id))).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await _visible_learner(db, current_user, tenant_ctx.org_id, record.user_id)
    return {
        "id": str(record.id), "user_id": str(record.user_id), "competency_id": str(record.competency_id), "source_type": record.source_type,
        "source_event_id": str(record.source_event_id) if record.source_event_id else None, "session_id": str(record.session_id) if record.session_id else None,
        "signal": record.signal, "confidence": record.confidence, "error_type": record.error_type, "evidence_quote": record.evidence_quote,
        "difficulty": record.difficulty, "attempt_number": record.attempt_number, "response_time_ms": record.response_time_ms,
        "occurred_at": record.occurred_at.isoformat(), "source": await service._source_of(db, record),
    }
