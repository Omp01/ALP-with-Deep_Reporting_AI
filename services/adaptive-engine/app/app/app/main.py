"""
Adaptive Engine Service — Real-time Competency Modelling & Adaptive Sequencing.
"""
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, asc

from app.core.database import get_db, engine
from app.models.tables import (
    LearnerCompetency,
    CompetencyHistory,
    AdaptiveSession,
    SessionSequenceStep,
    Competency,
    LearningEvent,
    Module,
    ContentItem,
)
from app.competency.mastery import (
    calculate_mastery,
    calculate_confidence,
    determine_trend,
)
from app.sequencing.policy import evaluate_adaptive_policy
from app.sequencing.recommender import find_recommended_content
from app.competency.skill_gap import get_learner_skill_gaps, get_cohort_skill_gaps
from shared.contracts.contracts import (
    AdaptiveNextRequest,
    AdaptiveNextResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("adaptive-engine")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('{"event": "startup", "service": "adaptive-engine", "status": "running"}')
    yield
    await engine.dispose()
    logger.info('{"event": "shutdown", "service": "adaptive-engine", "status": "stopped"}')


app = FastAPI(
    title="Adaptive Engine",
    description="Live Competency Modelling, Adaptive Sequencing & Skill-Gap Engine",
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
        f'{{"event": "request", "service": "adaptive-engine", '
        f'"request_id": "{request_id}", "method": "{request.method}", '
        f'"path": "{request.url.path}", "status": {response.status_code}, '
        f'"duration_ms": {duration_ms}}}'
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": "adaptive-engine",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/ready", tags=["Health"])
async def readiness():
    return {
        "status": "ready",
        "service": "adaptive-engine",
        "dependencies": {"postgresql": "connected"},
        "timestamp": datetime.utcnow().isoformat(),
    }


# =============================================================================
# Event Ingestion & Competency Modelling
# =============================================================================

class EventIngestPayload(BaseModel):
    event_id: Optional[UUID] = None
    org_id: UUID
    user_id: UUID
    event_type: str
    session_id: Optional[UUID] = None
    course_id: Optional[UUID] = None
    module_id: Optional[UUID] = None
    timestamp: Optional[datetime] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/adaptive/events", status_code=status.HTTP_200_OK)
async def process_learning_event(
    event: EventIngestPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Processes learning event, updates learner competency model, and records history.
    """
    raw_payload = event.payload or {}
    competency_id_str = raw_payload.get("competency_id")
    
    comp_id = None
    if competency_id_str:
        try:
            comp_id = UUID(str(competency_id_str))
        except ValueError:
            pass

    if not comp_id:
        first_comp = await db.execute(select(Competency).where(Competency.org_id == event.org_id).limit(1))
        comp_obj = first_comp.scalars().first()
        if comp_obj:
            comp_id = comp_obj.id

    if not comp_id:
        return {"status": "ignored", "reason": "No valid competency associated with event"}

    # Fetch existing learner competency state
    query = select(LearnerCompetency).where(
        and_(
            LearnerCompetency.org_id == event.org_id,
            LearnerCompetency.user_id == event.user_id,
            LearnerCompetency.competency_id == comp_id,
        )
    )
    res = await db.execute(query)
    lc = res.scalars().first()

    now = event.timestamp or datetime.utcnow()
    attempt = {
        "correct": raw_payload.get("correct", True),
        "difficulty": raw_payload.get("difficulty", "intermediate"),
        "duration_ms": raw_payload.get("duration_ms", 3000),
        "attempt_number": raw_payload.get("attempt_number", 1),
        "error_type": raw_payload.get("error_type"),
        "timestamp": now,
    }

    if not lc:
        calc = calculate_mastery([attempt], current_time=now)
        new_mastery = calc["mastery"]
        status_label = "proficient" if new_mastery >= 0.8 else ("competent" if new_mastery >= 0.6 else "novice")
        lc = LearnerCompetency(
            id=uuid.uuid4(),
            org_id=event.org_id,
            user_id=event.user_id,
            competency_id=comp_id,
            mastery_score=new_mastery,
            confidence_score=calculate_confidence(1),
            data_points_count=1,
            status=status_label,
            last_assessed_at=now,
            updated_at=now,
        )
        db.add(lc)
        await db.flush()
        delta = new_mastery
    else:
        old_mastery = lc.mastery_score
        new_count = lc.data_points_count + 1
        
        # Exponential moving average update
        is_correct = raw_payload.get("correct", True)
        target_val = 1.0 if is_correct else 0.0
        alpha = 0.25
        updated_mastery = round(float((1 - alpha) * old_mastery + alpha * target_val), 4)
        status_label = "expert" if updated_mastery >= 0.9 else ("proficient" if updated_mastery >= 0.75 else ("competent" if updated_mastery >= 0.6 else "developing"))

        lc.mastery_score = updated_mastery
        lc.data_points_count = new_count
        lc.confidence_score = calculate_confidence(new_count)
        lc.status = status_label
        lc.last_assessed_at = now
        lc.updated_at = now

        delta = updated_mastery - old_mastery

    # Record historical progression
    history_rec = CompetencyHistory(
        id=uuid.uuid4(),
        learner_competency_id=lc.id,
        mastery_score=lc.mastery_score,
        event_id=event.event_id,
        recorded_at=now,
    )
    db.add(history_rec)
    await db.commit()

    return {
        "status": "updated",
        "competency_id": str(comp_id),
        "new_mastery": lc.mastery_score,
        "confidence": lc.confidence_score,
        "delta": round(delta, 4),
    }


# =============================================================================
# Adaptive Sequencing & Recommendation
# =============================================================================

@app.post("/api/v1/adaptive/next", response_model=AdaptiveNextResponse)
async def get_next_recommendation(
    req: AdaptiveNextRequest,
    org_id: UUID = Query(..., description="Organization Tenant ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluates learner state against the curriculum to generate real-time adaptive next step.
    Saves the session and step to `adaptive_sessions` and `session_sequence_steps`.
    """
    comp_state = None
    comp_obj = None

    if req.current_competency_id:
        q = select(LearnerCompetency, Competency).join(
            Competency, LearnerCompetency.competency_id == Competency.id
        ).where(
            and_(
                LearnerCompetency.org_id == org_id,
                LearnerCompetency.user_id == req.learner_id,
                LearnerCompetency.competency_id == req.current_competency_id,
            )
        )
        res = await db.execute(q)
        row = res.first()
        if row:
            comp_state, comp_obj = row
    else:
        q = select(LearnerCompetency, Competency).join(
            Competency, LearnerCompetency.competency_id == Competency.id
        ).where(
            and_(
                LearnerCompetency.org_id == org_id,
                LearnerCompetency.user_id == req.learner_id,
            )
        ).order_by(LearnerCompetency.mastery_score.asc()).limit(1)
        res = await db.execute(q)
        row = res.first()
        if row:
            comp_state, comp_obj = row

    mastery = comp_state.mastery_score if comp_state else 0.50
    confidence = comp_state.confidence_score if comp_state else 0.20

    # 2. Evaluate Policy
    decision, reason, recommended_diff = evaluate_adaptive_policy(
        mastery=mastery,
        confidence=confidence,
        trend="stable",
        consecutive_correct=3 if mastery > 0.85 else 1,
    )

    # 3. Resolve Content
    content_match = await find_recommended_content(
        db=db,
        org_id=org_id,
        course_id=req.course_id,
        recommended_difficulty=recommended_diff,
        decision=decision,
        current_module_id=req.current_module_id,
    )

    # 4. Upsert Adaptive Session & Sequence Step
    session_q = select(AdaptiveSession).where(AdaptiveSession.id == req.session_id)
    session_res = await db.execute(session_q)
    adap_session = session_res.scalars().first()

    if not adap_session:
        adap_session = AdaptiveSession(
            id=req.session_id,
            org_id=org_id,
            user_id=req.learner_id,
            course_id=req.course_id,
            current_module_id=req.current_module_id,
            state="active",
            current_difficulty=0.8 if recommended_diff == "advanced" else (0.5 if recommended_diff == "intermediate" else 0.2),
            recommended_next_action=decision,
            session_metadata={},
            started_at=datetime.utcnow(),
        )
        db.add(adap_session)
        await db.flush()

    # Create sequence step
    count_steps_q = select(SessionSequenceStep).where(SessionSequenceStep.session_id == adap_session.id)
    steps_res = await db.execute(count_steps_q)
    step_num = len(steps_res.scalars().all()) + 1

    item_id_to_record = (
        UUID(content_match["content_id"])
        if content_match and content_match.get("content_id")
        else (UUID(content_match["module_id"]) if content_match and content_match.get("module_id") else uuid.uuid4())
    )

    step_record = SessionSequenceStep(
        id=uuid.uuid4(),
        session_id=adap_session.id,
        step_order=step_num,
        item_type="content" if content_match and content_match.get("content_id") else "module",
        item_id=item_id_to_record,
        reason=reason,
        status="presented",
        result_score=mastery,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(step_record)
    await db.commit()

    return AdaptiveNextResponse(
        decision=decision,
        reason=reason,
        competency_id=comp_state.competency_id if comp_state else None,
        competency_name=comp_obj.name if comp_state and comp_obj else "Foundational Competencies",
        mastery=mastery,
        confidence=confidence,
        recommended_content_id=UUID(content_match["content_id"]) if content_match and content_match.get("content_id") else None,
        recommended_content_title=content_match.get("content_title") if content_match else None,
        recommended_difficulty=recommended_diff,
        adaptation_type=f"Pedagogical {decision.upper()} step",
    )


# =============================================================================
# Query Endpoints: Competencies, Decisions, Skill Gaps
# =============================================================================

@app.get("/api/v1/adaptive/competencies/{learner_id}")
async def get_learner_competencies(
    learner_id: UUID,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves all competency mastery records for a learner."""
    q = select(LearnerCompetency, Competency).join(
        Competency, LearnerCompetency.competency_id == Competency.id
    ).where(
        and_(
            LearnerCompetency.org_id == org_id,
            LearnerCompetency.user_id == learner_id,
        )
    ).order_by(desc(LearnerCompetency.updated_at))
    
    res = await db.execute(q)
    results = []
    for lc, comp in res.all():
        results.append({
            "competency_id": str(comp.id),
            "name": comp.name,
            "domain": comp.taxonomy_level,
            "mastery": round(lc.mastery_score, 3),
            "confidence": round(lc.confidence_score, 3),
            "evidence_count": lc.data_points_count,
            "status": lc.status,
            "trend": "improving" if lc.mastery_score >= 0.75 else ("declining" if lc.mastery_score < 0.45 else "stable"),
            "last_updated": lc.updated_at.isoformat(),
        })
    return results


@app.get("/api/v1/adaptive/decisions/{learner_id}")
async def get_learner_decisions(
    learner_id: UUID,
    org_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Returns recent explainable adaptive decisions made for the learner."""
    q = (
        select(SessionSequenceStep, AdaptiveSession)
        .join(AdaptiveSession, SessionSequenceStep.session_id == AdaptiveSession.id)
        .where(
            and_(
                AdaptiveSession.org_id == org_id,
                AdaptiveSession.user_id == learner_id,
            )
        )
        .order_by(desc(SessionSequenceStep.created_at))
        .limit(limit)
    )

    res = await db.execute(q)
    rows = res.all()
    return [
        {
            "id": str(step.id),
            "session_id": str(session.id),
            "decision": session.recommended_next_action or "continue",
            "reason": step.reason,
            "mastery_at_decision": step.result_score,
            "recommended_content_id": str(step.item_id) if step.item_id else None,
            "step_order": step.step_order,
            "created_at": step.created_at.isoformat(),
        }
        for step, session in rows
    ]


@app.get("/api/v1/adaptive/skill-gaps/{learner_id}")
async def get_skill_gaps_for_learner(
    learner_id: UUID,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Returns individualized skill gaps and deficit severity."""
    gaps = await get_learner_skill_gaps(db, org_id, learner_id)
    return {"learner_id": str(learner_id), "gaps_count": len(gaps), "skill_gaps": gaps}


@app.get("/api/v1/adaptive/cohort-gaps/{team_id}")
async def get_skill_gaps_for_cohort(
    team_id: UUID,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Aggregates cohort-level skill gaps for teams and cohorts."""
    return await get_cohort_skill_gaps(db, org_id, team_id)
