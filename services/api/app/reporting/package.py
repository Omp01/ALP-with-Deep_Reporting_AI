"""
The evidence package (spec sections 25-26): structured, tenant-scoped, every record with an id.

A reporting agent never receives a database dump. It receives one of these: `records` (things that happened or are true, each
with an id and the time it applies to), `metrics` (numbers computed here, with their definition and the records they come from)
and `patterns` (deterministic findings over the metrics, each already carrying its evidence ids and a sentence whose numbers are
the metric values). The citation validator checks every claim against the same object, and the object is stored with the report
so citations can be opened later exactly as they were.

Ids look like `evidence_<uuid>`, `update_<uuid>`, `state_<uuid>`, `session_<uuid>`, `decision_<uuid>`, `risk_<uuid>`,
`content_<uuid>`, `question_<uuid>`, `metric_<key>`, `pattern_<n>`.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

CLAIM_TYPES = ("OBSERVATION", "CORRELATION", "PLAUSIBLE_EXPLANATION", "CAUSAL_CLAIM")
EVIDENCE_CONFIDENCE_K = 3.0


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def evidence_confidence(evidence_count: int) -> float:
    """How much evidence stands behind a finding: n / (n + K). Not a probability that the finding is true."""
    return round(evidence_count / (evidence_count + EVIDENCE_CONFIDENCE_K), 3) if evidence_count > 0 else 0.0


@dataclass
class Package:
    org_id: UUID
    audience: str
    scope_type: str
    scope_id: Optional[UUID]
    scope_label: str
    start: datetime
    end: datetime
    records: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    patterns: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)            # things the report cannot say and why (missing data)

    def record(self, kind: str, key: Any, label: str, data: Dict[str, Any], occurred_at: Optional[datetime] = None, learner_id: Optional[UUID] = None) -> str:
        rid = f"{kind}_{key}"
        self.records[rid] = {"id": rid, "type": kind, "org_id": str(self.org_id), "label": label, "occurred_at": _iso(occurred_at),
                             "learner_id": str(learner_id) if learner_id else None, "data": json.loads(json.dumps(data, default=_iso))}
        return rid

    def metric(self, key: str, name: str, value: Any, unit: str, definition: str, derived_from: Iterable[str] = ()) -> str:
        mid = f"metric_{key}"
        self.metrics[mid] = {"id": mid, "name": name, "value": value, "unit": unit, "definition": definition, "derived_from": [d for d in derived_from if d in self.records]}
        return mid

    def pattern(self, kind: str, statement: str, metric_ids: Iterable[str], evidence_ids: Iterable[str], claim_type: str = "OBSERVATION", subject: Optional[str] = None,
                priority: int = 5) -> str:
        ids = [e for e in dict.fromkeys(evidence_ids) if e in self.records]
        pid = f"pattern_{len(self.patterns) + 1}"
        self.patterns.append({"id": pid, "kind": kind, "statement": statement, "claim_type": claim_type, "metric_ids": [m for m in metric_ids if m in self.metrics],
                              "evidence_ids": ids, "subject": subject, "priority": priority, "confidence": evidence_confidence(len(ids))})
        return pid

    def scope(self) -> Dict[str, Any]:
        return {"tenant_id": str(self.org_id), "audience": self.audience, "scope_type": self.scope_type, "scope_id": str(self.scope_id) if self.scope_id else None,
                "scope_label": self.scope_label, "period_start": _iso(self.start), "period_end": _iso(self.end)}

    def to_dict(self) -> Dict[str, Any]:
        return {"report_scope": self.scope(), "records": self.records, "metrics": self.metrics, "patterns": self.patterns, "notes": self.notes}

    def content_hash(self) -> str:
        """Identical evidence gives an identical hash, so an identical request can reuse the stored report."""
        stable = self.to_dict()
        stable["report_scope"] = {k: v for k, v in stable["report_scope"].items() if k not in ("period_start", "period_end")}
        return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()

    def compact(self, max_records: int = 60) -> Dict[str, Any]:
        """What the language model sees: the patterns, the metrics, and the records those cite, trimmed to fit."""
        cited: List[str] = []
        for p in sorted(self.patterns, key=lambda p: p["priority"]):
            cited.extend(p["evidence_ids"])
        for m in self.metrics.values():
            cited.extend(m["derived_from"])
        keep = list(dict.fromkeys(cited))[:max_records]
        return {"report_scope": self.scope(), "patterns": self.patterns, "metrics": list(self.metrics.values()),
                "records": {rid: {"type": self.records[rid]["type"], "label": self.records[rid]["label"], "occurred_at": self.records[rid]["occurred_at"], "data": self.records[rid]["data"]}
                            for rid in keep}, "notes": self.notes}


def pct(value: float) -> str:
    return f"{round(value * 100)}%"
