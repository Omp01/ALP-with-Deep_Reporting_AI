"""
Reports and Scheduled Digest Gateway Router.
"""

from typing import Optional, Dict, Any
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext
from app.models import User
from app.core.config import settings

router = APIRouter(prefix="/reports", tags=["Scheduled Reports & Digests"])


@router.post("/digest/generate")
async def trigger_digest_generation(
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Triggers generation of an on-demand scheduled learning digest."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.reporting_engine_url}/api/v1/reports/digest/generate",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )


@router.get("/digest/latest")
async def get_latest_digest(
    current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Fetches the latest generated digest."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.reporting_engine_url}/api/v1/reports/digest/latest",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )
