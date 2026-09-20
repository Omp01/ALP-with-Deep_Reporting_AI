"""
Skill graph endpoints: prerequisite relationships between competencies.

Reading the graph is open to any signed-in user of the tenant (learners need it
to understand why something is recommended). Changing it is restricted to
L&D admins and organisation admins.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_current_tenant,
    get_current_user,
    log_audit_action,
    require_roles,
)
from app.core.database import get_db
from app.models import User
from app.schemas.competency import PrerequisiteCreate, PrerequisiteResponse, SkillGraphResponse
from app.services import skill_graph

router = APIRouter(tags=["Skill Graph"])

_EDITORS = ["ld_admin", "org_admin"]


def _raise(exc: skill_graph.SkillGraphError) -> None:
    detail = {"code": exc.code, "message": str(exc)}
    if isinstance(exc, skill_graph.PrerequisiteCycle):
        detail["cycle"] = [str(node) for node in exc.path]
    raise HTTPException(status_code=exc.status_code, detail=detail)


@router.get("/competencies/graph", response_model=SkillGraphResponse)
async def get_skill_graph(
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """The tenant's whole skill graph: competencies with their depth, and prerequisite edges."""
    try:
        return await skill_graph.build_graph(db, tenant_ctx.org_id)
    except skill_graph.SkillGraphError as exc:
        _raise(exc)


@router.get("/competencies/{competency_id}/prerequisites", response_model=List[PrerequisiteResponse])
async def list_prerequisites(
    competency_id: UUID,
    transitive: bool = Query(False, description="Include prerequisites of prerequisites"),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Direct prerequisites of a competency; with `transitive=true`, every ancestor."""
    try:
        await skill_graph._require_competency(db, tenant_ctx.org_id, competency_id)
    except skill_graph.SkillGraphError as exc:
        _raise(exc)

    edges = await skill_graph.load_edges(db, tenant_ctx.org_id)
    if not transitive:
        return [e for e in edges if e.competency_id == competency_id]

    ancestors = skill_graph.transitive_prerequisites(
        [(e.competency_id, e.prerequisite_id) for e in edges], competency_id
    )
    ancestors.add(competency_id)
    return [e for e in edges if e.competency_id in ancestors]


@router.post(
    "/competencies/{competency_id}/prerequisites",
    response_model=PrerequisiteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_prerequisite(
    competency_id: UUID,
    payload: PrerequisiteCreate,
    current_user: User = Depends(require_roles(_EDITORS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Declare that `competency_id` requires `payload.prerequisite_id`. Rejects cycles."""
    try:
        edge = await skill_graph.add_prerequisite(
            db,
            org_id=tenant_ctx.org_id,
            competency_id=competency_id,
            prerequisite_id=payload.prerequisite_id,
            min_mastery=payload.min_mastery,
            rationale=payload.rationale,
            created_by_id=current_user.id,
        )
    except skill_graph.SkillGraphError as exc:
        _raise(exc)

    await log_audit_action(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        action="PREREQUISITE_ADDED",
        resource_type="COMPETENCY",
        resource_id=str(competency_id),
        changes={"prerequisite_id": str(payload.prerequisite_id), "min_mastery": payload.min_mastery},
    )
    return edge


@router.delete(
    "/competencies/{competency_id}/prerequisites/{prerequisite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_prerequisite(
    competency_id: UUID,
    prerequisite_id: UUID,
    current_user: User = Depends(require_roles(_EDITORS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Remove a prerequisite relationship."""
    try:
        await skill_graph.remove_prerequisite(db, tenant_ctx.org_id, competency_id, prerequisite_id)
    except skill_graph.SkillGraphError as exc:
        _raise(exc)

    await log_audit_action(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        action="PREREQUISITE_REMOVED",
        resource_type="COMPETENCY",
        resource_id=str(competency_id),
        changes={"prerequisite_id": str(prerequisite_id)},
    )
