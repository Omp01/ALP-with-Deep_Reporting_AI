"""
Course, Module, and Content Item management API endpoints.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Course, Module, ContentItem, User
from app.schemas.course import (
    CourseCreate,
    CourseUpdate,
    CourseResponse,
    ModuleCreate,
    ModuleUpdate,
    ModuleResponse,
    ContentItemCreate,
    ContentItemResponse,
)
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext, log_audit_action

router = APIRouter(tags=["Courses & Content"])


# =============================================================================
# Course Endpoints
# =============================================================================

@router.get("/courses", response_model=List[CourseResponse])
async def list_courses(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all courses within caller's organization."""
    query = (
        select(Course)
        .where(Course.org_id == tenant_ctx.org_id)
        .options(
            selectinload(Course.modules).selectinload(Module.content_items)
        )
        .order_by(Course.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.where(Course.status == status)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseCreate,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new course."""
    # Verify course code uniqueness within tenant
    existing = await db.execute(
        select(Course).where(and_(Course.org_id == tenant_ctx.org_id, Course.code == payload.code))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Course code '{payload.code}' already exists in organization")

    course = Course(
        org_id=tenant_ctx.org_id,
        title=payload.title,
        code=payload.code,
        description=payload.description,
        status=payload.status,
        created_by_id=current_user.id,
        course_metadata=payload.course_metadata,
    )
    db.add(course)
    await db.flush()

    await log_audit_action(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        action="COURSE_CREATED",
        resource_type="COURSE",
        resource_id=str(course.id),
        changes={"title": payload.title, "code": payload.code},
    )

    query = (
        select(Course)
        .where(Course.id == course.id)
        .options(selectinload(Course.modules).selectinload(Module.content_items))
    )
    res = await db.execute(query)
    return res.scalar_one()


@router.get("/courses/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: UUID,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get a course by ID with its nested modules and content items."""
    query = (
        select(Course)
        .where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
        .options(
            selectinload(Course.modules).selectinload(Module.content_items)
        )
    )
    result = await db.execute(query)
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.put("/courses/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update course title, description, code, or metadata."""
    query = (
        select(Course)
        .where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
        .options(selectinload(Course.modules).selectinload(Module.content_items))
    )
    result = await db.execute(query)
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if payload.title is not None:
        course.title = payload.title
    if payload.code is not None:
        course.code = payload.code
    if payload.description is not None:
        course.description = payload.description
    if payload.status is not None:
        course.status = payload.status
    if payload.course_metadata is not None:
        course.course_metadata = payload.course_metadata

    await db.flush()
    return course


@router.post("/courses/{course_id}/publish", response_model=CourseResponse)
async def publish_course(
    course_id: UUID,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Publish a draft course making it available for enrollment."""
    query = (
        select(Course)
        .where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
        .options(selectinload(Course.modules).selectinload(Module.content_items))
    )
    result = await db.execute(query)
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    course.status = "published"
    await db.flush()
    return course


# =============================================================================
# Module Endpoints
# =============================================================================

@router.get("/courses/{course_id}/modules", response_model=List[ModuleResponse])
async def list_course_modules(
    course_id: UUID,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all modules belonging to a course, in sequence order."""
    query = (
        select(Module)
        .where(and_(Module.course_id == course_id, Module.org_id == tenant_ctx.org_id))
        .options(selectinload(Module.content_items))
        .order_by(Module.sequence_order)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/courses/{course_id}/modules", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(
    course_id: UUID,
    payload: ModuleCreate,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new module within a course."""
    # Verify course exists
    course = await db.execute(
        select(Course).where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
    )
    if not course.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Course not found")

    module = Module(
        org_id=tenant_ctx.org_id,
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        sequence_order=payload.sequence_order,
        estimated_duration_mins=payload.estimated_duration_mins,
    )
    db.add(module)
    await db.flush()

    query = (
        select(Module)
        .where(Module.id == module.id)
        .options(selectinload(Module.content_items))
    )
    res = await db.execute(query)
    return res.scalar_one()


@router.get("/modules/{module_id}", response_model=ModuleResponse)
async def get_module(
    module_id: UUID,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get single module with content items."""
    query = (
        select(Module)
        .where(and_(Module.id == module_id, Module.org_id == tenant_ctx.org_id))
        .options(selectinload(Module.content_items))
    )
    result = await db.execute(query)
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


# =============================================================================
# Content Item Endpoints
# =============================================================================

@router.post("/modules/{module_id}/content", response_model=ContentItemResponse, status_code=status.HTTP_201_CREATED)
async def create_content_item(
    module_id: UUID,
    payload: ContentItemCreate,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Add a content resource to a module."""
    module_res = await db.execute(
        select(Module).where(and_(Module.id == module_id, Module.org_id == tenant_ctx.org_id))
    )
    if not module_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Module not found")

    content_item = ContentItem(
        org_id=tenant_ctx.org_id,
        module_id=module_id,
        title=payload.title,
        content_type=payload.content_type,
        content_url=payload.content_url,
        raw_text=payload.raw_text,
        transcript=payload.transcript,
        item_metadata=payload.item_metadata,
        chunk_count=1 if payload.raw_text else 0,
    )
    db.add(content_item)
    await db.flush()
    return content_item


@router.get("/content/{content_id}", response_model=ContentItemResponse)
async def get_content_item(
    content_id: UUID,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve content item detail."""
    result = await db.execute(
        select(ContentItem).where(and_(ContentItem.id == content_id, ContentItem.org_id == tenant_ctx.org_id))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    return item
