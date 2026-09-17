"""
User management endpoints (strictly tenant-isolated).
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import User, UserTeam
from app.schemas.auth import UserProfileResponse, TenantInfo
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserProfileResponse])
async def list_tenant_users(
    role: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles(["org_admin", "instructor", "manager"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    List users belonging to the caller's organization.
    """
    query = (
        select(User)
        .where(User.org_id == tenant_ctx.org_id)
        .options(
            selectinload(User.organization),
            selectinload(User.team_memberships).selectinload(UserTeam.team),
        )
        .order_by(User.full_name)
        .limit(limit)
        .offset(offset)
    )

    if role:
        query = query.where(User.role == role)

    result = await db.execute(query)
    users = result.scalars().all()

    response = []
    for u in users:
        org_info = None
        if u.organization:
            org_info = TenantInfo(
                id=u.organization.id,
                name=u.organization.name,
                slug=u.organization.slug,
                is_active=u.organization.is_active,
            )
        teams = [tm.team.name for tm in u.team_memberships if tm.team]
        response.append(
            UserProfileResponse(
                id=u.id,
                org_id=u.org_id,
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                avatar_url=u.avatar_url,
                is_active=u.is_active,
                created_at=u.created_at,
                organization=org_info,
                teams=teams,
            )
        )
    return response


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_detail(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve user detail.
    Strictly isolated: users cannot view profiles across organizations.
    """
    query = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.organization),
            selectinload(User.team_memberships).selectinload(UserTeam.team),
        )
    )
    result = await db.execute(query)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Multi-tenant isolation check
    if current_user.role != "system_admin" and target_user.org_id != tenant_ctx.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in current organization",
        )

    org_info = None
    if target_user.organization:
        org_info = TenantInfo(
            id=target_user.organization.id,
            name=target_user.organization.name,
            slug=target_user.organization.slug,
            is_active=target_user.organization.is_active,
        )
    teams = [tm.team.name for tm in target_user.team_memberships if tm.team]

    return UserProfileResponse(
        id=target_user.id,
        org_id=target_user.org_id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=target_user.role,
        avatar_url=target_user.avatar_url,
        is_active=target_user.is_active,
        created_at=target_user.created_at,
        organization=org_info,
        teams=teams,
    )
