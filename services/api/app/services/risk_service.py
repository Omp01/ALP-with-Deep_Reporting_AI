"""
Risk Detection and Early Warning Service.
Evaluates multi-signal risk factors to detect dropout, stagnation, and cognitive overload.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from app.competency import insight, risk as risk_engine
from app.models import LearnerRisk, Enrollment


async def evaluate_learner_risk(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    course_id: UUID,
) -> Dict[str, Any]:
    """
    Evaluate one learner in one enrolled course and store the result.

    The rules and thresholds are in app/competency/risk.py and documented in docs/COMPETENCY_ENGINE.md. Every factor
    cites the numbers that triggered it; the earlier version read event payload keys that do not exist (`correct`) and
    invented a "nominal engagement" sentence when nothing fired.
    """
    now = datetime.utcnow()
    assessment = risk_engine.assess(await insight.risk_input(db, org_id, user_id, course_id, now))

    texts = [f.description for f in assessment.factors] or [assessment.note or "No risk indicators in the recorded evidence."]
    actions = assessment.actions or ["No intervention indicated by the recorded evidence."]

    existing = (await db.execute(
        select(LearnerRisk).where(and_(LearnerRisk.org_id == org_id, LearnerRisk.user_id == user_id,
                                       LearnerRisk.course_id == course_id, LearnerRisk.is_resolved == False))  # noqa: E712
    )).scalars().first()
    if existing is None:
        existing = LearnerRisk(id=uuid.uuid4(), org_id=org_id, user_id=user_id, course_id=course_id, is_resolved=False, detected_at=now)
        db.add(existing)
    existing.risk_level, existing.risk_score = assessment.level, assessment.score
    existing.risk_factors, existing.recommended_actions, existing.risk_details = texts, actions, assessment.details()
    existing.updated_at = now
    await db.flush()

    return {
        "id": str(existing.id), "user_id": str(user_id), "course_id": str(course_id), "risk_level": assessment.level,
        "risk_score": assessment.score, "risk_points": assessment.points, "risk_factors": texts, "risk_details": assessment.details(),
        "recommended_actions": actions, "note": assessment.note, "is_resolved": existing.is_resolved,
        "detected_at": existing.detected_at.isoformat(), "updated_at": existing.updated_at.isoformat(),
    }


async def scan_organization_risks(db: AsyncSession, org_id: UUID) -> Dict[str, Any]:
    """
    Scans all active enrollments in the organization and updates at-risk statuses.
    """
    enrollments_q = (
        select(Enrollment)
        .where(
            and_(
                Enrollment.org_id == org_id,
                Enrollment.status == "active",
            )
        )
    )
    res = await db.execute(enrollments_q)
    enrollments = res.scalars().all()

    evaluated = 0
    high_critical = 0
    results = []

    for enr in enrollments:
        eval_result = await evaluate_learner_risk(
            db=db,
            org_id=org_id,
            user_id=enr.user_id,
            course_id=enr.course_id,
        )
        evaluated += 1
        if eval_result["risk_level"] in ["high", "critical"]:
            high_critical += 1
        results.append(eval_result)

    await db.commit()
    return {
        "evaluated_enrollments": evaluated,
        "high_or_critical_risks": high_critical,
        "timestamp": datetime.utcnow().isoformat(),
    }
