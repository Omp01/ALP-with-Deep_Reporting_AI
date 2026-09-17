"""
Organization and Tenant management endpoints.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.models import Organization, AuditLog, User
from app.schemas.auth import TenantInfo
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext

router = APIRouter(prefix="/organizations", tags=["Organizations & Multi-Tenancy"])


@router.get("/me", response_model=TenantInfo)
async def get_my_organization(
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Retrieve metadata of the current tenant."""
    if not tenant_ctx.organization:
        raise HTTPException(status_code=404, detail="Tenant organization not found")
    return tenant_ctx.organization


@router.get("", response_model=List[TenantInfo])
async def list_all_organizations(
    current_user: User = Depends(require_roles(["system_admin"])),
    db: AsyncSession = Depends(get_db),
):
    """System Admin endpoint: List all organizations in the platform."""
    result = await db.execute(select(Organization).order_by(Organization.name))
    return result.scalars().all()


@router.get("/audit-logs")
async def get_tenant_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    current_user: User = Depends(require_roles(["org_admin", "system_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve immutable compliance audit logs for the current tenant.
    Guaranteed tenant-isolated.
    """
    query = (
        select(AuditLog)
        .where(AuditLog.org_id == tenant_ctx.org_id)
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
    )
    if action:
        query = query.where(AuditLog.action == action)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": str(l.id),
            "org_id": str(l.org_id),
            "user_id": str(l.user_id) if l.user_id else None,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "changes": l.changes,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]
