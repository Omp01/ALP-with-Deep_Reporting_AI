"""
Applying evidence to competency state, and explaining and verifying the result.

`apply()` is the only writer of competency mastery. It:

  1. stores the evidence (immutable) with the deterministic inputs the update used,
  2. runs the pure update in `bkt.py`,
  3. stores the update: previous mastery, new mastery, signal, weight, parameters (immutable),
  4. refreshes the state (counts, recent accuracy, error distribution, trend, time on task),
  5. records a `competency_updated` event.

It is idempotent per (source event, competency) and serialised per learner and competency with a row lock, so the same
answer arriving twice, or two answers at once, cannot corrupt the chain.

What is NOT evidence of mastery: watching or reading. Completing a lesson says the learner was exposed to the material,
not that they can use it, so lessons feed `time_on_task` but never move mastery. Only graded answers and graded work do.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.competency import bkt
from app.core.config import settings
from app.events import store as event_store
from app.models import (
    Assignment, AssignmentSubmission, Competency, CompetencyStateUpdate, ContentCompetency, ContentProgress, EvidenceRecord,
    CourseCompetency, Enrollment, LearnerCompetency, QuestionResponse, Quiz, QuizQuestion,
)

logger = logging.getLogger("api.competency")

CORRECT_AT = 0.5   # a signal at or above this counts as a correct answer in the counts (the update itself uses the signal)


def params_from_settings() -> bkt.MasteryParams:
    return bkt.MasteryParams(
        prior=settings.mastery_prior, learn=settings.mastery_learn, slip=settings.mastery_slip, guess=settings.mastery_guess,
        retry_weight=settings.mastery_retry_weight, confidence_k=settings.mastery_confidence_k,
        trend_window=settings.mastery_trend_window, trend_min_updates=settings.mastery_trend_min_updates,
        trend_threshold=settings.mastery_trend_threshold,
    )


class EvidenceRejected(ValueError):
    pass


@dataclass
class EvidenceInput:
    org_id: UUID
    user_id: UUID
    competency_id: UUID
    source_type: str                      # question_answered | assignment_graded | answer_graded | seed_history
    signal: float
    confidence: float = 1.0
    occurred_at: Optional[datetime] = None
    source_event_id: Optional[UUID] = None
    response_id: Optional[UUID] = None
    submission_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    error_type: Optional[str] = None
    evidence_quote: Optional[str] = None
    difficulty: Optional[float] = None
    attempt_number: Optional[int] = None
    response_time_ms: Optional[int] = None
    guess_floor: Optional[float] = None


@dataclass
class Applied:
    evidence: EvidenceRecord
    update: CompetencyStateUpdate
    state: LearnerCompetency
    created: bool        # False when this evidence had already been applied


async def _lock_state(db: AsyncSession, org_id: UUID, user_id: UUID, competency_id: UUID) -> LearnerCompetency:
    query = (select(LearnerCompetency)
             .where(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id, LearnerCompetency.competency_id == competency_id)
             .with_for_update())
    state = (await db.execute(query)).scalar_one_or_none()
    if state is not None:
        return state
    fresh = LearnerCompetency(org_id=org_id, user_id=user_id, competency_id=competency_id, mastery_score=0.0, confidence_score=0.0,
                              data_points_count=0, status="novice", basis="evidence")
    try:
        async with db.begin_nested():
            db.add(fresh)
            await db.flush()
    except IntegrityError:  # a concurrent request created it first
        if fresh in db:
            db.expunge(fresh)
        return (await db.execute(query)).scalar_one()
    return (await db.execute(query)).scalar_one()


async def _time_on_task(db: AsyncSession, user_id: UUID, competency_id: UUID) -> int:
    total = (await db.execute(
        select(func.coalesce(func.sum(ContentProgress.time_spent_seconds), 0))
        .join(ContentCompetency, ContentCompetency.content_item_id == ContentProgress.content_item_id)
        .where(ContentProgress.user_id == user_id, ContentCompetency.competency_id == competency_id)
    )).scalar()
    return int(total or 0)


async def apply(db: AsyncSession, evidence: EvidenceInput, *, emit_event: bool = True) -> Applied:
    """Apply one piece of evidence to the learner's state for its competency."""
    competency = await db.get(Competency, evidence.competency_id)
    if competency is None or competency.org_id != evidence.org_id:
        raise EvidenceRejected("The competency does not exist in this organisation.")
    if not 0.0 <= evidence.signal <= 1.0 or not 0.0 <= evidence.confidence <= 1.0:
        raise EvidenceRejected("Signal and confidence must be between 0 and 1.")

    params = params_from_settings()
    state = await _lock_state(db, evidence.org_id, evidence.user_id, evidence.competency_id)   # serialises writers

    if evidence.source_event_id is not None:   # idempotent: checked after the lock, so concurrent duplicates see each other
        existing = (await db.execute(select(EvidenceRecord).where(
            EvidenceRecord.source_event_id == evidence.source_event_id, EvidenceRecord.competency_id == evidence.competency_id))).scalar_one_or_none()
        if existing is not None:
            done = (await db.execute(select(CompetencyStateUpdate).where(CompetencyStateUpdate.evidence_id == existing.id))).scalar_one()
            return Applied(existing, done, state, created=False)

    now = evidence.occurred_at or datetime.utcnow()
    note: Optional[str] = None
    first = state.data_points_count == 0
    if state.basis == "legacy_unverified":
        note = f"Replaced an unverified figure ({state.mastery_score:.2f}) from an earlier version with no evidence behind it."
        state.basis, first = "evidence", True
        state.effective_evidence, state.data_points_count = 0.0, 0
        state.correct_count = state.incorrect_count = state.retry_count = 0
        state.error_distribution, state.recent_accuracy = {}, None
    previous = None if first else state.mastery_score

    result = bkt.update(
        previous, 0.0 if first else state.effective_evidence,
        bkt.Evidence(signal=evidence.signal, confidence=evidence.confidence, difficulty=evidence.difficulty,
                     attempt_number=evidence.attempt_number, guess_floor=evidence.guess_floor),
        params,
    )

    record = EvidenceRecord(
        org_id=evidence.org_id, user_id=evidence.user_id, competency_id=evidence.competency_id, source_type=evidence.source_type,
        source_event_id=evidence.source_event_id, response_id=evidence.response_id, submission_id=evidence.submission_id,
        session_id=evidence.session_id, signal=evidence.signal, confidence=evidence.confidence, error_type=evidence.error_type,
        evidence_quote=evidence.evidence_quote, difficulty=evidence.difficulty, attempt_number=evidence.attempt_number,
        response_time_ms=evidence.response_time_ms, guess_floor=evidence.guess_floor, occurred_at=now,
    )
    db.add(record)
    await db.flush()

    sequence = state.data_points_count + 1
    step = CompetencyStateUpdate(
        org_id=evidence.org_id, user_id=evidence.user_id, competency_id=evidence.competency_id, state_id=state.id, evidence_id=record.id,
        sequence=sequence, previous_mastery=result.previous_mastery, new_mastery=result.new_mastery,
        previous_confidence=result.previous_confidence, new_confidence=result.new_confidence, signal=evidence.signal,
        weight=result.weight, method=bkt.METHOD,
        params={**result.params, "slip_adjusted": result.slip, "guess_adjusted": result.guess, "posterior": result.posterior}, note=note,
    )
    db.add(step)
    await db.flush()

    # ---- refresh the state from what is stored
    recent = (await db.execute(
        select(EvidenceRecord.signal, EvidenceRecord.confidence, EvidenceRecord.attempt_number)
        .where(EvidenceRecord.org_id == evidence.org_id, EvidenceRecord.user_id == evidence.user_id, EvidenceRecord.competency_id == evidence.competency_id)
        .order_by(EvidenceRecord.occurred_at.desc(), EvidenceRecord.created_at.desc()).limit(10)
    )).all()
    weights = [(s, bkt.evidence_weight(params, bkt.Evidence(signal=s, confidence=c, attempt_number=a))) for s, c, a in recent]
    history = (await db.execute(
        select(CompetencyStateUpdate.new_mastery).where(CompetencyStateUpdate.state_id == state.id).order_by(CompetencyStateUpdate.sequence)
    )).scalars().all()
    trend, delta = bkt.trend_of(history, params)

    distribution: Dict[str, int] = dict(state.error_distribution or {})
    if evidence.error_type:
        distribution[evidence.error_type] = distribution.get(evidence.error_type, 0) + 1

    state.mastery_score, state.confidence_score = result.new_mastery, result.new_confidence
    state.effective_evidence, state.data_points_count = result.effective_evidence, sequence
    state.status = bkt.status_of(result.new_mastery)
    state.correct_count += 1 if evidence.signal >= CORRECT_AT else 0
    state.incorrect_count += 0 if evidence.signal >= CORRECT_AT else 1
    state.retry_count += 1 if (evidence.attempt_number or 1) > 1 else 0
    state.recent_accuracy = bkt.recent_accuracy(weights)
    state.error_distribution = distribution
    state.trend, state.trend_delta = trend, delta
    state.time_on_task_seconds = await _time_on_task(db, evidence.user_id, evidence.competency_id)
    state.last_evidence_id, state.last_update_id = record.id, step.id
    state.last_assessed_at = state.updated_at = now
    await db.flush()

    if emit_event:
        await event_store.record(
            db, org_id=evidence.org_id, user_id=evidence.user_id, event_type="competency_updated", competency_id=evidence.competency_id,
            session_id=evidence.session_id, timestamp=now, attach_session=False,
            payload={"update_id": str(step.id), "evidence_id": str(record.id), "previous_mastery": result.previous_mastery,
                     "new_mastery": result.new_mastery, "signal": evidence.signal, "weight": result.weight, "trend": trend, "method": bkt.METHOD},
        )
    return Applied(record, step, state, created=True)


# ------------------------------------------------------------------------------------- reading
def state_out(state: LearnerCompetency, competency: Competency, target: Optional[float] = None) -> Dict[str, Any]:
    return {
        "competency_id": str(competency.id), "code": competency.code, "name": competency.name, "domain": competency.domain,
        "mastery": round(state.mastery_score, 4), "confidence": round(state.confidence_score, 4), "status": state.status,
        "evidence_count": state.data_points_count, "correct": state.correct_count, "incorrect": state.incorrect_count,
        "retries": state.retry_count, "recent_accuracy": state.recent_accuracy, "time_on_task_seconds": state.time_on_task_seconds,
        "error_distribution": state.error_distribution or {}, "trend": state.trend, "trend_delta": state.trend_delta,
        "last_updated": state.last_assessed_at.isoformat() if state.last_assessed_at else None,
        "last_evidence_id": str(state.last_evidence_id) if state.last_evidence_id else None, "target_mastery": target,
    }


async def list_states(db: AsyncSession, org_id: UUID, user_id: UUID) -> List[Dict[str, Any]]:
    """The learner's evidence-based state per competency, with the target of the courses they are enrolled in (when there is one)."""
    rows = (await db.execute(
        select(LearnerCompetency, Competency).join(Competency, Competency.id == LearnerCompetency.competency_id)
        .where(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id, LearnerCompetency.basis == "evidence",
               LearnerCompetency.data_points_count > 0)
        .order_by(Competency.name)
    )).all()
    targets = {cid: float(t) for cid, t in (await db.execute(
        select(CourseCompetency.competency_id, func.max(CourseCompetency.target_mastery))
        .join(Enrollment, Enrollment.course_id == CourseCompetency.course_id)
        .where(Enrollment.user_id == user_id, Enrollment.org_id == org_id, Enrollment.status == "active")
        .group_by(CourseCompetency.competency_id)
    )).all()}
    return [state_out(s, c, targets.get(c.id)) for s, c in rows]


async def _source_of(db: AsyncSession, record: EvidenceRecord) -> Dict[str, Any]:
    """A short, factual description of where a piece of evidence came from."""
    if record.response_id:
        row = (await db.execute(
            select(QuestionResponse, QuizQuestion, Quiz).join(QuizQuestion, QuizQuestion.id == QuestionResponse.question_id)
            .join(Quiz, Quiz.id == QuizQuestion.quiz_id).where(QuestionResponse.id == record.response_id))).first()
        if row:
            response, question, quiz = row
            return {"kind": "answer", "question_id": str(question.id), "question": question.question_text, "quiz_id": str(quiz.id),
                    "quiz": quiz.title, "response_id": str(response.id), "question_type": question.question_type}
    if record.submission_id:
        row = (await db.execute(
            select(AssignmentSubmission, Assignment).join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
            .where(AssignmentSubmission.id == record.submission_id))).first()
        if row:
            submission, assignment = row
            return {"kind": "assignment", "assignment_id": str(assignment.id), "title": assignment.title, "submission_id": str(submission.id)}
    return {"kind": record.source_type}


def describe_step(step: CompetencyStateUpdate, record: EvidenceRecord, source: Dict[str, Any]) -> str:
    """One sentence for a link in the chain. Every number in it is read from the stored rows."""
    before = "started from the prior (no earlier evidence)" if step.previous_mastery is None else f"{step.previous_mastery:.2f}"
    what = {"answer": f"Answer to \"{source.get('question', 'a question')}\"", "assignment": f"Assignment \"{source.get('title', '')}\""}.get(
        source.get("kind", ""), record.source_type.replace("_", " ").capitalize())
    bits = [f"signal {record.signal:.2f}"]
    if record.confidence < 1.0:
        bits.append(f"grader confidence {record.confidence:.2f}")
    if (record.attempt_number or 1) > 1:
        bits.append(f"attempt {record.attempt_number} (weight {step.weight:.2f})")
    if record.difficulty is not None:
        bits.append(f"difficulty {record.difficulty:.2f}")
    return f"{what}: {', '.join(bits)}. Mastery {before} → {step.new_mastery:.2f}."


async def explain(db: AsyncSession, org_id: UUID, user_id: UUID, competency_id: UUID) -> Optional[Dict[str, Any]]:
    """The evidence chain behind the current mastery: previous -> evidence -> new, in order, each step traceable."""
    row = (await db.execute(
        select(LearnerCompetency, Competency).join(Competency, Competency.id == LearnerCompetency.competency_id)
        .where(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id, LearnerCompetency.competency_id == competency_id,
               LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0))).first()
    if row is None:
        return None
    state, competency = row
    steps = (await db.execute(
        select(CompetencyStateUpdate, EvidenceRecord).join(EvidenceRecord, EvidenceRecord.id == CompetencyStateUpdate.evidence_id)
        .where(CompetencyStateUpdate.state_id == state.id).order_by(CompetencyStateUpdate.sequence))).all()
    chain = []
    for step, record in steps:
        source = await _source_of(db, record)
        chain.append({
            "sequence": step.sequence, "update_id": str(step.id), "evidence_id": str(record.id), "source_event_id": str(record.source_event_id) if record.source_event_id else None,
            "source": source, "source_type": record.source_type, "signal": record.signal, "confidence": record.confidence, "weight": step.weight,
            "error_type": record.error_type, "evidence_quote": record.evidence_quote, "difficulty": record.difficulty, "attempt_number": record.attempt_number,
            "previous_mastery": step.previous_mastery, "new_mastery": step.new_mastery, "new_confidence": step.new_confidence,
            "occurred_at": record.occurred_at.isoformat(), "method": step.method, "note": step.note, "summary": describe_step(step, record, source),
        })
    verification = await verify(db, org_id, user_id, competency_id)
    return {"state": state_out(state, competency), "chain": chain, "method": bkt.METHOD, "parameters": steps[-1][0].params if steps else None,
            "verified": verification["consistent"]}


async def verify(db: AsyncSession, org_id: UUID, user_id: UUID, competency_id: UUID) -> Dict[str, Any]:
    """
    Recompute the chain from the stored evidence with the stored parameters and compare with what was stored.
    A mismatch means a figure was not produced by the deterministic function; it should never happen.
    """
    state = (await db.execute(select(LearnerCompetency).where(
        LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id, LearnerCompetency.competency_id == competency_id))).scalar_one_or_none()
    if state is None:
        return {"consistent": True, "steps": 0, "mismatches": []}
    rows = (await db.execute(
        select(CompetencyStateUpdate, EvidenceRecord).join(EvidenceRecord, EvidenceRecord.id == CompetencyStateUpdate.evidence_id)
        .where(CompetencyStateUpdate.state_id == state.id).order_by(CompetencyStateUpdate.sequence))).all()
    mismatches: List[Dict[str, Any]] = []
    mastery: Optional[float] = None
    effective = 0.0
    for step, record in rows:
        keys = bkt.MasteryParams.__dataclass_fields__.keys()
        params = bkt.MasteryParams(**{k: v for k, v in step.params.items() if k in keys})
        expected = bkt.update(mastery, effective, bkt.Evidence(
            signal=record.signal, confidence=record.confidence, difficulty=record.difficulty, attempt_number=record.attempt_number,
            guess_floor=record.guess_floor), params)
        if abs(expected.new_mastery - step.new_mastery) > 1e-6 or (step.previous_mastery is None) != (expected.previous_mastery is None) \
                or (step.previous_mastery is not None and abs(step.previous_mastery - expected.previous_mastery) > 1e-6):
            mismatches.append({"sequence": step.sequence, "stored": step.new_mastery, "recomputed": expected.new_mastery})
        mastery, effective = expected.new_mastery, expected.effective_evidence
    if rows and state.basis == "evidence" and abs((mastery or 0) - state.mastery_score) > 1e-6:
        mismatches.append({"sequence": "state", "stored": state.mastery_score, "recomputed": mastery})
    return {"consistent": not mismatches, "steps": len(rows), "mismatches": mismatches}
