"""
Deterministic Analytics Calculator.
Computes verified performance metrics for Learner, Team, and Organization dashboards.
"""

from typing import Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.models.tables import (
    LearnerCompetency,
    LearningEvent,
    Enrollment,
    Course,
    LearnerRisk,
    UserTeam,
    User,
)


async def compute_learner_analytics(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
) -> Dict[str, Any]:
    """Computes deterministic progress, mastery, and velocity analytics for a learner."""
    # Competency states
    comp_q = select(LearnerCompetency).where(
        and_(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id)
    )
    comp_res = await db.execute(comp_q)
    competencies = comp_res.scalars().all()

    total_comps = len(competencies)
    avg_mastery = (sum(c.mastery_score for c in competencies) / total_comps) if total_comps else 0.0

    mastery_distribution = {
        "expert": sum(1 for c in competencies if c.mastery_score >= 0.85),
        "proficient": sum(1 for c in competencies if 0.70 <= c.mastery_score < 0.85),
        "developing": sum(1 for c in competencies if 0.50 <= c.mastery_score < 0.70),
        "novice": sum(1 for c in competencies if c.mastery_score < 0.50),
    }

    # Telemetry events metrics
    events_q = select(LearningEvent).where(
        and_(LearningEvent.org_id == org_id, LearningEvent.user_id == user_id)
    )
    events_res = await db.execute(events_q)
    events = events_res.scalars().all()

    question_events = [e for e in events if e.event_type == "question_answered"]
    correct_count = sum(1 for q in question_events if (q.payload or {}).get("correct") is True)
    accuracy = (correct_count / len(question_events)) if question_events else 0.0

    latencies = [
        (q.payload or {}).get("duration_ms", 0)
        for q in question_events if (q.payload or {}).get("duration_ms")
    ]
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    # Enrollments
    enr_q = select(Enrollment).where(
        and_(Enrollment.org_id == org_id, Enrollment.user_id == user_id)
    )
    enr_res = await db.execute(enr_q)
    enrollments = enr_res.scalars().all()
    avg_progress = (sum(e.progress_pct for e in enrollments) / len(enrollments)) if enrollments else 0.0

    return {
        "user_id": str(user_id),
        "competencies_evaluated": total_comps,
        "average_mastery": round(avg_mastery, 3),
        "mastery_distribution": mastery_distribution,
        "total_questions_attempted": len(question_events),
        "accuracy_rate": round(accuracy, 3),
        "avg_response_time_ms": round(avg_latency, 1),
        "active_courses": len(enrollments),
        "average_course_progress_pct": round(avg_progress * 100, 1),
    }


async def compute_team_analytics(
    db: AsyncSession,
    org_id: UUID,
    team_id: UUID,
) -> Dict[str, Any]:
    """Computes aggregated cohort analytics for manager dashboard."""
    # Find team members
    members_q = select(UserTeam.user_id).where(
        and_(UserTeam.org_id == org_id, UserTeam.team_id == team_id)
    )
    members_res = await db.execute(members_q)
    user_ids = [r[0] for r in members_res.all()]

    if not user_ids:
        return {"team_id": str(team_id), "total_members": 0}

    # Query risks for team
    risks_q = select(LearnerRisk).where(
        and_(
            LearnerRisk.org_id == org_id,
            LearnerRisk.user_id.in_(user_ids),
            LearnerRisk.is_resolved == False,
        )
    )
    risks_res = await db.execute(risks_q)
    risks = risks_res.scalars().all()

    risk_breakdown = {
        "critical": sum(1 for r in risks if r.risk_level == "critical"),
        "high": sum(1 for r in risks if r.risk_level == "high"),
        "medium": sum(1 for r in risks if r.risk_level == "medium"),
        "low": sum(1 for r in risks if r.risk_level == "low"),
    }

    # Query competencies
    comp_q = select(LearnerCompetency).where(
        and_(
            LearnerCompetency.org_id == org_id,
            LearnerCompetency.user_id.in_(user_ids),
        )
    )
    comp_res = await db.execute(comp_q)
    competencies = comp_res.scalars().all()
    avg_mastery = (sum(c.mastery_score for c in competencies) / len(competencies)) if competencies else 0.0

    return {
        "team_id": str(team_id),
        "total_members": len(user_ids),
        "evaluated_competencies": len(competencies),
        "average_cohort_mastery": round(avg_mastery, 3),
        "at_risk_breakdown": risk_breakdown,
        "total_unresolved_risks": len(risks),
    }


async def compute_organization_analytics(
    db: AsyncSession,
    org_id: UUID,
) -> Dict[str, Any]:
    """Computes executive high-level learning operations analytics."""
    users_q = select(func.count(User.id)).where(User.org_id == org_id)
    users_count = (await db.execute(users_q)).scalar() or 0

    courses_q = select(func.count(Course.id)).where(Course.org_id == org_id)
    courses_count = (await db.execute(courses_q)).scalar() or 0

    enr_q = select(Enrollment).where(Enrollment.org_id == org_id)
    enrs = (await db.execute(enr_q)).scalars().all()
    avg_progress = (sum(e.progress_pct for e in enrs) / len(enrs)) if enrs else 0.0

    comp_q = select(func.avg(LearnerCompetency.mastery_score)).where(LearnerCompetency.org_id == org_id)
    org_mastery = (await db.execute(comp_q)).scalar() or 0.0

    risk_q = select(func.count(LearnerRisk.id)).where(
        and_(LearnerRisk.org_id == org_id, LearnerRisk.is_resolved == False, LearnerRisk.risk_level.in_(["high", "critical"]))
    )
    critical_risks = (await db.execute(risk_q)).scalar() or 0

    return {
        "org_id": str(org_id),
        "total_users": users_count,
        "total_courses": courses_count,
        "active_enrollments": len(enrs),
        "overall_completion_rate_pct": round(avg_progress * 100, 1),
        "organization_mastery_index": round(float(org_mastery), 3),
        "critical_at_risk_learners": critical_risks,
    }
