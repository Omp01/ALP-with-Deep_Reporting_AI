"""
Course, Module, and Content Item management API endpoints.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Course, Module, ContentItem, User, Enrollment
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
from app.api.deps import get_current_user, get_current_tenant, require_roles, effective_roles, TenantContext, log_audit_action
from app.core.rbac import has_any_role
from app.models import Competency, CourseCompetency
from app.services import progress as progress_service
from app.services.course_metrics import duration_minutes

router = APIRouter(tags=["Courses & Content"])


def course_duration_minutes(course: Course) -> Optional[int]:
    """Real duration of a course (see app.services.course_metrics.duration_minutes)."""
    total_seconds = sum(
        item.duration_seconds or 0
        for module in course.modules
        for item in module.content_items
        if item.status == progress_service.PUBLISHED
    )
    return duration_minutes(course.duration_minutes, total_seconds)


def _is_author(user: User) -> bool:
    return has_any_role(effective_roles(user), ["ld_admin", "org_admin"])


async def _course_skills(db: AsyncSession, org_id: UUID, course_ids: List[UUID]) -> dict:
    """Competency names per course, primary competencies first."""
    if not course_ids:
        return {}
    rows = await db.execute(
        select(CourseCompetency.course_id, Competency.name)
        .join(Competency, Competency.id == CourseCompetency.competency_id)
        .where(CourseCompetency.course_id.in_(course_ids), Competency.org_id == org_id)
        .order_by(CourseCompetency.is_primary.desc(), Competency.name)
    )
    skills: dict = {}
    for course_id, name in rows.all():
        skills.setdefault(course_id, []).append(name)
    return skills


def build_course_response(
    course: Course,
    enrollment: Optional[Enrollment] = None,
    enrollment_count: int = 0,
    progress_pct: Optional[float] = None,
    skills: Optional[List[str]] = None,
) -> CourseResponse:
    """Single place that turns a Course row into its API shape with derived fields."""
    response = CourseResponse.model_validate(course)
    response.duration_minutes = course_duration_minutes(course)
    response.enrollment_count = enrollment_count
    response.instructor_name = course.instructor.full_name if course.instructor else None
    response.is_enrolled = enrollment is not None
    # Derived progress when the caller supplies it; the stored value is only a cache.
    response.progress_pct = progress_pct if progress_pct is not None else (enrollment.progress_pct if enrollment else 0.0)
    response.skills = skills or []
    return response


# =============================================================================
# Course Endpoints
# =============================================================================

@router.get("/courses", response_model=List[CourseResponse])
async def list_courses(
    status: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("popular", description="popular, newest, rating, title"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all courses within caller's organization with rich filters, search, and enrollment status."""
    enrollment_counts = (
        select(Enrollment.course_id.label("course_id"), func.count(Enrollment.user_id).label("n"))
        .where(Enrollment.org_id == tenant_ctx.org_id)
        .group_by(Enrollment.course_id)
        .subquery()
    )
    enrolled_n = func.coalesce(enrollment_counts.c.n, 0)
    query = (
        select(Course, enrolled_n)
        .outerjoin(enrollment_counts, enrollment_counts.c.course_id == Course.id)
        .where(Course.org_id == tenant_ctx.org_id)
        .options(
            selectinload(Course.modules).selectinload(Module.content_items),
            selectinload(Course.instructor),
        )
    )

    # Learners only ever see published courses; authors may filter by any status.
    if not _is_author(current_user):
        query = query.where(Course.status == "published")
    elif status:
        query = query.where(Course.status == status)

    if category and category.lower() != "all":
        query = query.where(Course.category.ilike(f"%{category}%"))

    if difficulty and difficulty.lower() != "all":
        query = query.where(Course.difficulty.ilike(f"%{difficulty}%"))

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Course.title.ilike(search_pattern),
                Course.description.ilike(search_pattern),
                Course.code.ilike(search_pattern),
            )
        )

    # Sorting
    if sort_by == "rating":
        # No ratings source exists yet, so unrated courses (all of them today) tie and
        # fall back to title order rather than pretending to a ranking.
        query = query.order_by(Course.rating.desc().nulls_last(), Course.title.asc())
    elif sort_by == "newest":
        query = query.order_by(Course.created_at.desc())
    elif sort_by == "title":
        query = query.order_by(Course.title.asc())
    else:  # popular = most enrolled learners
        query = query.order_by(enrolled_n.desc(), Course.created_at.desc())

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    course_rows = result.all()

    # Query active enrollments for current user
    enr_res = await db.execute(
        select(Enrollment).where(
            and_(
                Enrollment.user_id == current_user.id,
                Enrollment.org_id == tenant_ctx.org_id,
                Enrollment.status == "active",
            )
        )
    )
    user_enrollments = {e.course_id: e for e in enr_res.scalars().all()}

    # Annotate dynamic fields
    course_ids = [c.id for c, _ in course_rows]
    derived = await progress_service.progress_for_courses(db, tenant_ctx.org_id, current_user.id, course_ids)
    skills = await _course_skills(db, tenant_ctx.org_id, course_ids)
    return [
        build_course_response(
            c, user_enrollments.get(c.id), enrollment_count=count,
            progress_pct=derived[c.id].percent if c.id in user_enrollments else 0.0,
            skills=skills.get(c.id, []),
        )
        for c, count in course_rows
    ]


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
        category=payload.category,
        difficulty=payload.difficulty,
        duration_minutes=payload.duration_minutes,
        thumbnail_url=payload.thumbnail_url,
        created_by_id=current_user.id,
        instructor_id=current_user.id,
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
        .options(
            selectinload(Course.modules).selectinload(Module.content_items),
            selectinload(Course.instructor),
        )
    )
    res = await db.execute(query)
    return build_course_response(res.scalar_one())


@router.get("/courses/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get a course by ID with its nested modules, content items, and user enrollment status."""
    query = (
        select(Course)
        .where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
        .options(
            selectinload(Course.modules).selectinload(Module.content_items),
            selectinload(Course.instructor),
        )
    )
    result = await db.execute(query)
    course = result.scalar_one_or_none()
    if not course or (course.status != "published" and not _is_author(current_user)):
        raise HTTPException(status_code=404, detail="Course not found")

    enr_res = await db.execute(
        select(Enrollment).where(
            and_(
                Enrollment.user_id == current_user.id,
                Enrollment.course_id == course_id,
                Enrollment.status == "active",
            )
        )
    )
    enr = enr_res.scalar_one_or_none()

    count_res = await db.execute(
        select(func.count(Enrollment.user_id)).where(
            and_(Enrollment.course_id == course_id, Enrollment.org_id == tenant_ctx.org_id)
        )
    )
    derived = (await progress_service.progress_for_courses(db, tenant_ctx.org_id, current_user.id, [course_id]))[course_id]
    skills = await _course_skills(db, tenant_ctx.org_id, [course_id])
    return build_course_response(
        course, enr, enrollment_count=count_res.scalar() or 0,
        progress_pct=derived.percent if enr else 0.0, skills=skills.get(course_id, []),
    )


@router.post("/courses/{course_id}/enroll", response_model=dict)
async def enroll_course_shortcut(
    course_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Direct enrollment endpoint for learners."""
    course_res = await db.execute(
        select(Course).where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
    )
    course = course_res.scalar_one_or_none()
    if not course or (course.status != "published" and not _is_author(current_user)):
        raise HTTPException(status_code=404, detail="Course not found")

    existing = await db.execute(
        select(Enrollment).where(
            and_(
                Enrollment.user_id == current_user.id,
                Enrollment.course_id == course_id,
                Enrollment.status == "active",
            )
        )
    )
    enrollment = existing.scalar_one_or_none()
    if not enrollment:
        enrollment = Enrollment(
            org_id=tenant_ctx.org_id,
            user_id=current_user.id,
            course_id=course_id,
            status="active",
            progress_pct=0.0,
            enrolled_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
        )
        db.add(enrollment)
        await db.flush()

        await log_audit_action(
            db=db,
            org_id=tenant_ctx.org_id,
            user_id=current_user.id,
            action="COURSE_ENROLLMENT",
            resource_type="ENROLLMENT",
            resource_id=str(enrollment.id),
            changes={"course_id": str(course_id)},
        )

    return {
        "status": "enrolled",
        "course_id": str(course_id),
        "enrollment_id": str(enrollment.id),
        "progress_pct": enrollment.progress_pct,
    }


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
        .options(selectinload(Course.modules).selectinload(Module.content_items), selectinload(Course.instructor))
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
    if payload.category is not None:
        course.category = payload.category
    if payload.difficulty is not None:
        course.difficulty = payload.difficulty
    if payload.duration_minutes is not None:
        course.duration_minutes = payload.duration_minutes
    if payload.thumbnail_url is not None:
        course.thumbnail_url = payload.thumbnail_url
    if payload.course_metadata is not None:
        course.course_metadata = payload.course_metadata

    await db.flush()
    return build_course_response(course)


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
        .options(selectinload(Course.modules).selectinload(Module.content_items), selectinload(Course.instructor))
    )
    result = await db.execute(query)
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    course.status = "published"
    await db.flush()
    return build_course_response(course)


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
    course_exists = await db.execute(
        select(Course.id).where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
    )
    if course_exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Course not found")

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
    module = module_res.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    # Every supplied field is persisted (this handler previously dropped description,
    # text_content, duration, order and status, and never set course_id).
    content_item = ContentItem(
        org_id=tenant_ctx.org_id,
        course_id=module.course_id,
        module_id=module_id,
        title=payload.title,
        description=payload.description,
        content_type=payload.content_type.upper(),
        content_url=payload.content_url,
        text_content=payload.text_content,
        raw_text=payload.raw_text,
        transcript=payload.transcript,
        duration_seconds=payload.duration_seconds,
        order_index=payload.order_index,
        status=payload.status,
        source_type=payload.source_type,
        source_url=payload.source_url,
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
