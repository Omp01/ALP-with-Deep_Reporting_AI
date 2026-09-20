"""
Builds the public user profile shape. One implementation, used by auth and users.
"""

from app.api.deps import effective_roles
from app.core.rbac import ROLE_RANK
from app.models import User
from app.schemas.auth import TenantInfo, UserProfileResponse


def build_user_profile(user: User) -> UserProfileResponse:
    """
    Convert a User (with `organization`, `team_memberships` and `role_links`
    eager-loaded) into its API shape.

    `role` keeps the legacy spelling the existing frontend already understands;
    `roles` is the canonical, authoritative list, most privileged first.
    """
    org_info = None
    if user.organization:
        org_info = TenantInfo(
            id=user.organization.id,
            name=user.organization.name,
            slug=user.organization.slug,
            is_active=user.organization.is_active,
        )

    teams = [tm.team.name for tm in user.team_memberships if tm.team]
    roles = sorted(effective_roles(user), key=lambda r: ROLE_RANK[r], reverse=True)

    return UserProfileResponse(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        roles=[r.value for r in roles],
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        created_at=user.created_at,
        organization=org_info,
        teams=teams,
    )
