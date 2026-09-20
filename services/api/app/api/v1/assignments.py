"""
Assignments and Practical Labs Router.
Supports creating assignments, listing assignments by module/course, submitting work, and grading using AsyncSession.
"""

from typing import List, Optional
from uuid import UUID
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.api.deps import get_db, get_current_user, get_current_tenant, require_roles, TenantContext
from app.models import Assignment, AssignmentSubmission, ContentItem, User, Module
from app.competency import service as competency_service
from app.events import store as event_store
from app.services import progress as progress_service
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentSubmissionCreate,
    AssignmentGradeRequest,
    AssignmentSubmissionResponse,
)

router = APIRouter(prefix="/assignments", tags=["Assignments & Hands-on Labs"])


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    payload: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(["instructor", "org_admin", "system_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Creates a new assignment or lab belonging to a module."""
    # Verify module exists in tenant
    res = await db.execute(
        select(Module).where(and_(Module.id == payload.module_id, Module.org_id == tenant_ctx.org_id))
    )
    module = res.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found in this organization")

    assignment = Assignment(
        id=uuid.uuid4(),
        org_id=tenant_ctx.org_id,
        course_id=payload.course_id,
        module_id=payload.module_id,
        competency_id=payload.competency_id,
        title=payload.title,
        instructions=payload.instructions,
        difficulty=payload.difficulty,
        max_score=payload.max_score,
        rubric=payload.rubric,
        status=payload.status,
    )
    db.add(assignment)
    await db.flush()
    return assignment


@router.get("", response_model=List[AssignmentResponse])
async def list_assignments(
    course_id: Optional[UUID] = Query(None),
    module_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Lists assignments filtered by course or module."""
    query = select(Assignment).where(Assignment.org_id == tenant_ctx.org_id)
    if course_id:
        query = query.where(Assignment.course_id == course_id)
    if module_id:
        query = query.where(Assignment.module_id == module_id)
    res = await db.execute(query)
    return res.scalars().all()


@router.get("/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Fetches details and rubric for a single assignment."""
    res = await db.execute(
        select(Assignment).where(and_(Assignment.id == assignment_id, Assignment.org_id == tenant_ctx.org_id))
    )
    assignment = res.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


@router.post("/{assignment_id}/submit", response_model=AssignmentSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_assignment(
    assignment_id: UUID,
    payload: AssignmentSubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Submits practical work for an assignment."""
    if payload.assignment_id is not None and payload.assignment_id != assignment_id:
        raise HTTPException(status_code=400, detail="assignment_id in the body does not match the URL")
    res = await db.execute(
        select(Assignment).where(and_(Assignment.id == assignment_id, Assignment.org_id == tenant_ctx.org_id))
    )
    assignment = res.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    submission = AssignmentSubmission(
        id=uuid.uuid4(),
        org_id=tenant_ctx.org_id,
        assignment_id=assignment_id,
        learner_id=current_user.id,
        submission_text=payload.submission_text,
        submission_url=payload.submission_url,
        status="SUBMITTED",
        rubric_scores={},
        is_ai_graded=False,
        submitted_at=datetime.utcnow(),
    )
    db.add(submission)
    await db.flush()

    await event_store.record(
        db, org_id=tenant_ctx.org_id, user_id=current_user.id, event_type="assignment_submitted",
        course_id=assignment.course_id, module_id=assignment.module_id, content_id=assignment.content_item_id,
        competency_id=assignment.competency_id, timestamp=submission.submitted_at,
        payload={"assignment_id": str(assignment.id), "submission_id": str(submission.id),
                 "has_text": bool(payload.submission_text), "has_url": bool(payload.submission_url)},
    )

    # Handing work in completes the lesson item; the grade arrives later.
    if assignment.content_item_id:
        lesson = await db.get(ContentItem, assignment.content_item_id)
        if lesson is not None and lesson.org_id == tenant_ctx.org_id:
            await progress_service.record_progress(
                db,
                org_id=tenant_ctx.org_id,
                user_id=current_user.id,
                item=lesson,
                status="completed",
                percent=100.0,
                verified=True,
                now=submission.submitted_at,
            )
    return submission


@router.get("/{assignment_id}/submissions", response_model=List[AssignmentSubmissionResponse])
async def get_assignment_submissions(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Fetches learner submissions (filtered to caller if learner; all if instructor/admin)."""
    query = select(AssignmentSubmission).where(
        and_(AssignmentSubmission.assignment_id == assignment_id, AssignmentSubmission.org_id == tenant_ctx.org_id)
    )
    if current_user.role == "learner":
        query = query.where(AssignmentSubmission.learner_id == current_user.id)
    res = await db.execute(query)
    return res.scalars().all()


@router.post("/submissions/{submission_id}/grade", response_model=AssignmentSubmissionResponse)
async def grade_submission(
    submission_id: UUID,
    payload: AssignmentGradeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(["instructor", "org_admin", "system_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Grades a learner assignment submission with rubric feedback."""
    res = await db.execute(
        select(AssignmentSubmission).where(
            and_(AssignmentSubmission.id == submission_id, AssignmentSubmission.org_id == tenant_ctx.org_id)
        )
    )
    submission = res.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.score = payload.score
    submission.feedback = payload.feedback
    submission.rubric_scores = payload.rubric_scores
    submission.is_ai_graded = payload.is_ai_graded
    submission.graded_by_id = current_user.id
    submission.graded_at = datetime.utcnow()
    submission.status = "GRADED"
    await db.flush()

    assignment = await db.get(Assignment, submission.assignment_id)
    # Evidence about the LEARNER, recorded by the grader's action. It is not part of the learner's
    # session (they are not there), so it is deliberately left without one.
    graded = await event_store.record(
        db, org_id=tenant_ctx.org_id, user_id=submission.learner_id, event_type="assignment_graded",
        course_id=assignment.course_id if assignment else None, module_id=assignment.module_id if assignment else None,
        content_id=assignment.content_item_id if assignment else None,
        competency_id=assignment.competency_id if assignment else None, attach_session=False,
        timestamp=submission.graded_at,
        payload={"assignment_id": str(submission.assignment_id), "submission_id": str(submission.id),
                 "score": payload.score, "max_score": assignment.max_score if assignment else None,
                 "graded_by": str(current_user.id), "is_ai_graded": bool(payload.is_ai_graded)},
    )

    # The grade is a signal about the competency the assignment assesses; the deterministic engine turns it into mastery.
    if assignment is not None and assignment.competency_id is not None and assignment.max_score > 0:
        await competency_service.apply(db, competency_service.EvidenceInput(
            org_id=tenant_ctx.org_id, user_id=submission.learner_id, competency_id=assignment.competency_id, source_type="assignment_graded",
            signal=min(max(payload.score / assignment.max_score, 0.0), 1.0),
            # a person's grade is trusted fully; a grade the grader marked as machine-produced is trusted a little less
            confidence=0.8 if payload.is_ai_graded else 1.0, occurred_at=submission.graded_at, source_event_id=graded.event.id,
            submission_id=submission.id, difficulty={"beginner": 0.25, "intermediate": 0.5, "advanced": 0.75}.get(assignment.difficulty),
        ))
    return submission
