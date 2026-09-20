"""
Learner experience API: course overview, player payload, media files, and home.

Authors (L&D admins, org admins) may preview unpublished courses and items; every
other role sees published content only. All lookups are tenant-scoped and a
resource in another tenant is indistinguishable from a missing one (404).
"""

import mimetypes
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, effective_roles, get_current_tenant, get_current_user
from app.core.database import get_db
from app.core.rbac import has_any_role
from app.core.storage import storage_client
from app.models import ContentItem, User
from app.schemas.learning import CourseOverview, LearnerHome, PlayerPayload
from app.services import learning_views
from app.services.progress import PUBLISHED

router = APIRouter(prefix="/learning", tags=["Learner Experience"])

_AUTHOR_ROLES = ["ld_admin", "org_admin"]


def _is_author(user: User) -> bool:
    return has_any_role(effective_roles(user), _AUTHOR_ROLES)


@router.get("/home", response_model=LearnerHome)
async def learner_home(
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Everything the learner home shows: continue, recommendations, competencies, activity, insight."""
    return await learning_views.build_home(db, org_id=tenant_ctx.org_id, user=current_user)


@router.get("/courses/{course_id}", response_model=CourseOverview)
async def course_overview(
    course_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Course detail and outline: objectives, competencies, prerequisites, modules, and the learner's progress."""
    try:
        return await learning_views.build_overview(
            db, org_id=tenant_ctx.org_id, user=current_user, course_id=course_id, is_author=_is_author(current_user)
        )
    except learning_views.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/content/{content_id}", response_model=PlayerPayload)
async def player_payload(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """One lesson item with how to present it, the learner's progress on it, and previous/next."""
    try:
        return await learning_views.build_player(
            db, org_id=tenant_ctx.org_id, user=current_user, item_id=content_id, is_author=_is_author(current_user)
        )
    except learning_views.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/content/{content_id}/file")
async def content_file(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Stream an uploaded file (PDF, video, audio) after checking tenant and visibility."""
    item = (
        await db.execute(
            select(ContentItem).where(and_(ContentItem.id == content_id, ContentItem.org_id == tenant_ctx.org_id))
        )
    ).scalar_one_or_none()
    if item is None or item.source_type != "upload" or not item.content_url:
        raise HTTPException(status_code=404, detail="File not found")
    if item.status != PUBLISHED and not _is_author(current_user):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        data = await storage_client.download_file(item.content_url)
    except Exception:
        raise HTTPException(status_code=502, detail="The stored file could not be retrieved")

    filename = item.content_url.rsplit("/", 1)[-1]
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{filename}"', "X-Content-Type-Options": "nosniff"},
    )
