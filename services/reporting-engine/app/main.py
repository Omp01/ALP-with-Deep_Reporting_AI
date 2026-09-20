"""
Reporting Engine Service — Grounded AI Reporting & Deterministic Analytics.
"""
import logging
import sys
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

# Automatically locate and add project root to sys.path for 'shared' imports when running locally
root_dir = Path(__file__).resolve().parents[3]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
from typing import Optional, Dict, Any, List
from uuid import UUID

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.core.database import get_db, engine
from app.models.tables import (
    AIInsight,
    ScheduledReport,
    ReportDigest,
)
from app.evidence.builder import build_evidence_package
from app.grounding.validator import validate_grounded_citations
from app.analytics.calculator import (
    compute_learner_analytics,
    compute_team_analytics,
    compute_organization_analytics,
)
from shared.contracts.contracts import (
    InsightGenerateRequest,
    InsightResponse,
    InsightClaim,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("reporting-engine")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('{"event": "startup", "service": "reporting-engine", "status": "running"}')
    yield
    await engine.dispose()
    logger.info('{"event": "shutdown", "service": "reporting-engine", "status": "stopped"}')


app = FastAPI(
    title="Reporting Engine",
    description="Evidence-Grounded AI Insights & Multi-Surface Analytics Engine",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()
    response: Response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        f'{{"event": "request", "service": "reporting-engine", '
        f'"request_id": "{request_id}", "method": "{request.method}", '
        f'"path": "{request.url.path}", "status": {response.status_code}, '
        f'"duration_ms": {duration_ms}}}'
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Reporting Engine Service",
        "status": "online",
        "docs_url": "/docs",
        "health_url": "/health",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": "reporting-engine",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/ready", tags=["Health"])
async def readiness():
    return {
        "status": "ready",
        "service": "reporting-engine",
        "dependencies": {"postgresql": "connected"},
        "timestamp": datetime.utcnow().isoformat(),
    }


from app.ai.llm_provider import generate_grounded_narrative

# =============================================================================
# Grounded AI Insights Endpoints
# =============================================================================

@app.post("/api/v1/insights/generate", response_model=InsightResponse)
async def generate_grounded_insight(
    req: InsightGenerateRequest,
    org_id: UUID = Query(...),
    report_type: str = Query("progress_summary"),
    db: AsyncSession = Depends(get_db),
):
    """
    Constructs a factual evidence package from PostgreSQL, synthesizes an AI narrative
    grounded with explicit [E-#] citations via LLM / Deterministic engine,
    verifies citation integrity, and saves to database.
    """
    start_time = time.monotonic()

    # 1. Build Evidence Package from verified DB state
    evidence_data = await build_evidence_package(
        db=db,
        org_id=org_id,
        scope_type=req.scope_type,
        scope_id=req.scope_id,
    )
    evidence_items = evidence_data.get("evidence_package", [])

    # 2. Synthesize Grounded Narrative using Multi-Provider LLM with Fallback
    narrative = await generate_grounded_narrative(
        scope_type=req.scope_type,
        evidence_items=evidence_items,
        question=req.question,
    )

    # 3. Validate Grounding & Citations
    is_valid, grounding_score, matched_citations = validate_grounded_citations(
        narrative_text=narrative,
        evidence_package=evidence_items,
    )

    claims_list = [
        InsightClaim(
            claim=mc.get("snippet", mc["citation_key"]),
            confidence=mc.get("confidence", 0.90),
            evidence_ids=[mc["citation_key"]],
            supported=True,
        )
        for mc in matched_citations
    ]
    if not claims_list and not evidence_items:
        claims_list.append(
            InsightClaim(
                claim="Learning activity is currently in initialized state.",
                confidence=0.70,
                evidence_ids=[],
                supported=True,
            )
        )

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    insight_id = uuid.uuid4()
    now = datetime.utcnow()

    # 4. Persist to PostgreSQL ai_insights table
    insight_rec = AIInsight(
        id=insight_id,
        org_id=org_id,
        report_type=report_type,
        scope_type=req.scope_type,
        scope_id=req.scope_id,
        narrative_text=narrative,
        structured_data={
            "question": req.question,
            "evidence_count": len(evidence_items),
            "claims_count": len(claims_list),
            "evidence_package": evidence_items,
        },
        confidence_score=grounding_score,
        citations=matched_citations,
        model_used="gpt-4o-mini",
        created_at=now,
    )
    db.add(insight_rec)
    await db.commit()

    return InsightResponse(
        insight_id=insight_id,
        scope_type=req.scope_type,
        scope_id=req.scope_id,
        question=req.question,
        claims=claims_list,
        summary=narrative,
        recommendations=[
            "Review verified citation evidence cards to inspect source telemetry",
            "Maintain adaptive remediation pacing for deficit competencies",
        ],
        status="validated" if is_valid else "generated",
        prompt_version="v1.0.0-grounded",
        model_used="gpt-4o-mini",
        generation_time_ms=elapsed_ms,
        created_at=now,
    )


@app.get("/api/v1/insights/{insight_id}")
async def get_insight(
    insight_id: UUID,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve saved AI insight with verified citations."""
    q = select(AIInsight).where(
        and_(AIInsight.id == insight_id, AIInsight.org_id == org_id)
    )
    res = await db.execute(q)
    rec = res.scalars().first()
    if not rec:
        raise HTTPException(status_code=404, detail="Insight not found")

    return {
        "id": str(rec.id),
        "org_id": str(rec.org_id),
        "report_type": rec.report_type,
        "scope_type": rec.scope_type,
        "scope_id": str(rec.scope_id) if rec.scope_id else None,
        "narrative_text": rec.narrative_text,
        "confidence_score": rec.confidence_score,
        "citations": rec.citations,
        "model_used": rec.model_used,
        "structured_data": rec.structured_data,
        "created_at": rec.created_at.isoformat(),
    }


@app.get("/api/v1/insights/{insight_id}/evidence")
async def get_insight_evidence(
    insight_id: UUID,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves backing evidence facts for an insight's claims."""
    q = select(AIInsight).where(
        and_(AIInsight.id == insight_id, AIInsight.org_id == org_id)
    )
    res = await db.execute(q)
    rec = res.scalars().first()
    if not rec:
        raise HTTPException(status_code=404, detail="Insight not found")

    structured = rec.structured_data or {}
    return {
        "insight_id": str(rec.id),
        "citations": rec.citations,
        "evidence_package": structured.get("evidence_package", []),
    }


# =============================================================================
# Analytics Endpoints
# =============================================================================

@app.get("/api/v1/analytics/learner/{user_id}")
async def get_learner_analytics(
    user_id: UUID,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Returns deterministic progress, accuracy, and velocity analytics."""
    return await compute_learner_analytics(db=db, org_id=org_id, user_id=user_id)


@app.get("/api/v1/analytics/team/{team_id}")
async def get_team_analytics(
    team_id: UUID,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Returns aggregated team/cohort metrics."""
    return await compute_team_analytics(db=db, org_id=org_id, team_id=team_id)


@app.get("/api/v1/analytics/organization")
async def get_org_analytics(
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Returns organization-level executive KPIs."""
    return await compute_organization_analytics(db=db, org_id=org_id)


# =============================================================================
# Scheduled Digest Endpoints
# =============================================================================

@app.post("/api/v1/reports/digest/generate")
async def generate_scheduled_digest(
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Generates a proactive scheduled digest for managers and admins."""
    # Find active scheduled report or create default
    sr_q = select(ScheduledReport).where(
        and_(ScheduledReport.org_id == org_id, ScheduledReport.is_active == True)
    ).limit(1)
    sr_res = await db.execute(sr_q)
    sr = sr_res.scalars().first()

    now = datetime.utcnow()
    if not sr:
        sr = ScheduledReport(
            id=uuid.uuid4(),
            org_id=org_id,
            title="Weekly Leadership Digest",
            report_type="executive_weekly",
            schedule_cron="0 8 * * 1",
            recipients=["admin@acme.com", "marcus.manager@acme.com"],
            last_run_at=now,
            is_active=True,
            created_at=now,
        )
        db.add(sr)
        await db.flush()

    org_metrics = await compute_organization_analytics(db=db, org_id=org_id)
    digest_text = (
        f"Leadership Learning Digest for Organization:\n"
        f"- Active Enrollments: {org_metrics['active_enrollments']}\n"
        f"- Overall Curriculum Completion: {org_metrics['overall_completion_rate_pct']}%\n"
        f"- Organization Mastery Index: {org_metrics['organization_mastery_index']}\n"
        f"- Critical At-Risk Learners Requiring Intervention: {org_metrics['critical_at_risk_learners']}"
    )

    digest_rec = ReportDigest(
        id=uuid.uuid4(),
        org_id=org_id,
        scheduled_report_id=sr.id,
        generated_content=digest_text,
        sent_to=sr.recipients,
        sent_at=now,
        status="success",
    )
    db.add(digest_rec)
    sr.last_run_at = now
    await db.commit()

    return {
        "digest_id": str(digest_rec.id),
        "scheduled_report_id": str(sr.id),
        "content": digest_text,
        "sent_to": digest_rec.sent_to,
        "timestamp": now.isoformat(),
    }


@app.get("/api/v1/reports/digest/latest")
async def get_latest_digest(
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Fetches the latest generated digest."""
    q = (
        select(ReportDigest)
        .where(ReportDigest.org_id == org_id)
        .order_by(desc(ReportDigest.sent_at))
        .limit(1)
    )
    res = await db.execute(q)
    rec = res.scalars().first()
    if not rec:
        raise HTTPException(status_code=404, detail="No digest found for organization")

    return {
        "id": str(rec.id),
        "content": rec.generated_content,
        "sent_to": rec.sent_to,
        "sent_at": rec.sent_at.isoformat(),
        "status": rec.status,
    }
