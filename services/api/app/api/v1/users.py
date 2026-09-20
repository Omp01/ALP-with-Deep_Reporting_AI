"""
User directory endpoints (strictly tenant-isolated).
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.rbac import Role, normalize_role
from app.models import RoleDefinition, User, UserRole, UserTeam
from app.schemas.auth import UserProfileResponse
from app.api.deps import (
    get_current_user,
    get_current_tenant,
    require_roles,
    effective_roles,
    TenantContext,
)
from app.services.user_profiles import build_user_profile

router = APIRouter(prefix="/users", tags=["Users"])

_PROFILE_LOAD_OPTIONS = (
    selectinload(User.organization),
    selectinload(User.team_memberships).selectinload(UserTeam.team),
    selectinload(User.role_links).selectinload(UserRole.role),
)


@router.get("", response_model=List[UserProfileResponse])
async def list_tenant_users(
    role: Optional[str] = Query(None, description="Filter by role (canonical or legacy spelling)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles(["org_admin", "ld_admin", "manager"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List users belonging to the caller's organization."""
    query = (
        select(User)
        .where(User.org_id == tenant_ctx.org_id)
        .options(*_PROFILE_LOAD_OPTIONS)
        .order_by(User.full_name)
        .limit(limit)
        .offset(offset)
    )

    if role:
        wanted = normalize_role(role)
        if wanted is None:
            raise HTTPException(status_code=400, detail=f"Unknown role '{role}'")
        holders = (
            select(UserRole.user_id)
            .join(RoleDefinition, RoleDefinition.id == UserRole.role_id)
            .where(RoleDefinition.code == wanted.value)
        )
        query = query.where(User.id.in_(holders))

    result = await db.execute(query)
    return [build_user_profile(u) for u in result.scalars().all()]


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_detail(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a user profile.

    A learner may only read their own profile; other roles may read profiles
    within their own organization. Cross-tenant lookups return 404, the same as
    a missing user, so ids cannot be probed across organizations.
    """
    is_self = user_id == current_user.id
    if not is_self and effective_roles(current_user) == {Role.LEARNER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only view their own profile",
        )

    result = await db.execute(
        select(User).where(User.id == user_id).options(*_PROFILE_LOAD_OPTIONS)
    )
    target_user = result.scalar_one_or_none()

    if not target_user or target_user.org_id != tenant_ctx.org_id:
        raise HTTPException(status_code=404, detail="User not found")

    return build_user_profile(target_user)
