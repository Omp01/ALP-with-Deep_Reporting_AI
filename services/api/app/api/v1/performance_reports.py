"""
Performance Reports API Router.

Provides endpoints for:
- Learner Performance Report: Overall assessment score, first-attempt accuracy,
  attempt-decay flashcard marks, topic mastery, and question-level drill-down with
  exact calculation snapshots and video review links.
- Manager & Admin Cohort Performance Report: Aggregated cohort metrics, at-risk learners,
  cohort-wide weak topics, and individual learner inspection.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    TenantContext,
    effective_roles,
    get_current_tenant,
    get_current_user,
    get_db,
)
from app.core.rbac import Role, has_any_role
from app.events import queries as event_queries
from app.models import (
    Assignment,
    AssignmentSubmission,
    ContentItem,
    Course,
    LearnerVideoCheckpoint,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    QuestionResponse,
    Team,
    User,
    UserTeam,
    VideoCheckpoint,
    VideoCheckpointAttempt,
)
from app.schemas.performance_reports import (
    CohortWeakTopic,
    LearnerPerformanceReport,
    ManagerCohortLearnerSummary,
    ManagerCohortPerformanceReport,
    QuestionAttemptItem,
    TopicMasteryItem,
)
from app.schemas.video_checkpoint import CheckpointRemediation
from app.services.scoring import (
    calculate_overall_assessment_score,
)
from app.services import psychometrics_service

router = APIRouter(prefix="/reports", tags=["Performance Reports"])

_MANAGER_ROLES = [Role.MANAGER, Role.LD_ADMIN, Role.ORG_ADMIN, Role.SUPER_ADMIN]


@router.get("/learner/performance", response_model=LearnerPerformanceReport)
async def get_learner_performance_report(
    user_id: Optional[UUID] = Query(None, description="Learner ID to inspect. Defaults to self."),
    course_id: Optional[UUID] = Query(None, description="Optional course scope filter."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Returns explainable performance analytics for a learner:
    - Attempt-decay flashcard marks, quiz scores, and assignment scores.
    - First-attempt accuracy and retry statistics.
    - Topic-level mastery distribution.
    - Full drill-down question history with immutable mathematical formula snapshots.
    """
    target_user_id = user_id or current_user.id
    held_roles = effective_roles(current_user)

    # 1. RBAC Verification
    if target_user_id != current_user.id:
        visible = await event_queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
        if visible is not None and target_user_id not in visible:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this learner's performance report.",
            )

    # 2. Fetch target user
    u_res = await db.execute(
        select(User).where(and_(User.id == target_user_id, User.org_id == tenant_ctx.org_id))
    )
    learner = u_res.scalar_one_or_none()
    if not learner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learner not found")

    course_title: Optional[str] = None
    if course_id:
        c_res = await db.execute(
            select(Course.title).where(and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id))
        )
        course_title = c_res.scalar_one_or_none()

    # 3. Flashcards Query
    chk_stmt = (
        select(LearnerVideoCheckpoint, VideoCheckpoint, ContentItem)
        .join(VideoCheckpoint, VideoCheckpoint.id == LearnerVideoCheckpoint.checkpoint_id)
        .join(ContentItem, ContentItem.id == VideoCheckpoint.content_item_id)
        .where(
            and_(
                LearnerVideoCheckpoint.user_id == target_user_id,
                LearnerVideoCheckpoint.org_id == tenant_ctx.org_id,
                LearnerVideoCheckpoint.status.in_(["answered", "correct", "incorrect"]),
            )
        )
    )
    if course_id:
        chk_stmt = chk_stmt.where(ContentItem.course_id == course_id)

    chk_res = await db.execute(chk_stmt)
    flashcard_rows = chk_res.all()

    # 4. Quizzes Query
    quiz_stmt = (
        select(QuizAttempt, Quiz)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(
            and_(
                QuizAttempt.user_id == target_user_id,
                Quiz.org_id == tenant_ctx.org_id,
                QuizAttempt.completed_at.isnot(None),
            )
        )
    )
    if course_id:
        quiz_stmt = quiz_stmt.where(Quiz.course_id == course_id)

    quiz_res = await db.execute(quiz_stmt)
    quiz_rows = quiz_res.all()

    # Fetch Question Responses for quizzes
    quiz_attempt_ids = [att.id for att, _ in quiz_rows]
    question_responses_map: Dict[UUID, List[Tuple[QuestionResponse, QuizQuestion]]] = {}
    if quiz_attempt_ids:
        qr_stmt = (
            select(QuestionResponse, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == QuestionResponse.question_id)
            .where(QuestionResponse.attempt_id.in_(quiz_attempt_ids))
        )
        qr_res = await db.execute(qr_stmt)
        for qr, qq in qr_res.all():
            question_responses_map.setdefault(qr.attempt_id, []).append((qr, qq))

    # 5. Assignments Query
    assign_stmt = (
        select(AssignmentSubmission, Assignment)
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .where(
            and_(
                AssignmentSubmission.user_id == target_user_id,
                Assignment.org_id == tenant_ctx.org_id,
                AssignmentSubmission.score.isnot(None),
            )
        )
    )
    if course_id:
        assign_stmt = assign_stmt.where(Assignment.course_id == course_id)

    assign_res = await db.execute(assign_stmt)
    assignment_rows = assign_res.all()

    # 6. Aggregate Scores & Metrics
    attempt_items: List[QuestionAttemptItem] = []
    topic_data: Dict[str, Dict[str, Any]] = {}
    total_attempts_sum = 0
    total_items_count = 0
    first_attempt_correct_count = 0
    chronological_scores: List[float] = []

    # Process Flashcards
    flashcard_scores_pct = []
    for l_chk, chk, ci in flashcard_rows:
        total_items_count += 1
        eff_attempts = max(1, l_chk.attempt_count)
        total_attempts_sum += eff_attempts
        
        max_m = float(chk.max_score or 10.0)
        awarded_m = float(l_chk.score or 0.0)
        pct = (awarded_m / max_m) * 100.0 if max_m > 0 else 0.0
        flashcard_scores_pct.append(pct)
        chronological_scores.append(pct)

        first_correct = (eff_attempts == 1 and l_chk.status == "correct")
        if first_correct:
            first_attempt_correct_count += 1

        topic_name = chk.topic or "Video Flashcard Concepts"
        t_entry = topic_data.setdefault(topic_name, {"total": 0, "correct": 0, "attempts": 0, "score_pcts": []})
        t_entry["total"] += 1
        t_entry["attempts"] += eff_attempts
        t_entry["score_pcts"].append(pct)
        if l_chk.status == "correct":
            t_entry["correct"] += 1

        start_sec = chk.timestamp_start_seconds if chk.timestamp_start_seconds is not None else max(0.0, chk.timestamp_seconds - 45.0)
        end_sec = chk.timestamp_end_seconds if chk.timestamp_end_seconds is not None else chk.timestamp_seconds
        start_fmt = f"{int(start_sec // 60):02d}:{int(start_sec % 60):02d}"
        end_fmt = f"{int(end_sec // 60):02d}:{int(end_sec % 60):02d}"

        remediation = CheckpointRemediation(
            topic=topic_name,
            video_title=ci.title,
            content_item_id=ci.id,
            timestamp_start_seconds=start_sec,
            timestamp_end_seconds=end_sec,
            section_label=f"{start_fmt} - {end_fmt}",
            explanation=chk.explanation,
            action_url=f"/learner/learning?item_id={ci.id}&start={int(start_sec)}",
        )

        attempt_items.append(
            QuestionAttemptItem(
                id=chk.id,
                title=chk.question[:120],
                assessment_type="flashcard",
                topic=topic_name,
                attempts=eff_attempts,
                first_attempt_correct=first_correct,
                score=round(awarded_m, 2),
                max_score=round(max_m, 2),
                status=l_chk.status,
                answered_at=l_chk.answered_at or l_chk.updated_at,
                calculation_details=l_chk.calculation_details,
                remediation=remediation,
            )
        )

    # Process Quizzes
    quiz_scores_pct = []
    for att, qz in quiz_rows:
        quiz_scores_pct.append(float(att.score))
        chronological_scores.append(float(att.score))
        q_responses = question_responses_map.get(att.id, [])
        for qr, qq in q_responses:
            total_items_count += 1
            eff_attempts = max(1, att.attempt_number)
            total_attempts_sum += eff_attempts
            
            first_correct = (eff_attempts == 1 and qr.is_correct)
            if first_correct:
                first_attempt_correct_count += 1

            topic_name = qq.topic or f"{qz.title} - Question"
            t_entry = topic_data.setdefault(topic_name, {"total": 0, "correct": 0, "attempts": 0, "score_pcts": []})
            t_entry["total"] += 1
            t_entry["attempts"] += eff_attempts
            pts_max = float(qq.points or 1.0)
            pts_awarded = float(qr.points_awarded or 0.0)
            q_pct = (pts_awarded / pts_max) * 100.0 if pts_max > 0 else 0.0
            t_entry["score_pcts"].append(q_pct)
            if qr.is_correct:
                t_entry["correct"] += 1

            remediation = None
            if not qr.is_correct and (qq.source_content_item_id or qq.topic):
                s_sec = qq.source_timestamp_seconds or 0.0
                remediation = CheckpointRemediation(
                    topic=topic_name,
                    video_title="Recommended Lesson Review",
                    content_item_id=qq.source_content_item_id or qz.id,
                    timestamp_start_seconds=s_sec,
                    timestamp_end_seconds=s_sec + 45.0,
                    section_label=f"{int(s_sec // 60):02d}:{int(s_sec % 60):02d}",
                    explanation=qq.explanation,
                    action_url=f"/learner/learning?item_id={qq.source_content_item_id}&start={int(s_sec)}" if qq.source_content_item_id else None,
                )

            calc_details = {
                "formula_id": "quiz_objective_v1",
                "formula_version": "1.0.0",
                "points_awarded": pts_awarded,
                "max_marks": pts_max,
                "attempt_number": eff_attempts,
                "reason": f"Points: {pts_awarded:.1f} / {pts_max:.1f} on quiz '{qz.title}'.",
            }

            attempt_items.append(
                QuestionAttemptItem(
                    id=qq.id,
                    title=qq.question_text[:120],
                    assessment_type="quiz",
                    topic=topic_name,
                    attempts=eff_attempts,
                    first_attempt_correct=first_correct,
                    score=round(pts_awarded, 2),
                    max_score=round(pts_max, 2),
                    status="correct" if qr.is_correct else "incorrect",
                    answered_at=att.completed_at,
                    calculation_details=calc_details,
                    remediation=remediation,
                )
            )

    # Process Assignments
    assignment_scores_pct = []
    for sub, assign in assignment_rows:
        total_items_count += 1
        total_attempts_sum += 1
        max_m = float(assign.max_score or 100.0)
        awarded_m = float(sub.score or 0.0)
        pct = (awarded_m / max_m) * 100.0 if max_m > 0 else 0.0
        assignment_scores_pct.append(pct)
        chronological_scores.append(pct)

        if pct >= 70.0:
            first_attempt_correct_count += 1

        calc_details = {
            "formula_id": "assignment_rubric_v1",
            "formula_version": "1.0.0",
            "marks_awarded": awarded_m,
            "max_marks": max_m,
            "reason": f"Graded assignment '{assign.title}': {awarded_m:.1f}/{max_m:.1f}.",
        }

        attempt_items.append(
            QuestionAttemptItem(
                id=sub.id,
                title=assign.title[:120],
                assessment_type="assignment",
                topic=assign.title,
                attempts=1,
                first_attempt_correct=pct >= 70.0,
                score=round(awarded_m, 2),
                max_score=round(max_m, 2),
                status="completed",
                answered_at=sub.submitted_at,
                calculation_details=calc_details,
                remediation=None,
            )
        )

    # Averages
    flashcard_avg = round(sum(flashcard_scores_pct) / len(flashcard_scores_pct), 2) if flashcard_scores_pct else None
    quiz_avg = round(sum(quiz_scores_pct) / len(quiz_scores_pct), 2) if quiz_scores_pct else None
    assign_avg = round(sum(assignment_scores_pct) / len(assignment_scores_pct), 2) if assignment_scores_pct else None

    overall_result = calculate_overall_assessment_score(
        quiz_avg=quiz_avg,
        assignment_avg=assign_avg,
        flashcard_avg=flashcard_avg,
    )

    first_attempt_acc = (
        round((first_attempt_correct_count / total_items_count) * 100.0, 1)
        if total_items_count > 0 else 100.0
    )
    avg_attempts = (
        round(total_attempts_sum / total_items_count, 2)
        if total_items_count > 0 else 1.0
    )
    retries_count = sum(1 for it in attempt_items if it.attempts > 1)

    # Topic Mastery List
    topic_mastery: List[TopicMasteryItem] = []
    strong_topics: List[str] = []
    weak_topics: List[str] = []

    for t_name, data in topic_data.items():
        score_list = data["score_pcts"]
        t_mastery = round(sum(score_list) / len(score_list), 1) if score_list else 0.0
        t_attempts = round(data["attempts"] / max(1, data["total"]), 2)
        
        if t_mastery >= 80.0:
            status_tag = "strong"
            strong_topics.append(t_name)
        elif t_mastery < 60.0:
            status_tag = "weak"
            weak_topics.append(t_name)
        else:
            status_tag = "developing"

        topic_mastery.append(
            TopicMasteryItem(
                topic=t_name,
                mastery_percent=t_mastery,
                total_questions=data["total"],
                correct_count=data["correct"],
                average_attempts=t_attempts,
                status=status_tag,
            )
        )

    # Sort topic mastery by mastery percent ascending so weak topics are prominent
    topic_mastery.sort(key=lambda t: t.mastery_percent)

    # Trend calculation
    trend = "stable"
    if len(chronological_scores) >= 6:
        half = len(chronological_scores) // 2
        first_half_avg = sum(chronological_scores[:half]) / half
        second_half_avg = sum(chronological_scores[half:]) / (len(chronological_scores) - half)
        if second_half_avg > first_half_avg + 4.0:
            trend = "improving"
        elif second_half_avg < first_half_avg - 4.0:
            trend = "declining"

    # Sort attempt history newest first
    attempt_items.sort(key=lambda x: x.answered_at or datetime.min, reverse=True)

    # Fetch psychometric calibration and LEI
    cal_rep = await psychometrics_service.get_learner_calibration_report(
        db, tenant_ctx.org_id, target_user_id, course_id
    )

    return LearnerPerformanceReport(
        user_id=learner.id,
        user_name=learner.full_name or learner.email,
        user_email=learner.email,
        course_id=course_id,
        course_title=course_title,
        overall_score=overall_result["overall_score"],
        quiz_score=quiz_avg,
        assignment_score=assign_avg,
        flashcard_score=flashcard_avg,
        weights_used=overall_result["weights_used"],
        first_attempt_accuracy=first_attempt_acc,
        average_attempts=avg_attempts,
        total_items_attempted=total_items_count,
        questions_requiring_retries=retries_count,
        topic_mastery=topic_mastery,
        strong_topics=strong_topics[:5],
        weak_topics=weak_topics[:5],
        improvement_trend=trend,
        attempt_history=attempt_items,
        lei_score=cal_rep.lei_score,
        lei_detail=cal_rep.lei_detail.model_dump() if cal_rep.lei_detail else None,
        confidence_score=cal_rep.average_confidence,
        confidence_gap=cal_rep.confidence_gap,
        calibration_quadrant=cal_rep.calibration_quadrant,
        neutral_recommendation=cal_rep.neutral_recommendation,
    )


@router.get("/manager/performance", response_model=ManagerCohortPerformanceReport)
async def get_manager_cohort_performance_report(
    team_id: Optional[UUID] = Query(None, description="Optional team filter."),
    course_id: Optional[UUID] = Query(None, description="Optional course filter."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Returns cohort-wide performance analytics for authorized managers and administrators:
    - Average cohort accuracy, score, and retry metrics.
    - Identification of at-risk learners requiring attention.
    - Cohort-wide repeated mistakes and weak topics.
    - Learner roster with drill-down links.
    """
    held_roles = effective_roles(current_user)
    if not has_any_role(held_roles, _MANAGER_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Manager or Admin role required.",
        )

    # 1. Determine cohort visible learners
    visible = await event_queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    user_query = select(User).where(and_(User.org_id == tenant_ctx.org_id, User.is_active == True))

    if visible is not None:
        user_query = user_query.where(User.id.in_(list(visible)))

    if team_id:
        user_query = user_query.join(UserTeam, UserTeam.user_id == User.id).where(UserTeam.team_id == team_id)

    res = await db.execute(user_query)
    cohort_users = list(res.scalars().all())

    if not cohort_users:
        return ManagerCohortPerformanceReport()

    cohort_summaries: List[ManagerCohortLearnerSummary] = []
    overall_scores: List[float] = []
    first_attempt_accs: List[float] = []
    attempts_per_item: List[float] = []
    cohort_topic_issues: Dict[str, Dict[str, Any]] = {}

    for u in cohort_users:
        # Fetch user's flashcards
        fc_stmt = (
            select(LearnerVideoCheckpoint, VideoCheckpoint)
            .join(VideoCheckpoint, VideoCheckpoint.id == LearnerVideoCheckpoint.checkpoint_id)
            .where(
                and_(
                    LearnerVideoCheckpoint.user_id == u.id,
                    LearnerVideoCheckpoint.org_id == tenant_ctx.org_id,
                    LearnerVideoCheckpoint.status.in_(["answered", "correct", "incorrect"]),
                )
            )
        )
        if course_id:
            fc_stmt = fc_stmt.join(ContentItem, ContentItem.id == VideoCheckpoint.content_item_id).where(ContentItem.course_id == course_id)

        fc_res = await db.execute(fc_stmt)
        fc_items = fc_res.all()

        # Fetch user's quizzes
        qz_stmt = (
            select(QuizAttempt)
            .where(
                and_(
                    QuizAttempt.user_id == u.id,
                    QuizAttempt.completed_at.isnot(None),
                )
            )
        )
        if course_id:
            qz_stmt = qz_stmt.join(Quiz, Quiz.id == QuizAttempt.quiz_id).where(Quiz.course_id == course_id)

        qz_res = await db.execute(qz_stmt)
        qz_items = list(qz_res.scalars().all())

        # Aggregate user metrics
        u_total_items = len(fc_items) + len(qz_items)
        u_first_correct = 0
        u_attempts_total = 0
        u_scores: List[float] = []

        for l_chk, chk in fc_items:
            eff_att = max(1, l_chk.attempt_count)
            u_attempts_total += eff_att
            max_m = float(chk.max_score or 10.0)
            score_m = float(l_chk.score or 0.0)
            pct = (score_m / max_m) * 100.0 if max_m > 0 else 0.0
            u_scores.append(pct)
            if eff_att == 1 and l_chk.status == "correct":
                u_first_correct += 1
            else:
                top = chk.topic or "Video Flashcard"
                t_info = cohort_topic_issues.setdefault(top, {"struggling_learners": set(), "attempts": [], "scores": []})
                t_info["struggling_learners"].add(u.id)
                t_info["attempts"].append(eff_att)
                t_info["scores"].append(pct)

        for q_att in qz_items:
            eff_att = max(1, q_att.attempt_number)
            u_attempts_total += eff_att
            u_scores.append(float(q_att.score))
            if eff_att == 1 and q_att.passed:
                u_first_correct += 1

        u_score_avg = round(sum(u_scores) / len(u_scores), 1) if u_scores else 0.0
        u_acc = round((u_first_correct / u_total_items) * 100.0, 1) if u_total_items > 0 else 100.0
        u_avg_att = round(u_attempts_total / u_total_items, 2) if u_total_items > 0 else 1.0

        if u_total_items > 0:
            overall_scores.append(u_score_avg)
            first_attempt_accs.append(u_acc)
            attempts_per_item.append(u_avg_att)

        # Status determination
        if u_acc < 60.0 or u_avg_att > 2.2:
            u_status = "at_risk"
        elif u_acc < 75.0 or u_avg_att > 1.6:
            u_status = "needs_review"
        else:
            u_status = "on_track"

        cohort_summaries.append(
            ManagerCohortLearnerSummary(
                user_id=u.id,
                user_name=u.full_name or u.email,
                user_email=u.email,
                overall_score=u_score_avg,
                first_attempt_accuracy=u_acc,
                average_attempts=u_avg_att,
                items_completed=u_total_items,
                status=u_status,
            )
        )

    # Cohort weak topics
    cohort_weak_topics: List[CohortWeakTopic] = []
    for top_name, t_info in cohort_topic_issues.items():
        struggle_count = len(t_info["struggling_learners"])
        if struggle_count > 0:
            avg_att = round(sum(t_info["attempts"]) / len(t_info["attempts"]), 2) if t_info["attempts"] else 1.0
            avg_acc = round(sum(t_info["scores"]) / len(t_info["scores"]), 1) if t_info["scores"] else 0.0
            cohort_weak_topics.append(
                CohortWeakTopic(
                    topic=top_name,
                    struggling_learner_count=struggle_count,
                    avg_attempts=avg_att,
                    avg_accuracy=avg_acc,
                )
            )

    cohort_weak_topics.sort(key=lambda t: t.struggling_learner_count, reverse=True)
    learners_attention = [s for s in cohort_summaries if s.status in ("at_risk", "needs_review")]
    learners_attention.sort(key=lambda s: (s.status == "at_risk", -s.average_attempts), reverse=True)

    psych_mgr = await psychometrics_service.get_manager_effectiveness_report(
        db, tenant_ctx.org_id, current_user, course_id
    )

    return ManagerCohortPerformanceReport(
        cohort_size=len(cohort_users),
        avg_overall_score=round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else 0.0,
        avg_first_attempt_accuracy=round(sum(first_attempt_accs) / len(first_attempt_accs), 1) if first_attempt_accs else 0.0,
        avg_attempts_per_item=round(sum(attempts_per_item) / len(attempts_per_item), 2) if attempts_per_item else 1.0,
        learners_requiring_attention=learners_attention,
        cohort_weak_topics=cohort_weak_topics[:8],
        learner_roster=cohort_summaries,
        cohort_calibration_distribution=psych_mgr.cohort_calibration_distribution,
        flagged_topics_count=len(psych_mgr.flagged_friction_topics),
    )
