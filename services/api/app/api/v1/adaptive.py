"""
Adaptive Learning & Live Competency Router.

`/next` and `/decisions` are served by the adaptive engine in this service (app/adaptive: a deterministic decision from stored
evidence, stored with the facts it used, so "Why am I seeing this?" is answered from the record). The competency state, skill gap
and cohort gap paths are served by the competency engine (app/competency).
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adaptive import service as adaptive_service
from app.api.deps import get_current_user, get_current_tenant, get_db, require_roles, TenantContext
from app.api.v1 import mastery as mastery_api
from app.competency import service as competency_service
from app.events import queries as event_queries
from app.models import User

router = APIRouter(prefix="/adaptive", tags=["Adaptive Engine & Competencies"])


class NextStepPayload(BaseModel):
    course_id: Optional[UUID] = None
    competency_id: Optional[UUID] = None       # default: the competency of the learner's latest evidence
    session_id: Optional[UUID] = None          # the learning session this happens in, when known


@router.post("/next")
async def get_next_adaptive_step(
    payload: NextStepPayload,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    What the caller should do next, and why. The decision is computed from stored evidence (never from the request), stored,
    and recorded as an `adaptive_decision_made` event. There is no learner_id: you can only ask for yourself.
    """
    try:
        return await adaptive_service.next_step(db, org_id=tenant_ctx.org_id, user=current_user, course_id=payload.course_id, competency_id=payload.competency_id,
                                                session_id=payload.session_id)
    except adaptive_service.AdaptiveError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.get("/decisions/{learner_id}")
async def get_adaptive_decisions(
    learner_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """The stored decisions for a learner, newest first, with the facts each one used."""
    await mastery_api._visible_learner(db, current_user, tenant_ctx.org_id, learner_id)
    return await adaptive_service.history(db, tenant_ctx.org_id, learner_id, limit)


# Competency state, skill gaps and cohort gaps are computed by the competency engine from stored evidence (app/competency),
# not by the adaptive-engine service. These paths are kept for existing clients; new clients use /mastery.

@router.get("/competencies/{learner_id}")
async def get_learner_competency_states(
    learner_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Mastery, confidence, trend (from the update history) and evidence counts for a learner. Only evidence-based state is returned."""
    await mastery_api._visible_learner(db, current_user, tenant_ctx.org_id, learner_id)
    return await competency_service.list_states(db, tenant_ctx.org_id, learner_id)


@router.get("/skill-gaps/{learner_id}")
async def get_learner_skill_gaps(
    learner_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Skill gaps of a learner: competencies below their target with enough evidence, each with the reasons and figures behind it."""
    found = await mastery_api.learner_gaps(learner_id, None, current_user, tenant_ctx, db)
    return {"learner_id": str(learner_id), "gaps_count": len(found["gaps"]), "skill_gaps": found["gaps"], "not_enough_evidence": found["not_enough_evidence"]}


@router.get("/cohort-gaps/{team_id}")
async def get_cohort_skill_gaps(
    team_id: UUID,
    current_user: User = Depends(require_roles(["ld_admin", "manager", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """For a team: per competency, how many assessed learners are below the target."""
    result = await mastery_api.cohort_gaps(team_id, None, current_user, tenant_ctx, db)
    return {"team_id": str(team_id), **result, "systemic_skill_gaps": [c for c in result["competencies"] if c["learners_below_target"] > 0]}
