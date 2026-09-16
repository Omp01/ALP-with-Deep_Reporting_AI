"""
Evidence Package Builder for Grounded AI Insights.
Aggregates factual ground-truth data from PostgreSQL to ground all generated narratives.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.tables import (
    LearnerCompetency,
    Competency,
    LearningEvent,
    LearnerRisk,
    Enrollment,
    Course,
    UserTeam,
)


async def build_evidence_package(
    db: AsyncSession,
    org_id: UUID,
    scope_type: str,
    scope_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Constructs an evidence package with numbered citations [E-1], [E-2], etc.
    Guaranteed to reflect verifiable database state.
    """
    evidence_items = []
    e_counter = 1

    # Scope: Learner
    if scope_type == "learner" and scope_id:
        # 1. Competency States
        comp_q = (
            select(LearnerCompetency, Competency)
            .join(Competency, LearnerCompetency.competency_id == Competency.id)
            .where(
                and_(
                    LearnerCompetency.org_id == org_id,
                    LearnerCompetency.user_id == scope_id,
                )
            )
        )
        comp_res = await db.execute(comp_q)
        for lc, c in comp_res.all():
            evidence_items.append({
                "citation_key": f"E-{e_counter}",
                "source_type": "competency_mastery",
                "source_id": str(lc.id),
                "competency_name": c.name,
                "fact": f"Mastery in {c.name} is {lc.mastery_score:.2f} (status: {lc.status}, confidence: {lc.confidence_score:.2f})",
                "confidence": 0.95,
            })
            e_counter += 1

        # 2. Recent Telemetry Events
        events_q = (
            select(LearningEvent)
            .where(
                and_(
                    LearningEvent.org_id == org_id,
                    LearningEvent.user_id == scope_id,
                )
            )
            .order_by(desc(LearningEvent.timestamp))
            .limit(10)
        )
        events_res = await db.execute(events_q)
        for ev in events_res.scalars().all():
            payload = ev.payload or {}
            fact_desc = f"Learning event '{ev.event_type}' recorded"
            if "correct" in payload:
                fact_desc += f" with correctness={payload['correct']}"
            if "duration_ms" in payload:
                fact_desc += f", latency={payload['duration_ms']}ms"

            evidence_items.append({
                "citation_key": f"E-{e_counter}",
                "source_type": "telemetry_event",
                "source_id": str(ev.id),
                "fact": fact_desc,
                "timestamp": ev.timestamp.isoformat(),
                "confidence": 0.99,
            })
            e_counter += 1

        # 3. Active Risk Signals
        risk_q = (
            select(LearnerRisk)
            .where(
                and_(
                    LearnerRisk.org_id == org_id,
                    LearnerRisk.user_id == scope_id,
                )
            )
            .order_by(desc(LearnerRisk.updated_at))
            .limit(1)
        )
        risk_res = await db.execute(risk_q)
        risk = risk_res.scalars().first()
        if risk:
            evidence_items.append({
                "citation_key": f"E-{e_counter}",
                "source_type": "risk_assessment",
                "source_id": str(risk.id),
                "fact": f"Assessed at {risk.risk_level.upper()} risk level (score: {risk.risk_score:.2f}). Factors: {', '.join(risk.risk_factors)}",
                "confidence": 0.92,
            })
            e_counter += 1

    # Scope: Team / Cohort
    elif scope_type == "cohort" or scope_type == "team":
        team_id = scope_id
        # Query team members
        members_q = select(UserTeam.user_id).where(
            and_(UserTeam.org_id == org_id, UserTeam.team_id == team_id)
        ) if team_id else select(UserTeam.user_id).where(UserTeam.org_id == org_id)
        members_res = await db.execute(members_q)
        uids = [r[0] for r in members_res.all()]

        if uids:
            # Aggregate cohort competencies
            cohort_comp_q = (
                select(LearnerCompetency, Competency)
                .join(Competency, LearnerCompetency.competency_id == Competency.id)
                .where(
                    and_(
                        LearnerCompetency.org_id == org_id,
                        LearnerCompetency.user_id.in_(uids),
                    )
                )
            )
            c_res = await db.execute(cohort_comp_q)
            rows = c_res.all()
            if rows:
                avg_m = sum(lc.mastery_score for lc, _ in rows) / len(rows)
                evidence_items.append({
                    "citation_key": f"E-{e_counter}",
                    "source_type": "cohort_metrics",
                    "source_id": str(team_id) if team_id else "all",
                    "fact": f"Cohort average competency mastery is {avg_m:.2f} across {len(rows)} evaluated competencies",
                    "confidence": 0.94,
                })
                e_counter += 1

    # Scope: Organization / Executive
    else:
        # Org wide enrollments & active learners count
        enr_q = select(Enrollment).where(Enrollment.org_id == org_id)
        enr_res = await db.execute(enr_q)
        enrs = enr_res.scalars().all()
        avg_progress = (sum(e.progress_pct for e in enrs) / len(enrs)) if enrs else 0.0

        evidence_items.append({
            "citation_key": f"E-{e_counter}",
            "source_type": "organization_metrics",
            "source_id": str(org_id),
            "fact": f"Organization maintains {len(enrs)} active enrollments with an average curriculum completion rate of {avg_progress * 100:.1f}%",
            "confidence": 0.98,
        })
        e_counter += 1

    return {
        "org_id": str(org_id),
        "scope_type": scope_type,
        "scope_id": str(scope_id) if scope_id else None,
        "total_evidence_facts": len(evidence_items),
        "evidence_package": evidence_items,
    }
