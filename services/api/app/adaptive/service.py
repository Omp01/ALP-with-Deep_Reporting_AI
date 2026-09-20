"""
Adaptive decisions from stored data: gather the situation, call the pure engine (`engine.decide`), store the decision.

Every decision is one row in `adaptive_decisions` with the facts, the evidence ids, the content chosen and what else was
considered, and one `adaptive_decision_made` event, so "why did it show me this?" is answered from the stored record and a
report can cite it.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adaptive import engine
from app.events import store as event_store
from app.models import (
    AdaptiveDecision, Competency, CompetencyPrerequisite, ContentCompetency, ContentItem, ContentProgress, Course, CourseCompetency, Enrollment,
    EvidenceRecord, LearnerCompetency, Module, Quiz, QuizQuestion, User,
)

LEVELS = {"beginner": 0.25, "intermediate": 0.5, "advanced": 0.75}
LESSON_TYPES_NOT = {"QUIZ", "ASSIGNMENT"}
RECENT = 8


class AdaptiveError(Exception):
    code = "adaptive_error"
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NoCompetency(AdaptiveError):
    code = "no_competency"
    status_code = 422


def _kind(content_type: str) -> str:
    return "assessment" if content_type == "QUIZ" else "assignment" if content_type == "ASSIGNMENT" else "lesson"


async def _course_ids(db: AsyncSession, org_id: UUID, user_id: UUID, course_id: Optional[UUID]) -> List[UUID]:
    if course_id is not None:
        ok = (await db.execute(select(Course.id).where(Course.id == course_id, Course.org_id == org_id))).scalar_one_or_none()
        if ok is None:
            raise AdaptiveError("Course not found")
        return [course_id]
    return list((await db.execute(select(Enrollment.course_id).where(Enrollment.user_id == user_id, Enrollment.org_id == org_id, Enrollment.status == "active"))).scalars())


async def _candidates(db: AsyncSession, org_id: UUID, user_id: UUID, course_ids: List[UUID]) -> List[engine.Candidate]:
    """Published items of published courses in scope, with the competencies they serve, the learner's completion and a difficulty when one is known."""
    items = (await db.execute(
        select(ContentItem, Module.sequence_order).join(Module, Module.id == ContentItem.module_id).join(Course, Course.id == ContentItem.course_id)
        .where(ContentItem.org_id == org_id, ContentItem.course_id.in_(course_ids), ContentItem.status == "published", Course.status == "published")
    )).all()
    if not items:
        return []
    ids = [i.id for i, _ in items]
    mapped: Dict[UUID, set] = {}
    for item_id, comp_id in (await db.execute(select(ContentCompetency.content_item_id, ContentCompetency.competency_id).where(ContentCompetency.content_item_id.in_(ids)))).all():
        mapped.setdefault(item_id, set()).add(comp_id)
    quiz_rows = (await db.execute(
        select(Quiz.content_item_id, QuizQuestion.competency_id, func.avg(QuizQuestion.difficulty))
        .join(QuizQuestion, QuizQuestion.quiz_id == Quiz.id).where(Quiz.org_id == org_id, Quiz.content_item_id.in_(ids)).group_by(Quiz.content_item_id, QuizQuestion.competency_id)
    )).all()
    quiz_difficulty: Dict[UUID, float] = {}
    for item_id, comp_id, difficulty in quiz_rows:
        if comp_id is not None:
            mapped.setdefault(item_id, set()).add(comp_id)
        if difficulty is not None:
            quiz_difficulty[item_id] = float(difficulty)
    progress = {p.content_item_id: p for p in (await db.execute(select(ContentProgress).where(ContentProgress.user_id == user_id, ContentProgress.content_item_id.in_(ids)))).scalars()}
    out = []
    for item, module_order in sorted(items, key=lambda t: (t[1], t[0].order_index)):
        p = progress.get(item.id)
        level = ((item.analysis or {}).get("level") if isinstance(item.analysis, dict) else None)
        out.append(engine.Candidate(
            content_id=str(item.id), title=item.title, content_type=item.content_type, kind=_kind(item.content_type),
            competency_ids=[str(c) for c in mapped.get(item.id, ())], course_id=str(item.course_id),
            difficulty=quiz_difficulty.get(item.id) if item.content_type == "QUIZ" else LEVELS.get(level),
            completed=bool(p and p.status == "completed"), completed_at=p.completed_at if p else None, order=len(out),
        ))
    return out


async def _target_competency(db: AsyncSession, org_id: UUID, user_id: UUID, course_ids: List[UUID], competency_id: Optional[UUID]) -> Competency:
    if competency_id is not None:
        comp = (await db.execute(select(Competency).where(Competency.id == competency_id, Competency.org_id == org_id))).scalar_one_or_none()
        if comp is None:
            raise AdaptiveError("Competency not found")
        return comp
    # the competency of the learner's most recent evidence in scope, else the weakest assessed one, else the first one nobody has assessed
    scope = [c for c in (await db.execute(select(CourseCompetency.competency_id).where(CourseCompetency.course_id.in_(course_ids)))).scalars()]
    if not scope:
        raise NoCompetency("This course has no competencies to adapt on.")
    latest = (await db.execute(select(EvidenceRecord.competency_id).where(EvidenceRecord.user_id == user_id, EvidenceRecord.org_id == org_id, EvidenceRecord.competency_id.in_(scope))
                               .order_by(EvidenceRecord.occurred_at.desc()).limit(1))).scalar_one_or_none()
    if latest is None:
        assessed = {c for c in (await db.execute(select(LearnerCompetency.competency_id).where(LearnerCompetency.user_id == user_id, LearnerCompetency.basis == "evidence"))).scalars()}
        latest = next((c for c in scope if c not in assessed), scope[0])
    return (await db.execute(select(Competency).where(Competency.id == latest, Competency.org_id == org_id))).scalar_one()


async def _state(db: AsyncSession, org_id: UUID, user_id: UUID, comp: Competency, course_ids: List[UUID]) -> engine.State:
    row = (await db.execute(select(LearnerCompetency).where(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id, LearnerCompetency.competency_id == comp.id,
                                                            LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0))).scalar_one_or_none()
    target = (await db.execute(select(func.max(CourseCompetency.target_mastery)).where(CourseCompetency.competency_id == comp.id, CourseCompetency.course_id.in_(course_ids)))).scalar()
    st = engine.State(str(comp.id), comp.name, None, target=float(target) if target is not None else engine.DEFAULT_TARGET)
    if row is not None:
        st.mastery, st.confidence, st.trend, st.evidence_count = row.mastery_score, row.confidence_score, row.trend, row.data_points_count
    return st


async def situation_for(db: AsyncSession, org_id: UUID, user_id: UUID, course_id: Optional[UUID], competency_id: Optional[UUID]) -> engine.Situation:
    course_ids = await _course_ids(db, org_id, user_id, course_id)
    if not course_ids:
        raise NoCompetency("You are not enrolled in any course.")
    comp = await _target_competency(db, org_id, user_id, course_ids, competency_id)
    state = await _state(db, org_id, user_id, comp, course_ids)
    recent_rows = (await db.execute(select(EvidenceRecord).where(EvidenceRecord.org_id == org_id, EvidenceRecord.user_id == user_id, EvidenceRecord.competency_id == comp.id)
                                    .order_by(EvidenceRecord.occurred_at.desc(), EvidenceRecord.created_at.desc()).limit(RECENT))).scalars().all()
    recent = [engine.Evidence(str(r.id), r.signal, r.error_type, r.difficulty, r.occurred_at) for r in recent_rows]

    candidates = await _candidates(db, org_id, user_id, course_ids)
    mine = [c for c in candidates if str(comp.id) in c.competency_ids]

    edges = (await db.execute(select(CompetencyPrerequisite, Competency).join(Competency, Competency.id == CompetencyPrerequisite.prerequisite_id)
                              .where(CompetencyPrerequisite.org_id == org_id, CompetencyPrerequisite.competency_id == comp.id))).all()
    prereq_ids = [e.prerequisite_id for e, _ in edges]
    masteries = {r.competency_id: r.mastery_score for r in (await db.execute(select(LearnerCompetency).where(
        LearnerCompetency.user_id == user_id, LearnerCompetency.competency_id.in_(prereq_ids), LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0))).scalars()} if prereq_ids else {}
    prereqs = [engine.Prerequisite(str(p.id), p.name, e.min_mastery, masteries.get(p.id)) for e, p in edges]
    prereq_candidates = {str(pid): [c for c in candidates if str(pid) in c.competency_ids] for pid in prereq_ids}
    others = [c for c in candidates if str(comp.id) not in c.competency_ids and c.kind == "lesson"]

    consumed = [c for c in mine if c.kind == "lesson" and c.completed]
    last_type = max(consumed, key=lambda c: (c.completed_at or datetime.min, c.order)).content_type if consumed else None
    return engine.Situation(state, recent, prereqs, mine, prereq_candidates, others, last_type)


def _content_out(c: Optional[engine.Candidate]) -> Optional[Dict[str, Any]]:
    if c is None:
        return None
    return {"content_id": c.content_id, "title": c.title, "content_type": c.content_type, "kind": c.kind, "course_id": c.course_id, "difficulty": c.difficulty, "completed": c.completed}


def decision_payload(d: engine.Decision, decision_id: Optional[UUID] = None, created_at: Optional[datetime] = None) -> Dict[str, Any]:
    return {
        "decision_id": str(decision_id) if decision_id else None, "action": d.action, "rule": d.rule, "reason": d.reason,
        "competency": {"id": d.competency_id, "name": d.competency_name}, "content": _content_out(d.content), "note": d.note,
        "why": engine.explain(d), "facts": [{"label": f.label, "value": f.value, "evidence_ids": list(f.evidence_ids)} for f in d.facts],
        "created_at": created_at.isoformat() if created_at else None,
    }


async def next_step(db: AsyncSession, *, org_id: UUID, user: User, course_id: Optional[UUID] = None, competency_id: Optional[UUID] = None,
                    session_id: Optional[UUID] = None, trigger: str = "requested") -> Dict[str, Any]:
    situation = await situation_for(db, org_id, user.id, course_id, competency_id)
    decision = engine.decide(situation)
    now = datetime.utcnow()
    row = AdaptiveDecision(
        id=uuid.uuid4(), org_id=org_id, user_id=user.id, competency_id=UUID(decision.competency_id), decision_type=decision.action.lower(), reason=decision.reason,
        rule_applied=decision.rule, created_at=now,
        decision_metadata={
            "facts": [{"label": f.label, "value": f.value, "evidence_ids": list(f.evidence_ids)} for f in decision.facts], "content": _content_out(decision.content),
            "considered": decision.considered, "course_id": str(course_id) if course_id else None, "learning_session_id": str(session_id) if session_id else None,
            "trigger": trigger, "engine": "adaptive_v1",
        },
    )
    db.add(row)
    await db.flush()
    content_uuid = UUID(decision.content.content_id) if decision.content else None
    course_uuid = UUID(decision.content.course_id) if decision.content and decision.content.course_id else course_id
    await event_store.record(
        db, org_id=org_id, user_id=user.id, event_type="adaptive_decision_made", course_id=course_uuid, content_id=content_uuid, competency_id=UUID(decision.competency_id),
        session_id=session_id, timestamp=now, attach_session=session_id is None and course_uuid is not None,
        payload={"decision_id": str(row.id), "action": decision.action, "rule": decision.rule, "mastery": next((f.value for f in decision.facts if f.label == "mastery"), None)},
    )
    return decision_payload(decision, row.id, now)


async def history(db: AsyncSession, org_id: UUID, user_id: UUID, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(AdaptiveDecision).where(AdaptiveDecision.org_id == org_id, AdaptiveDecision.user_id == user_id,
                                                            AdaptiveDecision.decision_metadata["engine"].astext == "adaptive_v1")
                             .order_by(AdaptiveDecision.created_at.desc()).limit(limit))).scalars().all()
    names = {c.id: c.name for c in (await db.execute(select(Competency).where(Competency.id.in_([r.competency_id for r in rows if r.competency_id])))).scalars()} if rows else {}
    return [{"decision_id": str(r.id), "action": r.decision_type.upper(), "rule": r.rule_applied, "reason": r.reason, "competency": {"id": str(r.competency_id), "name": names.get(r.competency_id)},
             "content": r.decision_metadata.get("content"), "facts": r.decision_metadata.get("facts", []), "considered": r.decision_metadata.get("considered", []),
             "created_at": r.created_at.isoformat()} for r in rows]


async def get_decision(db: AsyncSession, org_id: UUID, decision_id: UUID) -> Optional[AdaptiveDecision]:
    return (await db.execute(select(AdaptiveDecision).where(AdaptiveDecision.id == decision_id, AdaptiveDecision.org_id == org_id))).scalar_one_or_none()
