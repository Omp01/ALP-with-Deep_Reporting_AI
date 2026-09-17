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

from app.models import LearnerRisk, LearningEvent, Enrollment, Course, User, LearnerCompetency


RISK_WEIGHTS = {
    "declining_mastery": 0.25,
    "consecutive_failures": 0.20,
    "high_retry_rate": 0.15,
    "latency_spike": 0.10,
    "low_assessment_score": 0.15,
    "inactivity_stagnation": 0.15,
}


async def evaluate_learner_risk(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    course_id: UUID,
) -> Dict[str, Any]:
    """
    Evaluates risk signals for a specific learner within an enrolled course.
    """
    # 1. Fetch recent learning events for learner in course
    events_q = (
        select(LearningEvent)
        .where(
            and_(
                LearningEvent.org_id == org_id,
                LearningEvent.user_id == user_id,
                LearningEvent.course_id == course_id,
            )
        )
        .order_by(desc(LearningEvent.timestamp))
        .limit(50)
    )
    res = await db.execute(events_q)
    events = res.scalars().all()

    factors = []
    actions = []
    score = 0.0

    now = datetime.utcnow()

    # Signal 6: Inactivity Stagnation (>7 days without learning event)
    if not events:
        score += RISK_WEIGHTS["inactivity_stagnation"] * 0.8
        factors.append("No learning activity recorded in enrolled course")
        actions.append("Send automated re-engagement prompt and check-in survey")
    else:
        last_event_time = events[0].timestamp
        days_inactive = (now - last_event_time).total_seconds() / 86400.0
        if days_inactive >= 7.0:
            severity = min(1.0, days_inactive / 14.0)
            score += RISK_WEIGHTS["inactivity_stagnation"] * severity
            factors.append(f"Prolonged inactivity: {int(days_inactive)} days since last learning action")
            actions.append("Trigger manager 1-on-1 nudge or automated schedule reminder")

    # Assessment & Question telemetry signals
    question_events = [
        e for e in events if e.event_type in ["question_answered", "answer_retried"]
    ]

    if question_events:
        # Signal 2: Consecutive Failures (>=4 in recent submissions)
        consecutive_incorrect = 0
        for qe in question_events:
            p = qe.payload or {}
            if p.get("correct") is False:
                consecutive_incorrect += 1
            else:
                break

        if consecutive_incorrect >= 4:
            score += RISK_WEIGHTS["consecutive_failures"] * min(1.0, consecutive_incorrect / 6.0)
            factors.append(f"Repeated assessment failure ({consecutive_incorrect} consecutive incorrect items)")
            actions.append("Initiate foundational concept remediation and step down assessment difficulty")

        # Signal 3: High Retry Rate (>50% retries on questions)
        retry_events_count = sum(
            1 for qe in question_events
            if qe.event_type == "answer_retried" or (qe.payload or {}).get("attempt_number", 1) > 1
        )
        retry_rate = retry_events_count / len(question_events)
        if retry_rate > 0.45:
            score += RISK_WEIGHTS["high_retry_rate"] * min(1.0, retry_rate)
            factors.append(f"High struggle retry rate ({int(retry_rate * 100)}% of questions required retries)")
            actions.append("Provide scaffolded hints and interactive walkthrough examples")

        # Signal 5: Low Assessment Accuracy (<40% correct across recent window)
        correct_count = sum(
            1 for qe in question_events
            if (qe.payload or {}).get("correct") is True
        )
        accuracy = correct_count / len(question_events)
        if accuracy < 0.40:
            score += RISK_WEIGHTS["low_assessment_score"] * (1.0 - accuracy)
            factors.append(f"Critical low question accuracy ({int(accuracy * 100)}% accuracy across recent attempts)")
            actions.append("Assign prerequisite review before allowing advancement to next module")

        # Signal 4: Latency Spike (>40% increase in response time)
        latencies = [
            (qe.payload or {}).get("duration_ms")
            for qe in question_events if (qe.payload or {}).get("duration_ms")
        ]
        if len(latencies) >= 6:
            recent_half = latencies[: len(latencies) // 2]
            older_half = latencies[len(latencies) // 2 :]
            avg_recent = sum(recent_half) / len(recent_half)
            avg_older = sum(older_half) / len(older_half)
            if avg_older > 0 and (avg_recent - avg_older) / avg_older > 0.40:
                score += RISK_WEIGHTS["latency_spike"] * 0.8
                factors.append("Cognitive friction detected: 40%+ increase in question response latency")
                actions.append("Break down content into smaller micro-learning chunks to reduce fatigue")

    # Signal 1: Declining Mastery Trend
    comp_q = (
        select(LearnerCompetency)
        .where(
            and_(
                LearnerCompetency.org_id == org_id,
                LearnerCompetency.user_id == user_id,
            )
        )
    )
    comp_res = await db.execute(comp_q)
    competencies = comp_res.scalars().all()
    if competencies:
        low_or_declining = [c for c in competencies if c.mastery_score < 0.45]
        if len(low_or_declining) >= 2:
            score += RISK_WEIGHTS["declining_mastery"] * 0.9
            factors.append(f"Persistent mastery deficiency across {len(low_or_declining)} core competencies")
            actions.append("Schedule targeted instructor tutoring session")

    # Clamp final score
    final_score = min(1.0, round(score, 3))

    if final_score >= 0.70:
        level = "critical"
    elif final_score >= 0.50:
        level = "high"
    elif final_score >= 0.30:
        level = "medium"
    else:
        level = "low"

    if not factors:
        factors.append("Nominal engagement and steady progression")
    if not actions:
        actions.append("Maintain self-paced curriculum path")

    # Upsert or update existing active risk record
    existing_q = (
        select(LearnerRisk)
        .where(
            and_(
                LearnerRisk.org_id == org_id,
                LearnerRisk.user_id == user_id,
                LearnerRisk.course_id == course_id,
                LearnerRisk.is_resolved == False,
            )
        )
    )
    existing_res = await db.execute(existing_q)
    risk_rec = existing_res.scalars().first()

    if not risk_rec:
        risk_rec = LearnerRisk(
            id=uuid.uuid4(),
            org_id=org_id,
            user_id=user_id,
            course_id=course_id,
            risk_level=level,
            risk_score=final_score,
            risk_factors=factors,
            recommended_actions=actions,
            is_resolved=False,
            detected_at=now,
            updated_at=now,
        )
        db.add(risk_rec)
    else:
        risk_rec.risk_level = level
        risk_rec.risk_score = final_score
        risk_rec.risk_factors = factors
        risk_rec.recommended_actions = actions
        risk_rec.updated_at = now

    await db.flush()

    return {
        "id": str(risk_rec.id),
        "user_id": str(user_id),
        "course_id": str(course_id),
        "risk_level": level,
        "risk_score": final_score,
        "risk_factors": factors,
        "recommended_actions": actions,
        "is_resolved": risk_rec.is_resolved,
        "detected_at": risk_rec.detected_at.isoformat(),
        "updated_at": risk_rec.updated_at.isoformat(),
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
