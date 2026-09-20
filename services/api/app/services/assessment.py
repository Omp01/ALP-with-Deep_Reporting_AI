"""
Grading a submitted attempt, and turning graded answers into events and competency evidence.

    multiple choice   graded deterministically here (right option or not)
    written answers   graded by the grading agent into a signal (app/grading); if the agent is unavailable or its grade is not
                      trustworthy the answer waits for a person (`needs_review`) and nothing about it reaches mastery

Every graded answer becomes: an answer row, events (`question_answered`, and `answer_submitted` / `answer_graded` for written
answers), and, when the question has a competency and the answer was actually given, one piece of evidence for the
deterministic mastery update. A blank answer is not evidence of anything about the skill and is not applied.

An attempt with answers waiting for a person is `needs_review`: its score is provisional, it is not passed, the lesson is not
completed and `assessment_completed` is not recorded until the last answer is reviewed (`finalize_attempt`).
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.competency import service as competency_service
from app.core.config import settings
from app.events import evidence as event_evidence, store as event_store
from app.grading import grader
from app.models import Competency, ContentItem, GradingResult, QuestionResponse, Quiz, QuizAttempt, QuizQuestion
from app.services import progress as progress_service

WRITTEN_TYPES = {"short_answer", "open_ended"}


@dataclass
class SubmittedAnswer:
    question_id: UUID
    selected_option_id: Optional[UUID] = None
    text_response: Optional[str] = None
    response_time_ms: Optional[int] = None


@dataclass
class Outcome:
    responses: List[QuestionResponse] = field(default_factory=list)
    pending: int = 0


def is_written(question: QuizQuestion) -> bool:
    return question.question_type in WRITTEN_TYPES


async def _competency_of(db: AsyncSession, question: QuizQuestion, org_id: UUID) -> Optional[Competency]:
    if question.competency_id is None:
        return None
    competency = await db.get(Competency, question.competency_id)
    return competency if competency is not None and competency.org_id == org_id else None


async def _record_answer(
    db: AsyncSession, *, quiz: Quiz, attempt: QuizAttempt, question: QuizQuestion, response: QuestionResponse, user_id: UUID,
    org_id: UUID, signal: float, confidence: float, source_type: str, answered: bool, when: datetime, attach_session: bool = True,
    error_type: Optional[str], quote: Optional[str] = None, extra: Optional[Dict] = None, guess_floor: Optional[float] = None,
) -> None:
    """The graded answer: the `question_answered` event, and the evidence it gives about the competency."""
    recorded = await event_store.record(
        db, org_id=org_id, user_id=user_id, event_type="question_answered", course_id=quiz.course_id, module_id=quiz.module_id,
        content_id=quiz.content_item_id, assessment_id=quiz.id, question_id=question.id, competency_id=question.competency_id,
        timestamp=when, attach_session=attach_session,
        payload={
            "attempt_id": str(attempt.id), "attempt_number": attempt.attempt_number,
            "selected_option_id": str(response.selected_option_id) if response.selected_option_id else None,
            "answered": answered, "is_correct": bool(response.is_correct), "points_awarded": response.points_awarded,
            "question_type": question.question_type, "difficulty": question.difficulty, "response_time_ms": response.response_time_ms,
            "response_time_source": response.response_time_source, "error_type": response.error_type, "signal": round(signal, 4), **(extra or {}),
        },
    )
    if question.competency_id is not None and answered:
        await competency_service.apply(db, competency_service.EvidenceInput(
            org_id=org_id, user_id=user_id, competency_id=question.competency_id, source_type=source_type, signal=signal,
            confidence=confidence, occurred_at=when, source_event_id=recorded.event.id, response_id=response.id,
            session_id=recorded.event.session_id, error_type=error_type, evidence_quote=quote, difficulty=question.difficulty,
            attempt_number=attempt.attempt_number, response_time_ms=response.response_time_ms, guess_floor=guess_floor,
        ))


def _apply_grade_to_response(response: QuestionResponse, question: QuizQuestion, grade: grader.Grade, result_id: Optional[UUID]) -> None:
    response.score_fraction = grade.signal
    response.points_awarded = round(float(question.points) * grade.signal, 4)
    response.is_correct = grade.signal >= settings.grading_correct_threshold
    response.error_type = grade.error_type
    response.grading_status = "graded"
    response.grading_result_id = result_id


async def submit(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, quiz: Quiz, attempt: QuizAttempt, answers: List[SubmittedAnswer], now: datetime,
) -> Outcome:
    """Grade the answers of an attempt being submitted. The caller finalizes the attempt afterwards."""
    by_id = {q.id: q for q in quiz.questions}
    elapsed_ms = int((now - attempt.started_at).total_seconds() * 1000)
    outcome = Outcome()
    written: List[tuple] = []            # (response, question, competency, text)

    for index, answer in enumerate(answers):
        question = by_id.get(answer.question_id)
        if question is None:
            continue
        response_ms, response_source = event_evidence.response_time(answer.response_time_ms, elapsed_ms)
        response = QuestionResponse(
            id=uuid.uuid4(), attempt_id=attempt.id, question_id=question.id, selected_option_id=answer.selected_option_id,
            text_response=answer.text_response if is_written(question) else None, is_correct=False, points_awarded=0.0,
            response_time_ms=response_ms, response_time_source=response_source, grading_status="graded",
        )
        db.add(response)
        outcome.responses.append(response)
        when = now + timedelta(microseconds=index)

        if not is_written(question):
            correct = next((o for o in question.options if o.is_correct), None)
            answered = answer.selected_option_id is not None
            response.is_correct = bool(answered and correct and str(answer.selected_option_id) == str(correct.id))
            response.points_awarded = float(question.points) if response.is_correct else 0.0
            response.score_fraction = 1.0 if response.is_correct else 0.0
            response.error_type = event_evidence.error_type_for(is_correct=response.is_correct, answered=answered, question_type=question.question_type)
            await db.flush()
            options = len(question.options)
            await _record_answer(
                db, quiz=quiz, attempt=attempt, question=question, response=response, user_id=user_id, org_id=org_id,
                signal=1.0 if response.is_correct else 0.0, confidence=1.0, source_type="question_answered", answered=answered, when=when,
                error_type=response.error_type, guess_floor=(1.0 / options) if options >= 2 else None,
            )
            continue

        text = (answer.text_response or "").strip()
        await db.flush()
        await event_store.record(
            db, org_id=org_id, user_id=user_id, event_type="answer_submitted", course_id=quiz.course_id, module_id=quiz.module_id,
            content_id=quiz.content_item_id, assessment_id=quiz.id, question_id=question.id, competency_id=question.competency_id, timestamp=when,
            payload={"attempt_id": str(attempt.id), "attempt_number": attempt.attempt_number, "response_id": str(response.id), "characters": len(text)},
        )
        if not text:   # a blank written answer: worth nothing, deterministically, and not evidence of anything
            blank = grader.Grade(status="accepted", signal=0.0, confidence=1.0, error_type="unknown", evidence_quote=None, quote_verified=False,
                                 feedback="No answer was given.", rubric_scores={}, deterministic=True)
            _apply_grade_to_response(response, question, blank, None)
            await _record_answer(db, quiz=quiz, attempt=attempt, question=question, response=response, user_id=user_id, org_id=org_id, signal=0.0,
                                 confidence=1.0, source_type="answer_graded", answered=False, when=when, error_type="unknown")
            continue
        written.append((response, question, await _competency_of(db, question, org_id), text, when))

    # Written answers are graded together: the model calls overlap instead of queueing.
    prepared = []
    for response, question, competency, text, when in written:
        if competency is not None:
            prepared.append(await grader.question_for_grading(db, question, competency))
        else:
            prepared.append(grader.QuestionForGrading(question.question_text, question.expected_answer, question.rubric, "", "", None, ()))
    grades = await asyncio.gather(*[grader.grade_answer(q, item[3]) for q, item in zip(prepared, written)])

    for (response, question, competency, text, when), grade in zip(written, grades):
        result = GradingResult(
            org_id=org_id, response_id=response.id, source="ai", status=grade.status, provider=grade.provider, model=grade.model,
            prompt_version=grader.PROMPT_VERSION, correctness_signal=grade.signal, confidence=grade.confidence, error_type=grade.error_type,
            evidence_quote=grade.evidence_quote, quote_verified=grade.quote_verified, rubric_scores=grade.rubric_scores,
            feedback=grade.feedback, note=grade.reason, attempts=grade.attempts or 1, latency_ms=grade.latency_ms,
        )
        if grade.status == "accepted":
            db.add(result)
            await db.flush()
            _apply_grade_to_response(response, question, grade, result.id)
            await event_store.record(
                db, org_id=org_id, user_id=user_id, event_type="answer_graded", course_id=quiz.course_id, module_id=quiz.module_id,
                content_id=quiz.content_item_id, assessment_id=quiz.id, question_id=question.id, competency_id=question.competency_id,
                timestamp=when, payload={"attempt_id": str(attempt.id), "response_id": str(response.id), "graded_by": "ai", "signal": grade.signal,
                                         "confidence": grade.confidence, "quote_verified": grade.quote_verified, "model": grade.model},
            )
            await _record_answer(
                db, quiz=quiz, attempt=attempt, question=question, response=response, user_id=user_id, org_id=org_id, signal=grade.signal,
                confidence=grade.confidence, source_type="answer_graded", answered=True, when=when, error_type=grade.error_type,
                quote=grade.evidence_quote, extra={"graded_by": "ai", "grading_result_id": str(result.id)},
            )
        else:
            db.add(result)
            await db.flush()
            response.grading_status = "needs_review"
            response.grading_result_id = result.id
            response.points_awarded, response.score_fraction, response.is_correct = 0.0, None, False
            outcome.pending += 1
    await db.flush()
    return outcome


def totals(quiz: Quiz, responses: List[QuestionResponse]) -> tuple:
    total_possible = sum(q.points for q in quiz.questions) or 1
    earned = sum(r.points_awarded for r in responses)
    return earned, float(total_possible), round((earned / total_possible) * 100.0, 1)


async def finalize_attempt(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, quiz: Quiz, attempt: QuizAttempt, responses: List[QuestionResponse], now: datetime,
    attach_session: bool = True,
) -> None:
    """
    Score the attempt. If any answer still waits for a person the score is provisional and nothing is completed.
    Otherwise it is passed or not, the lesson is completed when passed, and `assessment_completed` is recorded.
    """
    earned, total_possible, score = totals(quiz, responses)
    pending = any(r.grading_status == "needs_review" for r in responses)
    attempt.score = score
    attempt.completed_at = attempt.completed_at or now
    if pending:
        attempt.grading_status, attempt.passed = "needs_review", False
        await db.flush()
        return

    attempt.grading_status = "graded"
    attempt.passed = score >= quiz.passing_score
    if quiz.content_item_id:
        lesson = await db.get(ContentItem, quiz.content_item_id)
        if lesson is not None and lesson.org_id == org_id:
            elapsed = int((now - attempt.started_at).total_seconds())
            await progress_service.record_progress(
                db, org_id=org_id, user_id=user_id, item=lesson, status="completed" if attempt.passed else "in_progress",
                # A failed attempt must never reach the completion threshold.
                percent=100.0 if attempt.passed else min(score, progress_service.COMPLETION_THRESHOLD - 1),
                time_spent_seconds=elapsed, verified=True, time_credit_cap=quiz.time_limit_mins * 60, now=now,
            )
    await event_store.record(
        db, org_id=org_id, user_id=user_id, event_type="assessment_completed", course_id=quiz.course_id, module_id=quiz.module_id,
        content_id=quiz.content_item_id, assessment_id=quiz.id, attach_session=attach_session,
        timestamp=now + timedelta(microseconds=len(responses) + 1),
        payload={"attempt_id": str(attempt.id), "attempt_number": attempt.attempt_number, "score": score, "passed": attempt.passed,
                 "earned_points": earned, "total_points": total_possible, "duration_seconds": int((now - attempt.started_at).total_seconds())},
    )
    await db.flush()


async def review(
    db: AsyncSession, *, org_id: UUID, reviewer_id: UUID, response: QuestionResponse, signal: float, error_type: Optional[str],
    feedback: Optional[str], now: datetime,
) -> QuizAttempt:
    """A person grades an answer that waited for review. Their grade is a signal with full confidence."""
    attempt = await db.get(QuizAttempt, response.attempt_id)
    question = await db.get(QuizQuestion, response.question_id)
    quiz = (await db.execute(select(Quiz).where(Quiz.id == attempt.quiz_id, Quiz.org_id == org_id))).scalar_one()
    await db.refresh(quiz, ["questions"])

    grade = grader.Grade(status="accepted", signal=round(signal, 4), confidence=1.0,
                         error_type=None if signal >= settings.grading_correct_threshold else (error_type or "unknown"),
                         evidence_quote=None, quote_verified=False, feedback=feedback, rubric_scores={})
    result = GradingResult(org_id=org_id, response_id=response.id, source="human", status="accepted", correctness_signal=grade.signal, confidence=1.0,
                           error_type=grade.error_type, feedback=feedback, graded_by_id=reviewer_id, prompt_version=None, attempts=1)
    db.add(result)
    await db.flush()
    _apply_grade_to_response(response, question, grade, result.id)

    learner_id = attempt.user_id
    await event_store.record(
        db, org_id=org_id, user_id=learner_id, event_type="answer_graded", course_id=quiz.course_id, module_id=quiz.module_id,
        content_id=quiz.content_item_id, assessment_id=quiz.id, question_id=question.id, competency_id=question.competency_id,
        attach_session=False, timestamp=now,
        payload={"attempt_id": str(attempt.id), "response_id": str(response.id), "graded_by": "human", "reviewer_id": str(reviewer_id),
                 "signal": grade.signal, "confidence": 1.0},
    )
    await _record_answer(
        db, quiz=quiz, attempt=attempt, question=question, response=response, user_id=learner_id, org_id=org_id, signal=grade.signal,
        confidence=1.0, source_type="answer_graded", answered=True, when=now, error_type=grade.error_type, attach_session=False,
        extra={"graded_by": "human", "grading_result_id": str(result.id)},
    )
    siblings = list((await db.execute(select(QuestionResponse).where(QuestionResponse.attempt_id == attempt.id))).scalars())
    await finalize_attempt(db, org_id=org_id, user_id=learner_id, quiz=quiz, attempt=attempt, responses=siblings, now=now, attach_session=False)
    return attempt
