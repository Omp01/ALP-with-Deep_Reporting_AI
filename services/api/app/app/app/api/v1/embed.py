"""
Embeddable Reporting Widget API.
Provides embeddable HTML and lightweight JSON payloads for embedding inside third-party portals.
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models import LearnerCompetency, Competency, User, Organization
from app.api.deps import get_current_tenant, TenantContext

router = APIRouter(prefix="/embed", tags=["Embeddable Widget"])


@router.get("/report")
async def get_embeddable_report_widget(
    learner_id: UUID = Query(..., description="Target Learner ID"),
    org_id: UUID = Query(..., description="Tenant Organization ID"),
    format: str = Query("html", regex="^(html|json)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Renders an embeddable widget card for external portals (e.g., Salesforce, Slack canvas, internal HR portal).
    """
    # Fetch learner and organization
    user_res = await db.execute(select(User).where(and_(User.id == learner_id, User.org_id == org_id)))
    user = user_res.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Learner not found")

    comp_res = await db.execute(
        select(LearnerCompetency, Competency)
        .join(Competency, LearnerCompetency.competency_id == Competency.id)
        .where(and_(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == learner_id))
    )
    competencies = comp_res.all()

    avg_mastery = (sum(lc.mastery_score for lc, _ in competencies) / len(competencies)) if competencies else 0.0

    if format == "json":
        return {
            "learner_id": str(learner_id),
            "full_name": user.full_name,
            "average_mastery": round(avg_mastery, 3),
            "competencies_count": len(competencies),
            "competencies": [
                {
                    "name": c.name,
                    "mastery": round(lc.mastery_score, 2),
                    "confidence": round(lc.confidence_score, 2),
                    "status": lc.status,
                }
                for lc, c in competencies
            ],
        }

    # Render clean, professional HTML widget
    comp_rows_html = "".join([
        f"""
        <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #f1f5f9;">
            <span style="font-size:14px; font-weight:500; color:#334155;">{c.name}</span>
            <div style="display:flex; align-items:center; gap:8px;">
                <div style="width:100px; height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden;">
                    <div style="width:{int(lc.mastery_score * 100)}%; height:100%; background:#2563eb;"></div>
                </div>
                <span style="font-size:12px; font-weight:600; color:#0f172a;">{int(lc.mastery_score * 100)}%</span>
            </div>
        </div>
        """
        for lc, c in competencies[:5]
    ])

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Adaptive Learning Progress - {user.full_name}</title>
    </head>
    <body style="margin:0; padding:16px; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#ffffff;">
        <div style="border:1px solid #e2e8f0; border-radius:12px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,0.05); max-width:480px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                <div>
                    <h3 style="margin:0; font-size:16px; font-weight:600; color:#0f172a;">{user.full_name}</h3>
                    <p style="margin:2px 0 0 0; font-size:12px; color:#64748b;">Learner Competency Report</p>
                </div>
                <div style="background:#eff6ff; color:#1d4ed8; padding:4px 10px; border-radius:9999px; font-size:12px; font-weight:600;">
                    {int(avg_mastery * 100)}% Overall
                </div>
            </div>
            <div style="margin-top:8px;">
                {comp_rows_html if comp_rows_html else '<p style="color:#94a3b8; font-size:13px;">No competency evaluations yet.</p>'}
            </div>
            <div style="margin-top:16px; text-align:right;">
                <span style="font-size:11px; color:#94a3b8;">Verified by Adaptive LMS Deep Reporting AI</span>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
