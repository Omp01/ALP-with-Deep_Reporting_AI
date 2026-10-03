"""
Psychometrics API Router.

Endpoints for:
- In-course micro-prompt delivery with survey fatigue cooldown.
- Submitting psychometric ratings (storing raw and normalized scores).
- Learner metacognitive calibration report (Confidence-Performance Gap, LEI, and 7-stage trajectory).
- Manager course effectiveness and content friction analytics.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    effective_roles,
    get_current_tenant,
    get_current_user,
    get_db,
)
from app.core.rbac import Role, has_any_role
from app.events import queries as event_queries
from app.models.user import User
from app.schemas.psychometrics import (
    LearnerCalibrationReport,
    ManagerPsychometricsEffectivenessReport,
    PsychometricQuestionSchema,
    PsychometricResponseReceipt,
    PsychometricResponseSubmit,
)
from app.services import psychometrics_service

router = APIRouter(prefix="/psychometrics", tags=["Psychometrics & Learning Analytics"])

_MANAGER_ROLES = [Role.MANAGER, Role.LD_ADMIN, Role.ORG_ADMIN, Role.SUPER_ADMIN]


@router.get("/prompt", response_model=Optional[PsychometricQuestionSchema])
async def get_active_psychometric_prompt(
    stage: str = Query("during_course", description="before_course, during_course, after_topic, after_video, after_assessment, end_of_module, end_of_course"),
    course_id: Optional[UUID] = Query(None, description="Course context"),
    content_item_id: Optional[UUID] = Query(None, description="Content item / lesson context"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Fetches an active, non-intrusive psychometric question for the current learning milestone.
    Automatically throttled by cooldown rules so the learner is never spammed.
    """
    return await psychometrics_service.get_active_prompt_for_learner(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=current_user.id,
        course_id=course_id,
        content_item_id=content_item_id,
        stage=stage,
    )


@router.post("/response", response_model=PsychometricResponseReceipt)
async def submit_psychometric_response(
    payload: PsychometricResponseSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Submits a learner's psychometric rating:
    - Stores both raw rating and normalized score (respecting reverse-keying).
    - Pairs with current objective performance to compute calibration gap.
    - Records longitudinal snapshot in LearnerTopicProgression.
    """
    try:
        return await psychometrics_service.record_learner_response(
            db=db,
            org_id=tenant_ctx.org_id,
            user_id=current_user.id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit response: {str(exc)}",
        )


@router.get("/learner/calibration", response_model=LearnerCalibrationReport)
async def get_learner_calibration(
    user_id: Optional[UUID] = Query(None, description="Learner ID to inspect. Defaults to self."),
    course_id: Optional[UUID] = Query(None, description="Optional course scope filter."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Returns the learner's Confidence vs Performance Calibration analysis:
    - Overall Confidence-Performance Gap and Quadrant (Calibrated Mastery, Blind Spot, Underestimated, Struggle).
    - Learning Evidence Index (LEI) composite score and weights snapshot.
    - 7-stage longitudinal learning journey trajectory.
    - Actionable, growth-oriented neutral study guidance.
    """
    target_user_id = user_id or current_user.id

    if target_user_id != current_user.id:
        visible = await event_queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
        if visible is not None and target_user_id not in visible:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this learner's calibration report.",
            )

    return await psychometrics_service.get_learner_calibration_report(
        db=db,
        org_id=tenant_ctx.org_id,
        user_id=target_user_id,
        course_id=course_id,
    )


@router.get("/manager/effectiveness", response_model=ManagerPsychometricsEffectivenessReport)
async def get_manager_effectiveness(
    course_id: Optional[UUID] = Query(None, description="Optional course scope filter."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Returns course-level effectiveness analytics for authorized managers & admins:
    - High-friction topic alerts (high difficulty + low confidence + low quiz performance).
    - Cohort calibration distribution across team members.
    - Actionable instructional recommendations.
    """
    held_roles = effective_roles(current_user)
    if not has_any_role(held_roles, _MANAGER_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Manager or Admin role required.",
        )

    return await psychometrics_service.get_manager_effectiveness_report(
        db=db,
        org_id=tenant_ctx.org_id,
        viewer=current_user,
        course_id=course_id,
    )
