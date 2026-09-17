"""
Analytics Gateway Router.
Proxies deterministic calculations for Learner, Team, and Organization dashboards.
"""

from typing import Optional, Dict, Any
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext
from app.models import User
from app.core.config import settings

router = APIRouter(prefix="/analytics", tags=["Deterministic Analytics"])


@router.get("/learner/{user_id}")
async def get_learner_analytics(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Returns progress, velocity, and mastery analytics for a learner."""
    if current_user.role == "learner" and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only view their own analytics",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.reporting_engine_url}/api/v1/analytics/learner/{user_id}",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )


@router.get("/team/{team_id}")
async def get_team_analytics(
    team_id: UUID,
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Returns aggregated team/cohort performance analytics."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.reporting_engine_url}/api/v1/analytics/team/{team_id}",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )


@router.get("/organization")
async def get_organization_analytics(
    current_user: User = Depends(require_roles(["instructor", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Returns high-level executive KPIs across the organization."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.reporting_engine_url}/api/v1/analytics/organization",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )
