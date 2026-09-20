"""
Learner content progress.

Progress is derived from `content_progress` rows (see app/services/progress.py for
the rules: server-verified completion for quizzes and assignments, clamped time).
"""

from typing import Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, get_current_user, get_db
from app.models import ContentItem, ContentProgress, Course, User
from app.schemas.progress import (
    ContentProgressResponse,
    ContentProgressUpdate,
    CourseProgressSummary,
)
from app.services import progress as progress_service

router = APIRouter(prefix="/progress", tags=["Content Progress & Completion"])


@router.post("/content/{content_item_id}", response_model=ContentProgressResponse)
async def update_content_progress(
    content_item_id: UUID,
    payload: ContentProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Record progress on a lesson item.

    Completion of videos and readings is reported by the player. Quizzes and
    assignments cannot be completed here: they complete when a passing attempt or a
    submission is recorded server-side.
    """
    item = (
        await db.execute(
            select(ContentItem).where(
                and_(ContentItem.id == content_item_id, ContentItem.org_id == tenant_ctx.org_id)
            )
        )
    ).scalar_one_or_none()
    if item is None or item.status != progress_service.PUBLISHED:
        raise HTTPException(status_code=404, detail="Content item not found")

    result = await progress_service.record_progress(
        db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        item=item,
        status=payload.status,
        percent=payload.progress_percent,
        time_spent_seconds=payload.time_spent_seconds,
        position_seconds=payload.position_seconds,
    )
    return ContentProgressResponse.model_validate(result.record)


@router.get("/course/{course_id}", response_model=CourseProgressSummary)
async def get_course_progress(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Derived progress for the current learner: totals plus a per-item map."""
    course = (
        await db.execute(
            select(Course.id).where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
        )
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    item_ids = (
        await db.execute(
            select(ContentItem.id).where(
                ContentItem.course_id == course_id,
                ContentItem.org_id == tenant_ctx.org_id,
                ContentItem.status == progress_service.PUBLISHED,
            )
        )
    ).scalars().all()

    records = []
    if item_ids:
        records = (
            await db.execute(
                select(ContentProgress).where(
                    ContentProgress.user_id == current_user.id,
                    ContentProgress.content_item_id.in_(item_ids),
                )
            )
        ).scalars().all()

    summary = (await progress_service.progress_for_courses(db, tenant_ctx.org_id, current_user.id, [course_id]))[course_id]
    items: Dict[str, ContentProgressResponse] = {
        str(r.content_item_id): ContentProgressResponse.model_validate(r) for r in records
    }
    return CourseProgressSummary(
        course_id=course_id,
        total_items=summary.total_items,
        completed_items=summary.completed_items,
        progress_percent=summary.percent,
        items_progress=items,
    )
