"""
Review of written answers the grading agent could not grade with enough trust.

A written answer waits here (`needs_review`) when the AI was unavailable, answered with something unusable, graded a different
skill, could not support its grade with a quote from the answer, or was not confident enough. Nothing about such an answer
reaches mastery until a person grades it. The person's grade is a signal with full confidence; the deterministic engine turns
it into mastery like any other evidence.

    GET  /grading/queue                    answers waiting for review (L&D and organisation admins)
    GET  /grading/responses/{id}           one answer with its question, rubric, expected answer and the AI's suggestion
    POST /grading/responses/{id}/review    grade it
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, get_db, log_audit_action, require_roles
from app.events.evidence import ERROR_TYPES
from app.models import Competency, GradingResult, QuestionResponse, Quiz, QuizAttempt, QuizQuestion, User
from app.services import assessment

router = APIRouter(prefix="/grading", tags=["Written-answer grading"])

_REVIEWERS = ["ld_admin", "org_admin"]


class Review(BaseModel):
    signal: float = Field(..., ge=0, le=1, description="0 = no evidence of the skill, 1 = complete and correct")
    error_type: Optional[str] = Field(None, description="Only for answers that are not fully correct")
    feedback: Optional[str] = Field(None, max_length=1000, description="Shown to the learner")


async def _load(db: AsyncSession, org_id: UUID, response_id: UUID):
    row = (await db.execute(
        select(QuestionResponse, QuizQuestion, Quiz, QuizAttempt, User)
        .join(QuizQuestion, QuizQuestion.id == QuestionResponse.question_id).join(Quiz, Quiz.id == QuizQuestion.quiz_id)
        .join(QuizAttempt, QuizAttempt.id == QuestionResponse.attempt_id).join(User, User.id == QuizAttempt.user_id)
        .where(QuestionResponse.id == response_id, Quiz.org_id == org_id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    return row


async def _out(db: AsyncSession, row) -> Dict[str, Any]:
    response, question, quiz, attempt, learner = row
    suggestion = None
    if response.grading_result_id:
        g = await db.get(GradingResult, response.grading_result_id)
        if g is not None:
            suggestion = {"source": g.source, "status": g.status, "signal": g.correctness_signal, "confidence": g.confidence, "error_type": g.error_type,
                          "evidence_quote": g.evidence_quote, "quote_verified": g.quote_verified, "feedback": g.feedback, "why_review": g.note,
                          "provider": g.provider, "model": g.model}
    competency = await db.get(Competency, question.competency_id) if question.competency_id else None
    return {
        "response_id": str(response.id), "attempt_id": str(attempt.id), "attempt_number": attempt.attempt_number, "quiz": quiz.title,
        "course_id": str(quiz.course_id), "learner": {"id": str(learner.id), "name": learner.full_name},
        "question": question.question_text, "question_type": question.question_type, "points": question.points,
        "expected_answer": question.expected_answer, "rubric": question.rubric or [],
        "competency": {"id": str(competency.id), "name": competency.name} if competency else None,
        "answer": response.text_response, "grading_status": response.grading_status,
        "score_fraction": response.score_fraction, "ai_suggestion": suggestion,
        "submitted_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
    }


@router.get("/queue")
async def queue(
    course_id: Optional[UUID] = None, limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_roles(_REVIEWERS)), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    query = (select(QuestionResponse, QuizQuestion, Quiz, QuizAttempt, User)
             .join(QuizQuestion, QuizQuestion.id == QuestionResponse.question_id).join(Quiz, Quiz.id == QuizQuestion.quiz_id)
             .join(QuizAttempt, QuizAttempt.id == QuestionResponse.attempt_id).join(User, User.id == QuizAttempt.user_id)
             .where(Quiz.org_id == tenant_ctx.org_id, QuestionResponse.grading_status == "needs_review")
             .order_by(QuizAttempt.completed_at.asc()).limit(limit))
    if course_id:
        query = query.where(Quiz.course_id == course_id)
    rows = (await db.execute(query)).all()
    return {"items": [await _out(db, r) for r in rows]}


@router.get("/responses/{response_id}")
async def response_detail(
    response_id: UUID, current_user: User = Depends(require_roles(_REVIEWERS)), tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    return await _out(db, await _load(db, tenant_ctx.org_id, response_id))


@router.post("/responses/{response_id}/review")
async def review_response(
    response_id: UUID, payload: Review, current_user: User = Depends(require_roles(_REVIEWERS)),
    tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    row = await _load(db, tenant_ctx.org_id, response_id)
    response = row[0]
    if response.grading_status != "needs_review":
        raise HTTPException(status_code=409, detail={"code": "not_waiting", "message": "This answer is not waiting for review."})
    if payload.error_type and payload.error_type not in ERROR_TYPES:
        raise HTTPException(status_code=422, detail={"code": "invalid_error_type", "message": f"error_type must be one of: {', '.join(ERROR_TYPES)}"})

    attempt = await assessment.review(
        db, org_id=tenant_ctx.org_id, reviewer_id=current_user.id, response=response, signal=payload.signal,
        error_type=payload.error_type, feedback=(payload.feedback or "").strip() or None, now=datetime.utcnow(),
    )
    await log_audit_action(db, tenant_ctx.org_id, current_user.id, "ANSWER_REVIEWED", "QUESTION_RESPONSE", str(response.id),
                           {"signal": payload.signal, "attempt_status": attempt.grading_status})
    return {"response_id": str(response.id), "attempt_id": str(attempt.id), "attempt_grading_status": attempt.grading_status,
            "attempt_score": attempt.score, "attempt_passed": attempt.passed}
