"""
FastAPI dependencies for Authentication, Multi-Tenancy, and RBAC guards.
"""

import logging
from typing import Optional, List, Callable, Set
from uuid import UUID
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.rbac import Role, has_any_role, normalize_role, normalize_roles
from app.core.security import decode_access_token
from app.models import User, Organization, AuditLog, UserRole, UserTeam

logger = logging.getLogger("api.authz")

security_scheme = HTTPBearer(auto_error=False)


def effective_roles(user: User) -> Set[Role]:
    """
    The user's canonical role set.

    `user_roles` is authoritative. When it has not been loaded for this instance
    (a user fetched without `selectinload(User.role_links)`), or the user has no
    assignments yet, fall back to the legacy `users.role` column so that a user
    never silently loses access. Reading an unloaded relationship in async code
    would raise, hence the `unloaded` check.
    """
    if "role_links" not in sa_inspect(user).unloaded:
        assigned = normalize_roles(link.role.code for link in user.role_links if link.role)
        if assigned:
            return assigned
    legacy = normalize_role(user.role)
    return {legacy} if legacy else set()


class TenantContext:
    """Carries tenant context for the current request."""
    def __init__(self, org_id: Optional[UUID] = None, organization: Optional[Organization] = None):
        self.org_id = org_id
        self.organization = organization


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate request via JWT Bearer token.
    Loads user along with their organization and team memberships.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("purpose"):       # an embed token is not an access token: it works only on /embed/data
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject identifier missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user ID in token",
        )

    # Fetch user with organization and teams
    query = (
        select(User)
        .where(User.id == user_uuid)
        .options(
            selectinload(User.organization),
            selectinload(User.team_memberships).selectinload(UserTeam.team),
            selectinload(User.role_links).selectinload(UserRole.role),
        )
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with token not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # Validate that the user's organization is active
    if user.organization and not user.organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization tenant is currently deactivated",
        )

    return user


async def get_current_tenant(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """
    Resolves the tenant context for the request:
    - If user is system_admin, they can explicitly pass X-Tenant-ID to switch scope.
    - Standard users are strictly bound to their user.org_id.
    """
    if Role.SUPER_ADMIN in effective_roles(current_user) and x_tenant_id:
        try:
            target_org_id = UUID(x_tenant_id)
            query = select(Organization).where(Organization.id == target_org_id)
            result = await db.execute(query)
            target_org = result.scalar_one_or_none()
            if not target_org:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Requested tenant {x_tenant_id} does not exist",
                )
            return TenantContext(org_id=target_org.id, organization=target_org)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid UUID format for X-Tenant-ID",
            )

    # Default to user's assigned organization
    return TenantContext(org_id=current_user.org_id, organization=current_user.organization)


def require_roles(allowed_roles: List[str]) -> Callable:
    """
    Dependency factory to enforce Role-Based Access Control (RBAC).
    Accepts canonical (`ld_admin`, `super_admin`) and legacy (`instructor`,
    `system_admin`) spellings interchangeably. `super_admin` always passes.
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        held = effective_roles(current_user)
        if not has_any_role(held, allowed_roles):
            logger.warning(
                '{"event": "authorization_denied", "user_id": "%s", "org_id": "%s", "roles": %s, "required": %s}',
                current_user.id,
                current_user.org_id,
                sorted(r.value for r in held),
                sorted(r.value for r in normalize_roles(allowed_roles)),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            )
        return current_user

    return role_checker


async def log_audit_action(
    db: AsyncSession,
    org_id: UUID,
    user_id: Optional[UUID],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    changes: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Create an immutable audit log record."""
    audit_entry = AuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes or {},
        ip_address=ip_address,
    )
    db.add(audit_entry)
    await db.flush()
