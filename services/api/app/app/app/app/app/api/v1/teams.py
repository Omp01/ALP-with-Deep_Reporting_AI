"""
Team and Cohort Management API Endpoints.
Guaranteed tenant-isolated.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Team, UserTeam, User
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext

router = APIRouter(prefix="/teams", tags=["Teams & Cohorts"])


class TeamResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: Optional[str] = None
    manager_id: Optional[UUID] = None
    member_count: int = 0


@router.get("", response_model=List[TeamResponse])
async def list_teams(
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all teams/cohorts belonging to the caller's organization."""
    query = (
        select(Team)
        .where(Team.org_id == tenant_ctx.org_id)
        .options(selectinload(Team.memberships))
        .order_by(Team.name)
    )
    result = await db.execute(query)
    teams = result.scalars().all()

    return [
        TeamResponse(
            id=t.id,
            org_id=t.org_id,
            name=t.name,
            description=t.description,
            manager_id=t.manager_id,
            member_count=len(t.memberships),
        )
        for t in teams
    ]


@router.get("/{team_id}/members")
async def get_team_members(
    team_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve members belonging to a specific team."""
    query = (
        select(UserTeam)
        .where(UserTeam.org_id == tenant_ctx.org_id, UserTeam.team_id == team_id)
        .options(selectinload(UserTeam.user))
    )
    result = await db.execute(query)
    memberships = result.scalars().all()

    return [
        {
            "user_id": str(m.user_id),
            "email": m.user.email if m.user else None,
            "full_name": m.user.full_name if m.user else None,
            "role": m.user.role if m.user else None,
            "joined_at": m.joined_at.isoformat(),
        }
        for m in memberships
    ]
