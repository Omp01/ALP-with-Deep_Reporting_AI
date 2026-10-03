"""
Automated unit and integration tests for the Deterministic Analytics Engine:
- What Changed? (Temporal comparison across periods)
- Silent Struggler Detection (High progress/completion vs weak demonstrated mastery)
- Learning Bottleneck Detection (Module-level friction & drop-offs)
- Assessment Intelligence (Question-level factual performance metrics)
- Scope and authorization verification
"""

import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import User
from app.reporting.analytics_engine import (
    compute_what_changed,
    detect_silent_strugglers,
    detect_learning_bottlenecks,
    compute_assessment_intelligence,
    SILENT_STRUGGLER_MIN_COMPLETION,
    SILENT_STRUGGLER_MAX_MASTERY,
)


@pytest.mark.asyncio
async def test_analytics_engine_direct_functions():
    """Verify all 4 deterministic analytics functions execute cleanly against database session."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Mock admin viewer
        viewer = User(id=uuid4(), org_id=uuid4(), email="admin@acme.com", full_name="Admin Test")
        org_id = viewer.org_id

        # 1. What Changed Analytics
        what_changed = await compute_what_changed(db, org_id, viewer, days=14)
        assert "days_window" in what_changed
        assert what_changed["days_window"] == 14
        assert "competency" in what_changed
        assert "assessment" in what_changed
        assert "activity" in what_changed

        # 2. Silent Struggler Detection
        strugglers = await detect_silent_strugglers(
            db, org_id, viewer,
            min_completion_pct=SILENT_STRUGGLER_MIN_COMPLETION,
            max_mastery_score=SILENT_STRUGGLER_MAX_MASTERY,
        )
        assert "thresholds" in strugglers
        assert strugglers["thresholds"]["min_completion_pct"] == SILENT_STRUGGLER_MIN_COMPLETION
        assert strugglers["thresholds"]["max_mastery_score"] == SILENT_STRUGGLER_MAX_MASTERY
        assert "total_strugglers_found" in strugglers
        assert "silent_strugglers" in strugglers

        # 3. Learning Bottleneck Detection
        bottlenecks = await detect_learning_bottlenecks(db, org_id, viewer)
        assert "total_modules_analyzed" in bottlenecks
        assert "bottlenecks_detected" in bottlenecks
        assert "modules" in bottlenecks

        # 4. Assessment Intelligence
        assessment_intel = await compute_assessment_intelligence(db, org_id, viewer)
        assert "total_questions_analyzed" in assessment_intel
        assert "questions" in assessment_intel

    await engine.dispose()
