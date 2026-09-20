"""
Gathers stored data for the skill-gap and risk engines (`gaps.py`, `risk.py`), which hold the rules.

Only evidence-based competency state is used (`basis == 'evidence'` with at least one piece of evidence): rows left by the earlier
engine are ignored.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.competency import gaps, risk
from app.models import (
    Competency, CompetencyPrerequisite, ContentCompetency, ContentItem, CourseCompetency, Enrollment, EvidenceRecord, LearnerCompetency,
    LearningEvent, Quiz, QuizAttempt,
)

# Events that mean the learner did something (not events the platform recorded about them).
ACTIVITY_TYPES = (
    "lesson_opened", "content_started", "content_completed", "video_started", "video_resumed", "video_progress", "article_opened",
    "assessment_started", "question_shown", "question_answered", "answer_submitted", "assignment_opened", "assignment_submitted",
)
EVIDENCE_IDS_PER_COMPETENCY = 5


async def _states(db: AsyncSession, org_id: UUID, user_id: UUID, competency_ids: Optional[Iterable[UUID]] = None):
    query = (select(LearnerCompetency, Competency).join(Competency, Competency.id == LearnerCompetency.competency_id)
             .where(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id, LearnerCompetency.basis == "evidence",
                    LearnerCompetency.data_points_count > 0))
    if competency_ids is not None:
        query = query.where(LearnerCompetency.competency_id.in_(list(competency_ids)))
    return (await db.execute(query)).all()


async def _recent_evidence(db: AsyncSession, org_id: UUID, user_id: UUID, competency_ids: Sequence[UUID]) -> Dict[UUID, List[str]]:
    if not competency_ids:
        return {}
    rows = (await db.execute(
        select(EvidenceRecord.competency_id, EvidenceRecord.id).where(
            EvidenceRecord.org_id == org_id, EvidenceRecord.user_id == user_id, EvidenceRecord.competency_id.in_(list(competency_ids)))
        .order_by(EvidenceRecord.occurred_at.desc(), EvidenceRecord.created_at.desc())
    )).all()
    out: Dict[UUID, List[str]] = defaultdict(list)
    for competency_id, evidence_id in rows:
        if len(out[competency_id]) < EVIDENCE_IDS_PER_COMPETENCY:
            out[competency_id].append(str(evidence_id))
    return out


async def _expected_seconds(db: AsyncSession, competency_ids: Sequence[UUID]) -> Dict[UUID, int]:
    if not competency_ids:
        return {}
    rows = (await db.execute(
        select(ContentCompetency.competency_id, func.coalesce(func.sum(ContentItem.duration_seconds), 0))
        .join(ContentItem, ContentItem.id == ContentCompetency.content_item_id)
        .where(ContentCompetency.competency_id.in_(list(competency_ids)), ContentItem.status == "published")
        .group_by(ContentCompetency.competency_id)
    )).all()
    return {cid: int(total or 0) for cid, total in rows}


async def _targets(db: AsyncSession, org_id: UUID, user_id: UUID, course_id: Optional[UUID]) -> Dict[UUID, float]:
    query = select(CourseCompetency.competency_id, func.max(CourseCompetency.target_mastery)).join(
        Enrollment, Enrollment.course_id == CourseCompetency.course_id).where(
        Enrollment.user_id == user_id, Enrollment.org_id == org_id, Enrollment.status == "active")
    if course_id is not None:
        query = query.where(CourseCompetency.course_id == course_id)
    return {cid: float(t) for cid, t in (await db.execute(query.group_by(CourseCompetency.competency_id))).all()}


async def _prerequisites(db: AsyncSession, org_id: UUID, user_id: UUID, competency_ids: Sequence[UUID]) -> Dict[UUID, List[gaps.Prerequisite]]:
    if not competency_ids:
        return {}
    edges = (await db.execute(
        select(CompetencyPrerequisite, Competency).join(Competency, Competency.id == CompetencyPrerequisite.prerequisite_id)
        .where(CompetencyPrerequisite.org_id == org_id, CompetencyPrerequisite.competency_id.in_(list(competency_ids))))).all()
    prereq_ids = [e.prerequisite_id for e, _ in edges]
    masteries = {s.competency_id: s.mastery_score for s, _ in await _states(db, org_id, user_id, prereq_ids)} if prereq_ids else {}
    out: Dict[UUID, List[gaps.Prerequisite]] = defaultdict(list)
    for edge, prereq in edges:
        out[edge.competency_id].append(gaps.Prerequisite(prereq.id, prereq.name, edge.min_mastery, masteries.get(prereq.id)))
    return out


async def learner_gaps(db: AsyncSession, org_id: UUID, user_id: UUID, course_id: Optional[UUID] = None) -> List[gaps.GapAssessment]:
    """Every assessed competency of the learner, judged against its target; gaps first, worst first."""
    targets = await _targets(db, org_id, user_id, course_id)
    rows = await _states(db, org_id, user_id, targets.keys() if course_id is not None else None)
    ids = [c.id for _, c in rows]
    evidence = await _recent_evidence(db, org_id, user_id, ids)
    expected = await _expected_seconds(db, ids)
    prereqs = await _prerequisites(db, org_id, user_id, ids)
    results = []
    for state, competency in rows:
        results.append(gaps.assess(gaps.GapInput(
            competency_id=competency.id, code=competency.code, name=competency.name, mastery=state.mastery_score, confidence=state.confidence_score,
            trend=state.trend, trend_delta=state.trend_delta, evidence_count=state.data_points_count, incorrect_count=state.incorrect_count,
            retry_count=state.retry_count, error_distribution=state.error_distribution or {}, time_on_task_seconds=state.time_on_task_seconds,
            target_mastery=targets.get(competency.id, gaps.DEFAULT_TARGET), expected_time_seconds=expected.get(competency.id, 0),
            prerequisites=prereqs.get(competency.id, []), evidence_ids=evidence.get(competency.id, []),
        )))
    return sorted(results, key=lambda a: (not a.is_gap, -a.points, a.mastery))


async def cohort_gaps(db: AsyncSession, org_id: UUID, user_ids: Optional[Set[UUID]], course_id: Optional[UUID] = None) -> Dict[str, Any]:
    """Team-level view: for each competency, how many assessed learners are below target (counts, never one average)."""
    query = (select(LearnerCompetency, Competency).join(Competency, Competency.id == LearnerCompetency.competency_id)
             .where(LearnerCompetency.org_id == org_id, LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0))
    if user_ids is not None:
        query = query.where(LearnerCompetency.user_id.in_(list(user_ids)))
    rows = (await db.execute(query)).all()
    target_query = select(CourseCompetency.competency_id, func.max(CourseCompetency.target_mastery)).group_by(CourseCompetency.competency_id)
    if course_id is not None:
        target_query = target_query.where(CourseCompetency.course_id == course_id)
    targets = {str(cid): float(t) for cid, t in (await db.execute(target_query)).all()}
    data = [{"competency_id": c.id, "name": c.name, "code": c.code, "user_id": s.user_id, "mastery": s.mastery_score, "trend": s.trend,
             "evidence_count": s.data_points_count} for s, c in rows]
    learners = len({d["user_id"] for d in data})
    return {"learners_with_evidence": learners, "competencies": gaps.cohort_summary(data, targets)}


async def risk_input(db: AsyncSession, org_id: UUID, user_id: UUID, course_id: UUID, now: Optional[datetime] = None) -> risk.RiskInput:
    now = now or datetime.utcnow()
    course_competencies = list((await db.execute(select(CourseCompetency.competency_id).where(CourseCompetency.course_id == course_id))).scalars())
    rows = await _states(db, org_id, user_id, course_competencies) if course_competencies else []
    ids = [c.id for _, c in rows]
    evidence = await _recent_evidence(db, org_id, user_id, ids)
    expected = await _expected_seconds(db, ids)
    prereqs = await _prerequisites(db, org_id, user_id, ids)
    facts = [
        risk.CompetencyFact(
            competency_id=str(c.id), name=c.name, mastery=s.mastery_score, confidence=s.confidence_score, trend=s.trend, trend_delta=s.trend_delta,
            evidence_count=s.data_points_count, retry_count=s.retry_count, time_on_task_seconds=s.time_on_task_seconds,
            expected_time_seconds=expected.get(c.id, 0), evidence_ids=evidence.get(c.id, []),
            blocked_by=[f"{p.name} ≥ {round(p.required_mastery * 100)}%" for p in prereqs.get(c.id, []) if p.mastery is not None and p.mastery < p.required_mastery],
        ) for s, c in rows
    ]

    failed = dict((await db.execute(
        select(Quiz.title, func.count(QuizAttempt.id)).join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(Quiz.course_id == course_id, Quiz.org_id == org_id, QuizAttempt.user_id == user_id, QuizAttempt.passed.is_(False),
               QuizAttempt.completed_at.is_not(None), QuizAttempt.grading_status == "graded").group_by(Quiz.title)
    )).all())

    last = (await db.execute(select(func.max(LearningEvent.timestamp)).where(
        LearningEvent.org_id == org_id, LearningEvent.user_id == user_id, LearningEvent.course_id == course_id,
        LearningEvent.event_type.in_(ACTIVITY_TYPES)))).scalar()
    enrolled = (await db.execute(select(Enrollment.enrolled_at).where(Enrollment.user_id == user_id, Enrollment.course_id == course_id))).scalar()
    return risk.RiskInput(
        competencies=facts, failed_attempts={k: int(v) for k, v in failed.items()},
        days_since_activity=None if last is None else max(0.0, (now - last).total_seconds() / 86400.0),
        days_enrolled=0.0 if enrolled is None else max(0.0, (now - enrolled).total_seconds() / 86400.0),
    )
