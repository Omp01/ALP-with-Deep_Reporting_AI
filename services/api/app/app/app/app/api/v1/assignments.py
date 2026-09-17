"""
Assignments and Practical Labs Router.
Supports creating assignments, listing assignments by module/course, submitting work, and grading.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, get_current_tenant, require_roles, TenantContext
from app.models import Assignment, AssignmentSubmission, User, Module
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentSubmissionCreate,
    AssignmentGradeRequest,
    AssignmentSubmissionResponse,
)

router = APIRouter(prefix="/assignments", tags=["Assignments & Hands-on Labs"])


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["instructor", "org_admin", "system_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Creates a new assignment or lab belonging to a module."""
    # Verify module exists in tenant
    module = db.query(Module).filter_by(id=payload.module_id, org_id=tenant_ctx.org_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found in this organization")

    assignment = Assignment(
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
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("", response_model=List[AssignmentResponse])
def list_assignments(
    course_id: Optional[UUID] = Query(None),
    module_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Lists assignments filtered by course or module."""
    q = db.query(Assignment).filter(Assignment.org_id == tenant_ctx.org_id)
    if course_id:
        q = q.filter(Assignment.course_id == course_id)
    if module_id:
        q = q.filter(Assignment.module_id == module_id)
    return q.all()


@router.get("/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Fetches details and rubric for a single assignment."""
    assignment = db.query(Assignment).filter_by(id=assignment_id, org_id=tenant_ctx.org_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


@router.post("/{assignment_id}/submit", response_model=AssignmentSubmissionResponse, status_code=status.HTTP_201_CREATED)
def submit_assignment(
    assignment_id: UUID,
    payload: AssignmentSubmissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Submits practical work for an assignment."""
    assignment = db.query(Assignment).filter_by(id=assignment_id, org_id=tenant_ctx.org_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    submission = AssignmentSubmission(
        org_id=tenant_ctx.org_id,
        assignment_id=assignment_id,
        learner_id=current_user.id,
        submission_text=payload.submission_text,
        submission_url=payload.submission_url,
        status="SUBMITTED",
        submitted_at=datetime.utcnow(),
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{assignment_id}/submissions", response_model=List[AssignmentSubmissionResponse])
def get_assignment_submissions(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Fetches learner submissions (filtered to caller if learner; all if instructor/admin)."""
    q = db.query(AssignmentSubmission).filter_by(assignment_id=assignment_id, org_id=tenant_ctx.org_id)
    if current_user.role == "learner":
        q = q.filter(AssignmentSubmission.learner_id == current_user.id)
    return q.all()


@router.post("/submissions/{submission_id}/grade", response_model=AssignmentSubmissionResponse)
def grade_submission(
    submission_id: UUID,
    payload: AssignmentGradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["instructor", "org_admin", "system_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Grades a learner assignment submission with rubric feedback."""
    submission = db.query(AssignmentSubmission).filter_by(id=submission_id, org_id=tenant_ctx.org_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.score = payload.score
    submission.feedback = payload.feedback
    submission.rubric_scores = payload.rubric_scores
    submission.is_ai_graded = payload.is_ai_graded
    submission.graded_by_id = current_user.id
    submission.graded_at = datetime.utcnow()
    submission.status = "GRADED"

    db.commit()
    db.refresh(submission)
    return submission
