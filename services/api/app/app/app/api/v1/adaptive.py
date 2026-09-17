"""
Adaptive Learning & Live Competency Gateway Router.
Enforces multi-tenant isolation, role authorization, and proxies to the Adaptive Engine service.
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext
from app.models import User
from app.core.config import settings
from shared.contracts.contracts import AdaptiveNextRequest, AdaptiveNextResponse

router = APIRouter(prefix="/adaptive", tags=["Adaptive Engine & Competencies"])


class NextStepPayload(BaseModel):
    learner_id: Optional[UUID] = None
    session_id: UUID
    course_id: UUID
    current_module_id: Optional[UUID] = None
    current_competency_id: Optional[UUID] = None


@router.post("/next", response_model=AdaptiveNextResponse)
async def get_next_adaptive_step(
    payload: NextStepPayload,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Computes real-time pedagogical recommendation and adapts difficulty/modality.
    Learners request for themselves; managers/admins can request for subordinate learners.
    """
    target_learner_id = payload.learner_id or current_user.id

    # RBAC check: learners can only request their own next step
    if current_user.role == "learner" and target_learner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only request adaptive sequencing for themselves",
        )

    req_body = {
        "learner_id": str(target_learner_id),
        "session_id": str(payload.session_id),
        "course_id": str(payload.course_id),
        "current_module_id": str(payload.current_module_id) if payload.current_module_id else None,
        "current_competency_id": str(payload.current_competency_id) if payload.current_competency_id else None,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.adaptive_engine_url}/api/v1/adaptive/next",
                params={"org_id": str(tenant_ctx.org_id)},
                json=req_body,
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Adaptive Engine returned error: {resp.text}",
                )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Adaptive Engine unreachable: {str(exc)}",
        )


@router.get("/decisions/{learner_id}")
async def get_adaptive_decisions(
    learner_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Retrieves explainable audit log of adaptive sequencing decisions."""
    if current_user.role == "learner" and learner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only inspect their own adaptive decisions",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.adaptive_engine_url}/api/v1/adaptive/decisions/{learner_id}",
                params={"org_id": str(tenant_ctx.org_id), "limit": limit},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Adaptive Engine unreachable: {str(exc)}",
        )


@router.get("/competencies/{learner_id}")
async def get_learner_competency_states(
    learner_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Fetches live mastery, confidence, trend, and error distributions for a learner."""
    if current_user.role == "learner" and learner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only inspect their own competency states",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.adaptive_engine_url}/api/v1/adaptive/competencies/{learner_id}",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Adaptive Engine unreachable: {str(exc)}",
        )


@router.get("/skill-gaps/{learner_id}")
async def get_learner_skill_gaps(
    learner_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Retrieves detected individual skill gaps and recommended interventions."""
    if current_user.role == "learner" and learner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only view their own skill gaps",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.adaptive_engine_url}/api/v1/adaptive/skill-gaps/{learner_id}",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Adaptive Engine unreachable: {str(exc)}",
        )


@router.get("/cohort-gaps/{team_id}")
async def get_cohort_skill_gaps(
    team_id: UUID,
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Aggregates systemic skill gaps across cohort/team members."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.adaptive_engine_url}/api/v1/adaptive/cohort-gaps/{team_id}",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Adaptive Engine unreachable: {str(exc)}",
        )
