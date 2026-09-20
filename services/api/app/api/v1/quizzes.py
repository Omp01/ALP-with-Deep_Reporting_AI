"""
Quizzes, Assessments, and Automated Grading Router.
Provides quiz inspection, question delivery, attempt lifecycle, and auto-grading with telemetry streaming.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_current_user, get_current_tenant, TenantContext
from app.events import evidence, store as event_store
from app.models import (
    GradingResult,
    Quiz,
    QuizQuestion,
    QuizOption,
    QuizAttempt,
    QuestionResponse,
    ContentProgress,
    ContentItem,
    Enrollment,
    Course,
    Module,
    User,
)
from app.schemas.quiz import (
    QuizResponse,
    QuizDetailResponse,
    QuizQuestionResponse,
    QuizOptionResponse,
    QuizAttemptResponse,
    QuizSubmitRequest,
    QuestionGradedResponse,
    LearnerQuizSummary,
)
from app.services import assessment, progress as progress_service

router = APIRouter(prefix="/quizzes", tags=["Assessments & Quizzes"])


# -----------------------------------------------------------------------------
# 1. Learner Quiz Summary Dashboard
# -----------------------------------------------------------------------------
@router.get("/learner/summary", response_model=List[LearnerQuizSummary])
async def get_learner_quizzes_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Returns all quizzes across courses the learner is enrolled in,
    along with attempts count, best score, pass status, and recency.
    """
    # 1. Get courses user is enrolled in
    enrolled_query = select(Enrollment.course_id).where(
        and_(
            Enrollment.user_id == current_user.id,
            Enrollment.org_id == tenant_ctx.org_id,
        )
    )
    enrolled_res = await db.execute(enrolled_query)
    enrolled_course_ids = [row[0] for row in enrolled_res.all()]

    if not enrolled_course_ids:
        # If not enrolled in any, fetch quizzes from published courses in organization
        pub_courses = await db.execute(
            select(Course.id).where(
                and_(Course.org_id == tenant_ctx.org_id, Course.status == "published")
            )
        )
        enrolled_course_ids = [row[0] for row in pub_courses.all()]

    if not enrolled_course_ids:
        return []

    # 2. Fetch quizzes in these courses with questions
    quizzes_query = (
        select(Quiz)
        .options(
            selectinload(Quiz.course),
            selectinload(Quiz.module),
            selectinload(Quiz.questions),
        )
        .where(
            and_(
                Quiz.org_id == tenant_ctx.org_id,
                Quiz.course_id.in_(enrolled_course_ids),
            )
        )
        .order_by(Quiz.created_at.desc())
    )
    quizzes_res = await db.execute(quizzes_query)
    quizzes = quizzes_res.scalars().all()

    # 3. Fetch all attempts by this user for these quizzes
    quiz_ids = [q.id for q in quizzes]
    attempts_map: Dict[UUID, List[QuizAttempt]] = {qid: [] for qid in quiz_ids}
    if quiz_ids:
        attempts_res = await db.execute(
            select(QuizAttempt)
            .where(
                and_(
                    QuizAttempt.user_id == current_user.id,
                    QuizAttempt.quiz_id.in_(quiz_ids),
                )
            )
            .order_by(QuizAttempt.started_at.desc())
        )
        for att in attempts_res.scalars().all():
            attempts_map[att.quiz_id].append(att)

    summary_list = []
    for q in quizzes:
        atts = attempts_map.get(q.id, [])
        # An attempt still waiting for a person to grade a written answer has only a provisional score: it is not a result.
        completed_atts = [a for a in atts if a.completed_at is not None and a.grading_status == "graded"]
        best_score = max((a.score for a in completed_atts), default=None)
        has_passed = any(a.passed for a in completed_atts)
        last_at = atts[0].completed_at or atts[0].started_at if atts else None

        summary_list.append(
            LearnerQuizSummary(
                quiz_id=q.id,
                content_item_id=q.content_item_id,
                course_id=q.course_id,
                course_title=q.course.title if q.course else "Unknown Course",
                module_id=q.module_id,
                module_title=q.module.title if q.module else None,
                title=q.title,
                passing_score=q.passing_score,
                time_limit_mins=q.time_limit_mins,
                questions_count=len(q.questions),
                is_adaptive=q.is_adaptive,
                attempts_count=len(atts),
                best_score=best_score,
                passed=has_passed,
                last_attempt_at=last_at,
            )
        )

    return summary_list


# -----------------------------------------------------------------------------
# 2. Quiz Metadata
# -----------------------------------------------------------------------------
@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Fetches quiz metadata including question count and total points."""
    res = await db.execute(
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .where(and_(Quiz.id == quiz_id, Quiz.org_id == tenant_ctx.org_id))
    )
    quiz = res.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    total_points = sum(q.points for q in quiz.questions)
    return QuizResponse(
        id=quiz.id,
        org_id=quiz.org_id,
        course_id=quiz.course_id,
        module_id=quiz.module_id,
        title=quiz.title,
        description=quiz.description,
        time_limit_mins=quiz.time_limit_mins,
        passing_score=quiz.passing_score,
        max_attempts=quiz.max_attempts,
        is_adaptive=quiz.is_adaptive,
        questions_count=len(quiz.questions),
        total_points=total_points,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
    )


# -----------------------------------------------------------------------------
# 3. Quiz Questions with Unrevealed Options
# -----------------------------------------------------------------------------
@router.get("/{quiz_id}/questions", response_model=List[QuizQuestionResponse])
async def get_quiz_questions(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Returns the ordered questions and options for a quiz.
    Options have 'is_correct' hidden to prevent client inspection before submission.
    """
    res = await db.execute(
        select(Quiz)
        .options(
            selectinload(Quiz.questions).selectinload(QuizQuestion.options)
        )
        .where(and_(Quiz.id == quiz_id, Quiz.org_id == tenant_ctx.org_id))
    )
    quiz = res.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    response_questions = []
    for q in sorted(quiz.questions, key=lambda item: item.order_index):
        safe_options = [
            QuizOptionResponse(
                id=opt.id,
                question_id=opt.question_id,
                option_text=opt.option_text,
                order_index=opt.order_index,
                is_correct=None,  # Conceal during quiz runner
                explanation=None,
            )
            for opt in sorted(q.options, key=lambda o: o.order_index)
        ]
        response_questions.append(
            QuizQuestionResponse(
                id=q.id,
                quiz_id=q.quiz_id,
                competency_id=q.competency_id,
                question_text=q.question_text,
                question_type=q.question_type,
                points=q.points,
                order_index=q.order_index,
                explanation=None,  # Conceal until post-grading
                rubric=[{"criterion": r.get("criterion"), "description": r.get("description")} for r in (q.rubric or [])] or None,
                options=safe_options,
            )
        )

    return response_questions


# -----------------------------------------------------------------------------
# 4. Start Quiz Attempt
# -----------------------------------------------------------------------------
@router.post("/{quiz_id}/attempts", response_model=QuizAttemptResponse, status_code=status.HTTP_201_CREATED)
async def start_quiz_attempt(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Starts a new quiz attempt for the current learner.
    Enforces max_attempts limit and emits an ASSESSMENT_STARTED telemetry event.
    """
    res = await db.execute(
        select(Quiz).where(and_(Quiz.id == quiz_id, Quiz.org_id == tenant_ctx.org_id))
    )
    quiz = res.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    # Count existing attempts
    attempts_res = await db.execute(
        select(func.count(QuizAttempt.id)).where(
            and_(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.user_id == current_user.id,
            )
        )
    )
    existing_count = attempts_res.scalar() or 0
    if existing_count >= quiz.max_attempts:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum attempts ({quiz.max_attempts}) reached for this assessment.",
        )

    attempt_id = uuid.uuid4()
    new_attempt = QuizAttempt(
        id=attempt_id,
        quiz_id=quiz_id,
        user_id=current_user.id,
        score=0.0,
        passed=False,
        attempt_number=existing_count + 1,
        started_at=datetime.utcnow(),
    )
    db.add(new_attempt)

    await db.flush()  # the attempt exists before events refer to it

    refs = dict(
        org_id=tenant_ctx.org_id, user_id=current_user.id, course_id=quiz.course_id, module_id=quiz.module_id,
        content_id=quiz.content_item_id, assessment_id=quiz.id,
    )
    attempt_payload = {"attempt_id": str(attempt_id), "attempt_number": existing_count + 1, "title": quiz.title}
    await event_store.record(db, event_type="assessment_started", payload=attempt_payload, timestamp=new_attempt.started_at, **refs)
    if existing_count >= 1:
        previous = (await db.execute(
            select(QuizAttempt.id).where(and_(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == current_user.id, QuizAttempt.id != attempt_id))
            .order_by(QuizAttempt.attempt_number.desc()).limit(1)
        )).scalar_one_or_none()
        await event_store.record(
            db, event_type="retry_started", timestamp=new_attempt.started_at + timedelta(microseconds=1), **refs,
            payload={**attempt_payload, "previous_attempt_id": str(previous) if previous else None},
        )

    return QuizAttemptResponse(
        id=new_attempt.id,
        quiz_id=new_attempt.quiz_id,
        user_id=new_attempt.user_id,
        score=new_attempt.score,
        passed=new_attempt.passed,
        attempt_number=new_attempt.attempt_number,
        started_at=new_attempt.started_at,
        completed_at=None,
        responses=[],
    )


# -----------------------------------------------------------------------------
# 5. Submit Quiz Attempt & Auto-Grade
# -----------------------------------------------------------------------------
@router.post("/{quiz_id}/attempts/{attempt_id}/submit", response_model=QuizAttemptResponse)
async def submit_quiz_attempt(
    quiz_id: UUID,
    attempt_id: UUID,
    payload: QuizSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Evaluates submitted responses, grades score, creates QuestionResponse records,
    marks ContentProgress complete, and emits ASSESSMENT_COMPLETED telemetry.
    """
    # 1. Fetch Attempt
    att_res = await db.execute(
        select(QuizAttempt).where(
            and_(
                QuizAttempt.id == attempt_id,
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.user_id == current_user.id,
            )
        )
    )
    attempt = att_res.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=404, detail="Quiz attempt not found")
    if attempt.completed_at is not None:
        raise HTTPException(status_code=400, detail="This attempt has already been submitted and graded.")

    # 2. Fetch Quiz with Questions and Options
    quiz_res = await db.execute(
        select(Quiz)
        .options(
            selectinload(Quiz.questions).selectinload(QuizQuestion.options)
        )
        .where(and_(Quiz.id == quiz_id, Quiz.org_id == tenant_ctx.org_id))
    )
    quiz = quiz_res.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    now = datetime.utcnow()

    # 3. Grade: multiple choice deterministically, written answers by the grading agent (or wait for a person)
    outcome = await assessment.submit(
        db, org_id=tenant_ctx.org_id, user_id=current_user.id, quiz=quiz, attempt=attempt, now=now,
        answers=[assessment.SubmittedAnswer(r.question_id, r.selected_option_id, r.text_response, r.response_time_ms) for r in payload.responses],
    )

    # 4. Score, pass or not, complete the lesson this quiz is presented as, record the result: all deferred while
    #    any written answer waits for a person
    await assessment.finalize_attempt(db, org_id=tenant_ctx.org_id, user_id=current_user.id, quiz=quiz, attempt=attempt,
                                      responses=outcome.responses, now=now)

    return await _attempt_out(db, quiz, attempt, outcome.responses)


async def _attempt_out(db: AsyncSession, quiz: Quiz, attempt: QuizAttempt, responses: List[QuestionResponse]) -> QuizAttemptResponse:
    """The attempt as the learner sees it: each answer with its result and, for written answers, who graded it and why."""
    by_id: Dict[UUID, QuizQuestion] = {q.id: q for q in quiz.questions}
    results = {}
    ids = [r.grading_result_id for r in responses if r.grading_result_id]
    if ids:
        results = {g.id: g for g in (await db.execute(select(GradingResult).where(GradingResult.id.in_(ids)))).scalars()}
    graded: List[QuestionGradedResponse] = []
    for r in responses:
        question = by_id.get(r.question_id)
        if question is None:
            continue
        written = assessment.is_written(question)
        correct = next((o for o in question.options if o.is_correct), None)
        result = results.get(r.grading_result_id) if r.grading_result_id else None
        shows_answer = r.grading_status == "graded"
        graded.append(QuestionGradedResponse(
            question_id=question.id, selected_option_id=r.selected_option_id, is_correct=r.is_correct, points_awarded=r.points_awarded,
            correct_option_id=correct.id if correct and not written else None,
            explanation=(question.explanation or (correct.explanation if correct else None)) if shows_answer else None,
            question_type=question.question_type, grading_status=r.grading_status, score_fraction=r.score_fraction,
            graded_by=result.source if result and result.status == "accepted" else None,
            feedback=result.feedback if result and result.status == "accepted" else None,
        ))
    return QuizAttemptResponse(
        id=attempt.id, quiz_id=attempt.quiz_id, user_id=attempt.user_id, score=attempt.score, passed=attempt.passed,
        attempt_number=attempt.attempt_number, started_at=attempt.started_at, completed_at=attempt.completed_at,
        grading_status=attempt.grading_status, responses=graded,
    )


# -----------------------------------------------------------------------------
# 6. List User Attempts for a Quiz
# -----------------------------------------------------------------------------
@router.get("/{quiz_id}/attempts", response_model=List[QuizAttemptResponse])
async def get_quiz_attempts(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Returns all previous attempts and scores for the current user."""
    res = await db.execute(
        select(QuizAttempt)
        .options(selectinload(QuizAttempt.responses))
        .where(
            and_(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.user_id == current_user.id,
            )
        )
        .order_by(QuizAttempt.started_at.desc())
    )
    attempts = res.scalars().all()
    if not attempts:
        return []
    quiz = (await db.execute(
        select(Quiz).options(selectinload(Quiz.questions).selectinload(QuizQuestion.options)).where(Quiz.id == quiz_id, Quiz.org_id == tenant_ctx.org_id)
    )).scalar_one_or_none()
    if quiz is None:
        return []
    return [await _attempt_out(db, quiz, att, list(att.responses)) for att in attempts]
