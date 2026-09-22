"""
Video Learning API Router.

Provides endpoints for interactive video learning:
- Checkpoints fetching and AI generation from transcripts.
- Immediate flash-card answering and validation.
- Anti-skipping seek validation.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_current_user, TenantContext
from app.core.database import get_db
from app.models.user import User
from app.schemas.video_checkpoint import (
    VideoCheckpointAnswerRequest,
    VideoCheckpointAnswerResponse,
    VideoCheckpointsResponse,
    VideoCheckpointStatusUpdateRequest,
    VideoSeekValidationRequest,
    VideoSeekValidationResponse,
)
from app.services import video_checkpoints as checkpoint_service

router = APIRouter(prefix="/learning/video", tags=["Interactive Video Learning"])


@router.get("/{content_item_id}/checkpoints", response_model=VideoCheckpointsResponse)
async def get_video_checkpoints(
    content_item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Fetch all interactive checkpoints for a video lesson item, including the learner's
    current completion status. Generates checkpoints on demand if none exist.
    """
    try:
        return await checkpoint_service.get_or_create_checkpoints_for_content(
            db=db,
            org_id=tenant_ctx.org_id,
            content_item_id=content_item_id,
            user_id=current_user.id,
            force_regenerate=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load video checkpoints: {str(exc)}",
        )


@router.post("/{content_item_id}/checkpoints/generate", response_model=VideoCheckpointsResponse)
async def regenerate_video_checkpoints(
    content_item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Force AI regeneration of interactive checkpoints from the video transcript.
    """
    try:
        return await checkpoint_service.get_or_create_checkpoints_for_content(
            db=db,
            org_id=tenant_ctx.org_id,
            content_item_id=content_item_id,
            user_id=current_user.id,
            force_regenerate=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate video checkpoints: {str(exc)}",
        )


@router.post("/{content_item_id}/checkpoints/{checkpoint_id}/status")
async def update_checkpoint_status(
    content_item_id: UUID,
    checkpoint_id: UUID,
    payload: VideoCheckpointStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Mark checkpoint status (e.g. 'displayed' when the flash-card appears).
    """
    await checkpoint_service.update_checkpoint_status(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        content_item_id=content_item_id,
        checkpoint_id=checkpoint_id,
        status=payload.status,
    )
    return {"status": "ok"}


@router.post(
    "/{content_item_id}/checkpoints/{checkpoint_id}/answer",
    response_model=VideoCheckpointAnswerResponse,
)
async def submit_checkpoint_answer(
    content_item_id: UUID,
    checkpoint_id: UUID,
    payload: VideoCheckpointAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Submit learner's answer choice for a video checkpoint.
    Returns whether the answer is correct, explanation, and updated completion state.
    """
    try:
        return await checkpoint_service.record_checkpoint_answer(
            db=db,
            org_id=tenant_ctx.org_id,
            user_id=current_user.id,
            content_item_id=content_item_id,
            checkpoint_id=checkpoint_id,
            selected_option_id=payload.selected_option_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit answer: {str(exc)}",
        )


@router.post("/{content_item_id}/validate-seek", response_model=VideoSeekValidationResponse)
async def validate_seek(
    content_item_id: UUID,
    payload: VideoSeekValidationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Validates a jump in video playback. If forward skipping bypasses uncompleted checkpoints,
    the seek is blocked and returns the first missed checkpoint.
    """
    return await checkpoint_service.validate_seek(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        content_item_id=content_item_id,
        current_time=payload.current_time,
        target_time=payload.target_time,
    )
