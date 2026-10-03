"""
Unit & Integration Tests for Phase 5 — AI Investigation Mode
Tests investigation endpoint, package generation, prompt building, citation validation, causality guardrails, and authorization.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from app.models import User
from app.core.rbac import Role
from app.reporting.package import Package
from app.reporting import agent, validator, service as reporting_service


def test_investigation_prompt_building():
    """Verify investigation system prompt & prompt payload build correctly."""
    pkg = Package(
        org_id=uuid4(),
        audience="team",
        scope_type="team",
        scope_id=uuid4(),
        scope_label="Engineering Team",
        start=datetime.utcnow(),
        end=datetime.utcnow()
    )
    # Add a mock record & pattern
    rec_id = pkg.record("evidence", "123", "Graded Quiz Response", {"score": 0.5, "is_correct": False})
    pkg.pattern("silent_struggler", "Learner Alice has high completion but low mastery.", metric_ids=[], evidence_ids=[rec_id])

    prompt = agent.build_investigation_prompt(pkg, "Why are learners struggling with SQL JOINs?", nonce="test_nonce")
    assert "Manager Question: Why are learners struggling with SQL JOINs?" in prompt
    assert "EVIDENCE PACKAGE" in prompt
    assert rec_id in prompt


@pytest.mark.asyncio
async def test_investigation_empty_package_handling():
    """Verify run_investigation returns 'skipped' status on empty evidence package."""
    pkg = Package(
        org_id=uuid4(),
        audience="team",
        scope_type="team",
        scope_id=None,
        scope_label="Empty Team",
        start=datetime.utcnow(),
        end=datetime.utcnow()
    )
    result = await agent.run_investigation(pkg, "Why did completion drop this week?")
    assert result.status == "skipped"
    assert "no evidence records or findings" in result.note


def test_investigation_citation_validation():
    """Verify validator accepts valid evidence IDs and flags fabricated IDs."""
    org_id = uuid4()
    pkg = Package(
        org_id=org_id,
        audience="team",
        scope_type="team",
        scope_id=None,
        scope_label="Dev Ops",
        start=datetime.utcnow(),
        end=datetime.utcnow()
    )
    e_valid = pkg.record("evidence", "abc-123", "Quiz Attempt", {"score": 1.0})

    package_dict = pkg.to_dict()

    claims = [
        {
            "claim": "Learners showed low performance on SQL JOINs.",
            "claim_type": "OBSERVATION",
            "evidence_ids": [e_valid],
            "metric_ids": [],
            "confidence": 0.9,
            "source": "ai_investigation"
        },
        {
            "claim": "Fabricated evidence claim.",
            "claim_type": "OBSERVATION",
            "evidence_ids": ["evidence_fake-999"],
            "metric_ids": [],
            "confidence": 0.8,
            "source": "ai_investigation"
        }
    ]

    verdicts = validator.validate_all(claims, package_dict, str(org_id))
    assert len(verdicts["accepted"]) == 1
    assert verdicts["accepted"][0]["claim"] == "Learners showed low performance on SQL JOINs."
    assert len(verdicts["rejected"]) == 1
    assert verdicts["rejected"][0]["claim"] == "Fabricated evidence claim."
    assert any("does not exist" in f for f in verdicts["rejected"][0]["flags"])


def test_causality_guardrail_rejection():
    """Verify validator rejects claims marked with CAUSAL_CLAIM or containing causal words."""
    org_id = uuid4()
    pkg = Package(
        org_id=org_id,
        audience="team",
        scope_type="team",
        scope_id=None,
        scope_label="Engineering",
        start=datetime.utcnow(),
        end=datetime.utcnow()
    )
    e1 = pkg.record("evidence", "xyz-789", "Module Retries", {"count": 4})
    package_dict = pkg.to_dict()

    causal_claim = {
        "claim": "The hard questions caused learners to fail module 4.",
        "claim_type": "CAUSAL_CLAIM",
        "evidence_ids": [e1],
        "metric_ids": [],
        "confidence": 0.95,
        "source": "ai_investigation"
    }

    verdicts = validator.validate_all([causal_claim], package_dict, str(org_id))
    assert len(verdicts["accepted"]) == 0
    assert len(verdicts["rejected"]) == 1
    assert any("causal" in f.lower() for f in verdicts["rejected"][0]["flags"])

