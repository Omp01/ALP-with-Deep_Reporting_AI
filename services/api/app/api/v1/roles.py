"""
Role catalogue and role assignment.

Assignment rules (enforced server-side, spec §36):
  * Only `org_admin` and `super_admin` may change roles.
  * Only `super_admin` may grant, revoke, or modify a `super_admin`.
  * Nobody may change their own roles (no self-escalation, no self-lockout).
  * A user always keeps at least one role.
  * The target must belong to the caller's tenant; anything else is a 404.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    TenantContext,
    effective_roles,
    get_current_tenant,
    get_current_user,
    log_audit_action,
    require_roles,
)
from app.core.database import get_db
from app.core.rbac import Role, legacy_storage_value, normalize_role, normalize_roles
from app.models import RoleDefinition, User, UserRole

router = APIRouter(tags=["Roles"])


class RoleResponse(BaseModel):
    code: str
    name: str
    description: str | None = None
    rank: int


class UserRolesResponse(BaseModel):
    user_id: UUID
    roles: List[str]


class UserRolesUpdate(BaseModel):
    roles: List[str] = Field(..., min_length=1, description="Canonical or legacy role codes")


@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The platform role catalogue, least to most privileged."""
    result = await db.execute(select(RoleDefinition).order_by(RoleDefinition.rank))
    return [
        RoleResponse(code=r.code, name=r.name, description=r.description, rank=r.rank)
        for r in result.scalars().all()
    ]


async def _load_target(db: AsyncSession, user_id: UUID, tenant_ctx: TenantContext) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.role_links).selectinload(UserRole.role))
    )
    target = result.scalar_one_or_none()
    if target is None or target.org_id != tenant_ctx.org_id:
        raise HTTPException(status_code=404, detail="User not found")
    return target


@router.get("/users/{user_id}/roles", response_model=UserRolesResponse)
async def get_user_roles(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """A user's roles. Visible to the user themself and to manager / L&D / admin roles."""
    if user_id != current_user.id and effective_roles(current_user) == {Role.LEARNER}:
        raise HTTPException(status_code=403, detail="Learners can only view their own roles")
    target = await _load_target(db, user_id, tenant_ctx)
    return UserRolesResponse(user_id=target.id, roles=sorted(r.value for r in effective_roles(target)))


@router.put("/users/{user_id}/roles", response_model=UserRolesResponse)
async def set_user_roles(
    user_id: UUID,
    payload: UserRolesUpdate,
    current_user: User = Depends(require_roles(["org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Replace a user's role set."""
    if user_id == current_user.id:
        raise HTTPException(status_code=403, detail="You cannot change your own roles")

    unknown = [r for r in payload.roles if normalize_role(r) is None]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown role(s): {', '.join(unknown)}")
    requested = normalize_roles(payload.roles)

    target = await _load_target(db, user_id, tenant_ctx)
    before = effective_roles(target)

    caller_is_super = Role.SUPER_ADMIN in effective_roles(current_user)
    touches_super = Role.SUPER_ADMIN in requested or Role.SUPER_ADMIN in before
    if touches_super and not caller_is_super:
        raise HTTPException(status_code=403, detail="Only a super admin can grant or change super admin")

    catalogue = {
        r.code: r
        for r in (await db.execute(select(RoleDefinition))).scalars().all()
    }
    missing = [r.value for r in requested if r.value not in catalogue]
    if missing:  # catalogue is seeded by migration 003; this means the DB is misconfigured
        raise HTTPException(status_code=500, detail=f"Role catalogue missing: {', '.join(missing)}")

    await db.execute(delete(UserRole).where(UserRole.user_id == target.id))
    for role in requested:
        db.add(
            UserRole(
                user_id=target.id,
                role_id=catalogue[role.value].id,
                org_id=target.org_id,
                assigned_by_id=current_user.id,
            )
        )
    target.role = legacy_storage_value(requested)  # keep the compatibility column in step
    await db.flush()

    await log_audit_action(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        action="USER_ROLES_CHANGED",
        resource_type="USER",
        resource_id=str(target.id),
        changes={
            "before": sorted(r.value for r in before),
            "after": sorted(r.value for r in requested),
        },
    )
    return UserRolesResponse(user_id=target.id, roles=sorted(r.value for r in requested))
