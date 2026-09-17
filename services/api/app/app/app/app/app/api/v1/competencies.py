"""
Competency Knowledge Graph and Curriculum Mapping API endpoints.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models import (
    Competency,
    Course,
    Module,
    CourseCompetency,
    ModuleCompetency,
    User,
)
from app.schemas.competency import (
    CompetencyCreate,
    CompetencyUpdate,
    CompetencyResponse,
    CourseCompetencyMapRequest,
    ModuleCompetencyMapRequest,
)
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext

router = APIRouter(tags=["Competencies & Taxonomy"])


@router.get("/competencies", response_model=List[CompetencyResponse])
async def list_competencies(
    taxonomy_level: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List competencies in the tenant's curriculum knowledge graph."""
    query = (
        select(Competency)
        .where(Competency.org_id == tenant_ctx.org_id)
        .order_by(Competency.name)
        .limit(limit)
        .offset(offset)
    )
    if taxonomy_level:
        query = query.where(Competency.taxonomy_level == taxonomy_level)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/competencies", response_model=CompetencyResponse, status_code=status.HTTP_201_CREATED)
async def create_competency(
    payload: CompetencyCreate,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new competency node in Bloom's taxonomy framework."""
    existing = await db.execute(
        select(Competency).where(and_(Competency.org_id == tenant_ctx.org_id, Competency.code == payload.code))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Competency code '{payload.code}' already exists")

    competency = Competency(
        org_id=tenant_ctx.org_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        taxonomy_level=payload.taxonomy_level,
        parent_id=payload.parent_id,
    )
    db.add(competency)
    await db.flush()
    return competency


@router.get("/competencies/{competency_id}", response_model=CompetencyResponse)
async def get_competency(
    competency_id: UUID,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve competency detail."""
    result = await db.execute(
        select(Competency).where(and_(Competency.id == competency_id, Competency.org_id == tenant_ctx.org_id))
    )
    comp = result.scalar_one_or_none()
    if not comp:
        raise HTTPException(status_code=404, detail="Competency not found")
    return comp


@router.post("/courses/{course_id}/competencies", status_code=status.HTTP_201_CREATED)
async def map_course_competency(
    course_id: UUID,
    payload: CourseCompetencyMapRequest,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Map target competency and mastery benchmark to a course."""
    # Verify course exists
    course = await db.execute(
        select(Course).where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
    )
    if not course.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Course not found")

    # Verify competency exists
    comp = await db.execute(
        select(Competency).where(and_(Competency.id == payload.competency_id, Competency.org_id == tenant_ctx.org_id))
    )
    if not comp.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Competency not found")

    # Upsert mapping
    existing = await db.execute(
        select(CourseCompetency).where(
            and_(CourseCompetency.course_id == course_id, CourseCompetency.competency_id == payload.competency_id)
        )
    )
    mapping = existing.scalar_one_or_none()
    if mapping:
        mapping.target_mastery = payload.target_mastery
        mapping.is_primary = payload.is_primary
    else:
        mapping = CourseCompetency(
            course_id=course_id,
            competency_id=payload.competency_id,
            target_mastery=payload.target_mastery,
            is_primary=payload.is_primary,
        )
        db.add(mapping)

    await db.flush()
    return {"status": "success", "course_id": str(course_id), "competency_id": str(payload.competency_id)}


@router.post("/modules/{module_id}/competencies", status_code=status.HTTP_201_CREATED)
async def map_module_competency(
    module_id: UUID,
    payload: ModuleCompetencyMapRequest,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Map competency and evaluation weight to an instructional module."""
    module_res = await db.execute(
        select(Module).where(and_(Module.id == module_id, Module.org_id == tenant_ctx.org_id))
    )
    if not module_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Module not found")

    comp_res = await db.execute(
        select(Competency).where(and_(Competency.id == payload.competency_id, Competency.org_id == tenant_ctx.org_id))
    )
    if not comp_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Competency not found")

    existing = await db.execute(
        select(ModuleCompetency).where(
            and_(ModuleCompetency.module_id == module_id, ModuleCompetency.competency_id == payload.competency_id)
        )
    )
    mapping = existing.scalar_one_or_none()
    if mapping:
        mapping.weight = payload.weight
    else:
        mapping = ModuleCompetency(
            module_id=module_id,
            competency_id=payload.competency_id,
            weight=payload.weight,
        )
        db.add(mapping)

    await db.flush()
    return {"status": "success", "module_id": str(module_id), "competency_id": str(payload.competency_id)}
