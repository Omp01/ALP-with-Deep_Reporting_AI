"""
Skill-Gap Detection Engine.
Identifies individual learner deficiencies and aggregates cohort-level systemic gaps.
"""
from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.tables import LearnerCompetency, Competency, UserTeam, SkillGap


async def get_learner_skill_gaps(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
) -> List[Dict[str, Any]]:
    """
    Detects skill gaps for an individual learner where mastery_score < 0.65.
    Queries both persisted skill_gaps and live learner_competencies.
    """
    # 1. Query persisted gaps first
    persisted_query = (
        select(SkillGap, Competency)
        .join(Competency, SkillGap.competency_id == Competency.id)
        .where(
            and_(
                SkillGap.org_id == org_id,
                SkillGap.user_id == user_id,
            )
        )
    )
    persisted_res = await db.execute(persisted_query)
    persisted_rows = persisted_res.all()

    gaps = []
    seen_comp_ids = set()
    for sg, comp in persisted_rows:
        seen_comp_ids.add(comp.id)
        gaps.append({
            "competency_id": str(comp.id),
            "competency_name": comp.name,
            "domain": getattr(comp, "taxonomy_level", "understand"),
            "mastery": round(sg.current_mastery, 3),
            "target_mastery": round(sg.target_mastery, 3),
            "gap_size": round(sg.gap_size, 3),
            "severity": sg.severity,
            "recommended_action": (
                f"Assign foundational remedial exercises in {comp.name}"
                if sg.severity in ["critical", "high"]
                else f"Schedule reinforcement assessment for {comp.name}"
            ),
        })

    # 2. Check live competencies if not already recorded
    live_query = (
        select(LearnerCompetency, Competency)
        .join(Competency, LearnerCompetency.competency_id == Competency.id)
        .where(
            and_(
                LearnerCompetency.org_id == org_id,
                LearnerCompetency.user_id == user_id,
            )
        )
    )
    live_res = await db.execute(live_query)
    live_rows = live_res.all()

    for lc, comp in live_rows:
        if comp.id in seen_comp_ids:
            continue
        if lc.mastery_score < 0.65:
            severity = "critical" if lc.mastery_score < 0.40 else ("high" if lc.mastery_score < 0.60 else "medium")
            gaps.append({
                "competency_id": str(comp.id),
                "competency_name": comp.name,
                "domain": comp.taxonomy_level,
                "mastery": round(lc.mastery_score, 3),
                "target_mastery": 0.80,
                "gap_size": round(0.80 - lc.mastery_score, 3),
                "severity": severity,
                "recommended_action": (
                    f"Assign foundational remedial exercises in {comp.name}"
                    if severity in ["critical", "high"]
                    else f"Schedule reinforcement assessment for {comp.name}"
                ),
            })

    return sorted(gaps, key=lambda g: g["mastery"])


async def get_cohort_skill_gaps(
    db: AsyncSession,
    org_id: UUID,
    team_id: UUID,
) -> Dict[str, Any]:
    """
    Aggregates skill gaps across an entire team or cohort.
    Identifies systemic organizational bottlenecks.
    """
    # 1. Fetch team member user IDs
    members_query = select(UserTeam.user_id).where(
        and_(UserTeam.org_id == org_id, UserTeam.team_id == team_id)
    )
    members_res = await db.execute(members_query)
    user_ids = [row[0] for row in members_res.all()]

    if not user_ids:
        # Check if any skill gaps already assigned directly to team_id
        sg_query = (
            select(SkillGap, Competency)
            .join(Competency, SkillGap.competency_id == Competency.id)
            .where(and_(SkillGap.org_id == org_id, SkillGap.team_id == team_id))
        )
        sg_res = await db.execute(sg_query)
        cohort_gaps = []
        for sg, comp in sg_res.all():
            cohort_gaps.append({
                "competency_id": str(comp.id),
                "competency_name": comp.name,
                "domain": comp.taxonomy_level,
                "avg_mastery": round(sg.current_mastery, 3),
                "target_mastery": round(sg.target_mastery, 3),
                "gap_size": round(sg.gap_size, 3),
                "systemic_risk": sg.severity,
            })
        return {"team_id": str(team_id), "total_members": 0, "cohort_gaps": cohort_gaps}

    # 2. Query competency metrics across cohort members
    cohort_query = (
        select(
            Competency.id,
            Competency.name,
            Competency.taxonomy_level,
            func.avg(LearnerCompetency.mastery_score).label("avg_mastery"),
            func.avg(LearnerCompetency.confidence_score).label("avg_confidence"),
            func.count(LearnerCompetency.id).label("evaluated_count"),
        )
        .join(LearnerCompetency, Competency.id == LearnerCompetency.competency_id)
        .where(
            and_(
                LearnerCompetency.org_id == org_id,
                LearnerCompetency.user_id.in_(user_ids),
            )
        )
        .group_by(Competency.id, Competency.name, Competency.taxonomy_level)
    )

    cohort_res = await db.execute(cohort_query)
    results = cohort_res.all()

    cohort_gaps = []
    for comp_id, name, tax_level, avg_mastery, avg_confidence, count in results:
        avg_m = float(avg_mastery) if avg_mastery is not None else 0.0
        avg_c = float(avg_confidence) if avg_confidence is not None else 0.0
        if avg_m < 0.70:
            cohort_gaps.append({
                "competency_id": str(comp_id),
                "competency_name": name,
                "domain": tax_level,
                "avg_mastery": round(avg_m, 3),
                "avg_confidence": round(avg_c, 3),
                "learners_evaluated": count,
                "cohort_coverage_pct": round((count / len(user_ids)) * 100, 1),
                "systemic_risk": "high" if avg_m < 0.50 else "moderate",
            })

    return {
        "team_id": str(team_id),
        "total_members": len(user_ids),
        "cohort_gaps": sorted(cohort_gaps, key=lambda x: x["avg_mastery"]),
    }
