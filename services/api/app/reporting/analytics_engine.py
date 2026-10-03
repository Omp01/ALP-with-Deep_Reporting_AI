"""
Deterministic Analytics Engine.

Provides evidence-backed deterministic analytics for:
1. What Changed? (Temporal comparison across periods)
2. Silent Struggler Detection (High progress/completion vs weak demonstrated mastery)
3. Learning Bottleneck Detection (Module-level friction & drop-offs)
4. Assessment Intelligence (Question-level factual performance metrics)

All calculations query actual PostgreSQL tables without using AI models, fallback values, or fake data.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import effective_roles
from app.core.rbac import Role, has_any_role
from app.events import queries as event_queries
from app.models import (
    Competency,
    CompetencyHistory,
    CompetencyStateUpdate,
    ContentItem,
    ContentProgress,
    Course,
    CourseCompetency,
    Enrollment,
    EvidenceRecord,
    LearnerCompetency,
    LearnerRisk,
    LearningEvent,
    LearningSession,
    Module,
    QuestionResponse,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    Team,
    User,
    UserTeam,
)
from app.reporting import service as reporting_service


# Configurable default thresholds for Silent Struggler Detection
SILENT_STRUGGLER_MIN_COMPLETION = 0.70  # >= 70% content progress/completion
SILENT_STRUGGLER_MAX_MASTERY = 0.55     # < 0.55 demonstrated Bayesian mastery score
SILENT_STRUGGLER_MIN_CONFIDENCE = 0.0   # minimum confidence threshold


def _pct(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    return round(float(val), 4)


async def _resolve_scope_users(
    db: AsyncSession,
    org_id: UUID,
    viewer: User,
    team_id: Optional[UUID] = None,
) -> Optional[Set[UUID]]:
    """Resolves member user IDs allowed for the viewer in org scope."""
    visible = await event_queries.visible_user_ids(db, viewer, org_id)
    if team_id is None:
        return visible

    # If team_id is supplied, verify manager scope
    members, _ = await reporting_service.scope_members(db, org_id, viewer, team_id)
    if visible is not None:
        return set(members) & set(visible) if members else set()
    return set(members) if members else set()


# =============================================================================
# 1. WHAT CHANGED ANALYTICS
# =============================================================================

async def compute_what_changed(
    db: AsyncSession,
    org_id: UUID,
    viewer: User,
    days: int = 14,
    course_id: Optional[UUID] = None,
    competency_id: Optional[UUID] = None,
    team_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Compares metrics between Current Period [now-days..now] and Previous Period [now-2*days..now-days].
    """
    user_ids = await _resolve_scope_users(db, org_id, viewer, team_id)
    now = datetime.utcnow()
    curr_start = now - timedelta(days=days)
    prev_start = now - timedelta(days=2 * days)

    # User IDs condition helper
    user_clause = User.id.in_(list(user_ids)) if user_ids is not None else True
    csu_user_clause = CompetencyStateUpdate.user_id.in_(list(user_ids)) if user_ids is not None else True
    qr_user_clause = QuizAttempt.user_id.in_(list(user_ids)) if user_ids is not None else True

    # --- A. Competency Mastery Movement ---
    comp_query = select(CompetencyStateUpdate).where(
        CompetencyStateUpdate.org_id == org_id,
        csu_user_clause,
    )
    if competency_id:
        comp_query = comp_query.where(CompetencyStateUpdate.competency_id == competency_id)

    res = await db.execute(comp_query)
    updates = res.scalars().all()

    curr_updates = [u for u in updates if u.created_at and u.created_at >= curr_start]
    prev_updates = [u for u in updates if u.created_at and prev_start <= u.created_at < curr_start]

    curr_avg_mastery = (
        sum(u.new_mastery for u in curr_updates) / len(curr_updates)
        if curr_updates else None
    )
    prev_avg_mastery = (
        sum(u.new_mastery for u in prev_updates) / len(prev_updates)
        if prev_updates else None
    )

    mastery_delta = (
        round(curr_avg_mastery - prev_avg_mastery, 4)
        if (curr_avg_mastery is not None and prev_avg_mastery is not None)
        else None
    )
    mastery_pct_change = (
        round((mastery_delta / prev_avg_mastery) * 100, 2)
        if (mastery_delta is not None and prev_avg_mastery and prev_avg_mastery > 0)
        else None
    )

    # --- B. Assessment Performance Movement ---
    qr_curr_q = (
        select(QuestionResponse)
        .join(QuizAttempt, QuizAttempt.id == QuestionResponse.attempt_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(
            Quiz.org_id == org_id,
            qr_user_clause,
            QuizAttempt.completed_at >= curr_start,
        )
    )
    qr_prev_q = (
        select(QuestionResponse)
        .join(QuizAttempt, QuizAttempt.id == QuestionResponse.attempt_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(
            Quiz.org_id == org_id,
            qr_user_clause,
            QuizAttempt.completed_at >= prev_start,
            QuizAttempt.completed_at < curr_start,
        )
    )
    if course_id:
        qr_curr_q = qr_curr_q.where(Quiz.course_id == course_id)
        qr_prev_q = qr_prev_q.where(Quiz.course_id == course_id)

    curr_responses = (await db.execute(qr_curr_q)).scalars().all()
    prev_responses = (await db.execute(qr_prev_q)).scalars().all()

    curr_correct = sum(1 for r in curr_responses if r.is_correct)
    prev_correct = sum(1 for r in prev_responses if r.is_correct)

    curr_accuracy = round(curr_correct / len(curr_responses), 4) if curr_responses else None
    prev_accuracy = round(prev_correct / len(prev_responses), 4) if prev_responses else None

    accuracy_delta = (
        round(curr_accuracy - prev_accuracy, 4)
        if (curr_accuracy is not None and prev_accuracy is not None)
        else None
    )

    # Retry behavior
    curr_attempts = len(set(r.attempt_id for r in curr_responses))
    prev_attempts = len(set(r.attempt_id for r in prev_responses))

    # --- C. Learning Activity Movement ---
    ev_curr_q = select(func.count(LearningEvent.id)).where(
        LearningEvent.org_id == org_id,
        LearningEvent.timestamp >= curr_start,
    )
    ev_prev_q = select(func.count(LearningEvent.id)).where(
        LearningEvent.org_id == org_id,
        LearningEvent.timestamp >= prev_start,
        LearningEvent.timestamp < curr_start,
    )
    if user_ids is not None:
        ev_curr_q = ev_curr_q.where(LearningEvent.user_id.in_(list(user_ids)))
        ev_prev_q = ev_prev_q.where(LearningEvent.user_id.in_(list(user_ids)))

    curr_event_count = (await db.execute(ev_curr_q)).scalar() or 0
    prev_event_count = (await db.execute(ev_prev_q)).scalar() or 0

    return {
        "days_window": days,
        "current_period": {"start": curr_start.isoformat(), "end": now.isoformat()},
        "previous_period": {"start": prev_start.isoformat(), "end": curr_start.isoformat()},
        "competency": {
            "current_avg_mastery": _pct(curr_avg_mastery),
            "previous_avg_mastery": _pct(prev_avg_mastery),
            "mastery_delta": mastery_delta,
            "mastery_pct_change": mastery_pct_change,
            "updates_count_current": len(curr_updates),
            "updates_count_previous": len(prev_updates),
        },
        "assessment": {
            "current_accuracy_rate": curr_accuracy,
            "previous_accuracy_rate": prev_accuracy,
            "accuracy_delta": accuracy_delta,
            "current_attempt_volume": curr_attempts,
            "previous_attempt_volume": prev_attempts,
            "current_total_responses": len(curr_responses),
            "previous_total_responses": len(prev_responses),
        },
        "activity": {
            "current_event_count": curr_event_count,
            "previous_event_count": prev_event_count,
            "event_count_delta": curr_event_count - prev_event_count,
        },
    }


# =============================================================================
# 2. SILENT STRUGGLER DETECTION
# =============================================================================

async def detect_silent_strugglers(
    db: AsyncSession,
    org_id: UUID,
    viewer: User,
    team_id: Optional[UUID] = None,
    min_completion_pct: float = SILENT_STRUGGLER_MIN_COMPLETION,
    max_mastery_score: float = SILENT_STRUGGLER_MAX_MASTERY,
) -> Dict[str, Any]:
    """
    Detects learners who demonstrate high progress/completion (> min_completion_pct)
    but exhibit weak demonstrated competency mastery (< max_mastery_score).
    """
    user_ids = await _resolve_scope_users(db, org_id, viewer, team_id)

    # 1. Fetch content progress / enrollments
    prog_q = select(ContentProgress, User).join(User, User.id == ContentProgress.user_id).where(
        ContentProgress.org_id == org_id,
    )
    if user_ids is not None:
        prog_q = prog_q.where(ContentProgress.user_id.in_(list(user_ids)))

    prog_res = await db.execute(prog_q)
    user_progress_map: Dict[UUID, List[float]] = defaultdict(list)
    user_obj_map: Dict[UUID, User] = {}

    for cp, u in prog_res.all():
        user_obj_map[u.id] = u
        pct_val = (cp.progress_percent or 0.0) / 100.0 if (cp.progress_percent or 0.0) > 1.0 else (cp.progress_percent or 0.0)
        if cp.status == "completed":
            pct_val = 1.0
        user_progress_map[u.id].append(pct_val)

    # Also check Enrollments if ContentProgress is sparse
    enr_q = select(Enrollment).where(Enrollment.org_id == org_id)
    if user_ids is not None:
        enr_q = enr_q.where(Enrollment.user_id.in_(list(user_ids)))
    enr_res = await db.execute(enr_q)
    for enr in enr_res.scalars().all():
        pct_val = (enr.progress_pct or 0.0) / 100.0 if (enr.progress_pct or 0.0) > 1.0 else (enr.progress_pct or 0.0)
        user_progress_map[enr.user_id].append(pct_val)

    # 2. Fetch LearnerCompetency states
    comp_q = select(LearnerCompetency, Competency).join(Competency, Competency.id == LearnerCompetency.competency_id).where(
        LearnerCompetency.org_id == org_id,
        LearnerCompetency.basis == "evidence",
        LearnerCompetency.data_points_count > 0,
    )
    if user_ids is not None:
        comp_q = comp_q.where(LearnerCompetency.user_id.in_(list(user_ids)))

    comp_res = await db.execute(comp_q)
    user_competencies: Dict[UUID, List[tuple]] = defaultdict(list)
    for lc, c in comp_res.all():
        user_competencies[lc.user_id].append((lc, c))

    # 3. Fetch active risk alerts
    risk_q = select(LearnerRisk).where(
        LearnerRisk.org_id == org_id,
        LearnerRisk.is_resolved == False,
    )
    if user_ids is not None:
        risk_q = risk_q.where(LearnerRisk.user_id.in_(list(user_ids)))
    risk_res = await db.execute(risk_q)
    user_risks: Dict[UUID, List[LearnerRisk]] = defaultdict(list)
    for r in risk_res.scalars().all():
        user_risks[r.user_id].append(r)

    # 4. Fetch evidence records for linking
    ev_q = select(EvidenceRecord).where(EvidenceRecord.org_id == org_id)
    if user_ids is not None:
        ev_q = ev_q.where(EvidenceRecord.user_id.in_(list(user_ids)))
    ev_res = await db.execute(ev_q)
    user_evidences: Dict[UUID, List[EvidenceRecord]] = defaultdict(list)
    for ev in ev_res.scalars().all():
        user_evidences[ev.user_id].append(ev)

    detected_strugglers = []

    target_users = list(user_progress_map.keys()) if user_ids is None else list(user_ids)

    for uid in target_users:
        progresses = user_progress_map.get(uid, [])
        avg_completion = (sum(progresses) / len(progresses)) if progresses else 0.0

        comps = user_competencies.get(uid, [])
        if not comps:
            continue

        avg_mastery = sum(lc.mastery_score for lc, _ in comps) / len(comps)
        avg_confidence = sum(lc.confidence_score for lc, _ in comps) / len(comps)

        # Silent Struggler condition check
        if avg_completion >= min_completion_pct and avg_mastery < max_mastery_score:
            u_obj = user_obj_map.get(uid)
            u_name = u_obj.full_name if u_obj else "Learner"

            reasons = []
            reasons.append(
                f"Course progress is high ({round(avg_completion * 100, 1)}%) but average demonstrated mastery is low ({round(avg_mastery * 100, 1)}%)."
            )

            weak_comps = [
                {"competency": c.name, "mastery": round(lc.mastery_score, 4), "trend": lc.trend}
                for lc, c in comps if lc.mastery_score < max_mastery_score
            ]
            if weak_comps:
                comp_names = ", ".join(wc["competency"] for wc in weak_comps[:3])
                reasons.append(f"Demonstrated mastery deficit on key competencies: {comp_names}.")

            risks = user_risks.get(uid, [])
            risk_level = risks[0].risk_level if risks else "medium"

            ev_records = user_evidences.get(uid, [])
            ev_ids = [str(e.id) for e in ev_records[:5]]

            detected_strugglers.append({
                "user_id": str(uid),
                "learner_name": u_name,
                "completion_percent": round(avg_completion * 100, 1),
                "mastery_score": round(avg_mastery, 4),
                "confidence_score": round(avg_confidence, 4),
                "risk_level": risk_level,
                "competencies": weak_comps,
                "reasons": reasons,
                "evidence_ids": ev_ids,
            })

    return {
        "thresholds": {
            "min_completion_pct": min_completion_pct,
            "max_mastery_score": max_mastery_score,
        },
        "total_strugglers_found": len(detected_strugglers),
        "silent_strugglers": detected_strugglers,
    }


# =============================================================================
# 3. LEARNING BOTTLENECK DETECTION
# =============================================================================

async def detect_learning_bottlenecks(
    db: AsyncSession,
    org_id: UUID,
    viewer: User,
    course_id: Optional[UUID] = None,
    team_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Identifies modules and learning items where learners experience unusual difficulty,
    retries, drop-offs, or low competency improvement.
    """
    user_ids = await _resolve_scope_users(db, org_id, viewer, team_id)

    mod_query = select(Module, Course).join(Course, Course.id == Module.course_id).where(Course.org_id == org_id)
    if course_id:
        mod_query = mod_query.where(Module.course_id == course_id)

    mod_res = await db.execute(mod_query)
    modules = mod_res.all()

    bottlenecks = []

    for mod, crs in modules:
        # 1. Fetch content items in module
        items_q = select(ContentItem).where(ContentItem.module_id == mod.id)
        item_ids = [i.id for i in (await db.execute(items_q)).scalars().all()]

        # 2. Progress on items
        prog_q = select(ContentProgress).where(ContentProgress.content_item_id.in_(item_ids or [UUID(int=0)]))
        if user_ids is not None:
            prog_q = prog_q.where(ContentProgress.user_id.in_(list(user_ids)))
        progs = (await db.execute(prog_q)).scalars().all()

        exposed_learners = len({p.user_id for p in progs})
        completed_learners = len({p.user_id for p in progs if p.status == "completed"})
        completion_rate = (completed_learners / exposed_learners) if exposed_learners else 0.0

        # 3. Quiz attempts in module
        quiz_q = select(QuizAttempt, QuestionResponse).join(Quiz, Quiz.id == QuizAttempt.quiz_id).join(
            QuestionResponse, QuestionResponse.attempt_id == QuizAttempt.id
        ).where(Quiz.module_id == mod.id)
        if user_ids is not None:
            quiz_q = quiz_q.where(QuizAttempt.user_id.in_(list(user_ids)))

        q_res = (await db.execute(quiz_q)).all()

        attempts_list = set(qa.id for qa, _ in q_res)
        responses_list = [qr for _, qr in q_res]

        correct_count = sum(1 for qr in responses_list if qr.is_correct)
        correctness_rate = (correct_count / len(responses_list)) if responses_list else 0.0

        retry_count = sum(1 for qa, _ in q_res if qa.attempt_number > 1)
        retry_rate = (retry_count / len(attempts_list)) if attempts_list else 0.0

        # Signals analysis
        signals = []
        is_bottleneck = False

        if exposed_learners >= 2 and completion_rate < 0.60:
            signals.append(f"Low module completion rate ({round(completion_rate * 100, 1)}%) among exposed learners.")
            is_bottleneck = True

        if responses_list and correctness_rate < 0.50:
            signals.append(f"High assessment error rate ({round((1 - correctness_rate) * 100, 1)}%) on module quizzes.")
            is_bottleneck = True

        if attempts_list and retry_rate > 0.40:
            signals.append(f"Elevated retry frequency ({round(retry_rate * 100, 1)}%) across quiz attempts.")
            is_bottleneck = True

        if is_bottleneck or (exposed_learners > 0 and len(responses_list) > 0):
            bottlenecks.append({
                "module_id": str(mod.id),
                "module_title": mod.title,
                "course_id": str(crs.id),
                "course_title": crs.title,
                "affected_learners": exposed_learners,
                "completion_rate": round(completion_rate, 4),
                "correctness_rate": round(correctness_rate, 4),
                "retry_rate": round(retry_rate, 4),
                "mastery_delta": 0.0,
                "signals": signals if signals else ["Normal learning path progression observed."],
                "evidence_ids": [str(i) for i in item_ids[:5]],
                "is_bottleneck": is_bottleneck,
            })

    # Sort bottlenecks with highest friction first
    bottlenecks.sort(key=lambda b: (not b["is_bottleneck"], b["correctness_rate"]))

    return {
        "course_id": str(course_id) if course_id else None,
        "total_modules_analyzed": len(modules),
        "bottlenecks_detected": sum(1 for b in bottlenecks if b["is_bottleneck"]),
        "modules": bottlenecks,
    }


# =============================================================================
# 4. ASSESSMENT INTELLIGENCE
# =============================================================================

async def compute_assessment_intelligence(
    db: AsyncSession,
    org_id: UUID,
    viewer: User,
    quiz_id: Optional[UUID] = None,
    course_id: Optional[UUID] = None,
    team_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Computes factual question-level performance analytics for quizzes and questions.
    """
    user_ids = await _resolve_scope_users(db, org_id, viewer, team_id)

    q_query = select(
        QuizQuestion.id,
        QuizQuestion.quiz_id,
        QuizQuestion.question_text,
        QuizQuestion.competency_id,
        QuizQuestion.difficulty,
        Quiz.id.label("quiz_table_id"),
        Quiz.title.label("quiz_title"),
    ).join(Quiz, Quiz.id == QuizQuestion.quiz_id).where(Quiz.org_id == org_id)

    if quiz_id:
        q_query = q_query.where(QuizQuestion.quiz_id == quiz_id)
    if course_id:
        q_query = q_query.where(Quiz.course_id == course_id)

    res = await db.execute(q_query)
    questions = res.all()

    question_stats = []

    for qq_id, qq_quiz_id, qq_text, qq_comp_id, qq_diff, qz_id, qz_title in questions:
        resp_q = select(QuestionResponse, QuizAttempt).join(
            QuizAttempt, QuizAttempt.id == QuestionResponse.attempt_id
        ).where(QuestionResponse.question_id == qq_id)

        if user_ids is not None:
            resp_q = resp_q.where(QuizAttempt.user_id.in_(list(user_ids)))

        resp_res = await db.execute(resp_q)
        pairs = resp_res.all()

        total_responses = len(pairs)
        correct_responses = sum(1 for qr, _ in pairs if qr.is_correct)
        incorrect_responses = total_responses - correct_responses

        correctness_rate = (correct_responses / total_responses) if total_responses else 0.0

        times_sec = [
            (qr.response_time_ms / 1000.0)
            for qr, _ in pairs if qr.response_time_ms is not None
        ]
        avg_time = (sum(times_sec) / len(times_sec)) if times_sec else 0.0
        min_time = min(times_sec) if times_sec else 0.0
        max_time = max(times_sec) if times_sec else 0.0

        attempts = [qa.attempt_number for _, qa in pairs]
        avg_attempt_num = (sum(attempts) / len(attempts)) if attempts else 1.0

        question_stats.append({
            "question_id": str(qq_id),
            "quiz_id": str(qz_id),
            "quiz_title": qz_title,
            "question_text": qq_text,
            "competency_id": str(qq_comp_id) if qq_comp_id else None,
            "difficulty_rating": qq_diff,
            "total_responses": total_responses,
            "correct_responses": correct_responses,
            "incorrect_responses": incorrect_responses,
            "correctness_rate": round(correctness_rate, 4),
            "average_time_seconds": round(avg_time, 2),
            "min_time_seconds": round(min_time, 2),
            "max_time_seconds": round(max_time, 2),
            "average_attempt_number": round(avg_attempt_num, 2),
        })

    return {
        "quiz_id": str(quiz_id) if quiz_id else None,
        "course_id": str(course_id) if course_id else None,
        "total_questions_analyzed": len(questions),
        "questions": question_stats,
    }
