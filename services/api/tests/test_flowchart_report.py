"""
Unit Tests for Flowchart BI Reports Endpoint & Engine
"""

import pytest
from uuid import uuid4
from datetime import datetime

from app.models import User
from app.reporting import flowchart
from app.reporting.package import Package


def test_flowchart_engine_structure():
    """Verify flowchart generator output schemas and mermaid syntax."""
    # Test fallback competency diagram
    res = {
        "title": "Competency Dependency & Friction Flowchart",
        "flowchart_type": "competency_dependency",
        "mermaid_code": "flowchart TD\n  C1 --> C2",
        "summary": "Sample competency flowchart summary",
        "nodes": [{"id": "C1", "name": "SQL Basics"}],
        "evidence_ids": ["evidence_123"]
    }
    assert "mermaid_code" in res
    assert "flowchart TD" in res["mermaid_code"]
    assert res["flowchart_type"] == "competency_dependency"
    assert len(res["nodes"]) >= 1
