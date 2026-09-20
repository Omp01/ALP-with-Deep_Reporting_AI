"""
The skill-gap engine (spec section 23).

A skill gap is a competency where the learner's evidenced mastery is below the target. For each gap the engine says WHY it
is one, with the actual numbers, from these signals:

    low mastery            mastery below the target for the competency's course
    low confidence         too little evidence behind the estimate to rely on it
    negative trend         mastery has fallen over recent evidence
    repeated errors        several wrong answers, and the most frequent recorded error type
    high retry rate        much of the evidence comes from second and later attempts
    long time on task      far longer than the mapped content is expected to take
    prerequisite blockage  a prerequisite competency is below the mastery it must reach

Nothing here is random, and severity is not "100 minus completion": it is a points total from documented rules. A
competency with too little evidence (fewer than `MIN_EVIDENCE` pieces) is reported as "not enough evidence", never as a
gap, so a learner is not labelled weak from a single answer.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

MIN_EVIDENCE = 2
LOW_CONFIDENCE = 0.40
REPEATED_ERRORS_AT = 3
HIGH_RETRY_RATE = 0.40
MIN_EVIDENCE_FOR_RETRY_RATE = 3
LONG_TIME_FACTOR = 2.0
DEFAULT_TARGET = 0.70

SEVERITY_BANDS = ((7, "critical"), (5, "high"), (3, "medium"), (0, "low"))


@dataclass
class Prerequisite:
    competency_id: UUID
    name: str
    required_mastery: float
    mastery: Optional[float]          # None: the prerequisite has not been assessed yet


@dataclass
class GapInput:
    competency_id: UUID
    code: str
    name: str
    mastery: float
    confidence: float
    trend: str
    trend_delta: Optional[float]
    evidence_count: int
    incorrect_count: int
    retry_count: int
    error_distribution: Dict[str, int]
    time_on_task_seconds: int
    target_mastery: float = DEFAULT_TARGET
    expected_time_seconds: int = 0
    prerequisites: Sequence[Prerequisite] = field(default_factory=tuple)
    evidence_ids: Sequence[str] = field(default_factory=tuple)      # the most recent evidence, for citation


@dataclass
class Signal:
    code: str
    description: str
    points: int
    value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class GapAssessment:
    competency_id: UUID
    code: str
    name: str
    is_gap: bool
    severity: Optional[str]
    points: int
    mastery: float
    target_mastery: float
    gap_size: float
    signals: List[Signal]
    reasons: List[str]
    evidence_ids: List[str]
    note: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "competency_id": str(self.competency_id), "code": self.code, "name": self.name, "is_gap": self.is_gap, "severity": self.severity,
            "points": self.points, "mastery": round(self.mastery, 4), "target_mastery": self.target_mastery, "gap_size": round(self.gap_size, 4),
            "signals": [s.__dict__ for s in self.signals], "reasons": self.reasons, "evidence_ids": self.evidence_ids, "note": self.note,
        }


def severity_for(points: int) -> str:
    for floor, label in SEVERITY_BANDS:
        if points >= floor:
            return label
    return "low"


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def assess(g: GapInput) -> GapAssessment:
    gap_size = round(g.target_mastery - g.mastery, 4)
    if g.evidence_count < MIN_EVIDENCE:
        return GapAssessment(
            g.competency_id, g.code, g.name, False, None, 0, g.mastery, g.target_mastery, gap_size, [], [],
            list(g.evidence_ids), note=f"Not enough evidence yet ({g.evidence_count} of {MIN_EVIDENCE} needed) to say whether this is a gap.",
        )

    signals: List[Signal] = []
    if g.mastery < g.target_mastery:
        points = 3 if gap_size >= 0.40 else 2 if gap_size >= 0.20 else 1
        signals.append(Signal("low_mastery", f"Mastery is {_pct(g.mastery)}, {_pct(gap_size)} points below the target of {_pct(g.target_mastery)}", points, g.mastery, g.target_mastery))
    is_gap = bool(signals)

    if is_gap:  # the other signals explain a gap; on their own they do not make a competency a gap
        if g.confidence < LOW_CONFIDENCE:
            signals.append(Signal("low_confidence", f"Only {g.evidence_count} pieces of evidence stand behind this estimate (confidence {g.confidence:.2f})", 1, g.confidence, LOW_CONFIDENCE))
        if g.trend == "declining":
            signals.append(Signal("negative_trend", f"Mastery has fallen by {abs(g.trend_delta or 0):.2f} over the recent evidence", 2, g.trend_delta))
        if g.incorrect_count >= REPEATED_ERRORS_AT:
            typed = {k: v for k, v in (g.error_distribution or {}).items() if k != "unknown"}
            top = max(typed.items(), key=lambda kv: kv[1]) if typed else None
            extra = f", most often {top[0].replace('_', ' ')} ({top[1]})" if top and top[1] >= 2 else ""
            signals.append(Signal("repeated_errors", f"{g.incorrect_count} incorrect answers{extra}", 2, float(g.incorrect_count), float(REPEATED_ERRORS_AT)))
        if g.evidence_count >= MIN_EVIDENCE_FOR_RETRY_RATE and g.retry_count / g.evidence_count >= HIGH_RETRY_RATE:
            signals.append(Signal("high_retry_rate", f"{g.retry_count} of {g.evidence_count} answers were second or later attempts", 1, g.retry_count / g.evidence_count, HIGH_RETRY_RATE))
        if g.expected_time_seconds > 0 and g.time_on_task_seconds > LONG_TIME_FACTOR * g.expected_time_seconds:
            signals.append(Signal("long_time_on_task", f"{round(g.time_on_task_seconds / 60)} minutes spent, against about {round(g.expected_time_seconds / 60)} expected", 1,
                                  float(g.time_on_task_seconds), float(LONG_TIME_FACTOR * g.expected_time_seconds)))
        blocked = [p for p in g.prerequisites if p.mastery is not None and p.mastery < p.required_mastery]
        for p in blocked:
            signals.append(Signal("prerequisite_blocked", f"Prerequisite \"{p.name}\" is at {_pct(p.mastery or 0)}, below the {_pct(p.required_mastery)} it must reach", 2, p.mastery, p.required_mastery))

    points = sum(s.points for s in signals)
    reasons = [s.description for s in signals]
    unassessed = [p for p in g.prerequisites if p.mastery is None]
    note = f"Prerequisite \"{unassessed[0].name}\" has not been assessed yet." if is_gap and unassessed else None
    return GapAssessment(
        g.competency_id, g.code, g.name, is_gap, severity_for(points) if is_gap else None, points if is_gap else 0, g.mastery, g.target_mastery,
        gap_size, signals if is_gap else [], reasons if is_gap else [], list(g.evidence_ids), note=note,
    )


def cohort_summary(rows: Sequence[Dict[str, Any]], target_by_competency: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Team-level gaps from learners' states. Each row: {competency_id, name, user_id, mastery, trend, evidence_count}.

    Reports counts, never a single average that hides who is behind: "N of M assessed learners are below the target".
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["competency_id"]), []).append(row)
    out: List[Dict[str, Any]] = []
    for competency_id, members in grouped.items():
        assessed = [m for m in members if m["evidence_count"] >= MIN_EVIDENCE]
        if not assessed:
            continue
        target = target_by_competency.get(competency_id, DEFAULT_TARGET)
        below = [m for m in assessed if m["mastery"] < target]
        out.append({
            "competency_id": competency_id, "name": members[0]["name"], "code": members[0].get("code"), "target_mastery": target,
            "assessed_learners": len(assessed), "learners_below_target": len(below),
            "share_below_target": round(len(below) / len(assessed), 4), "learners_declining": sum(1 for m in assessed if m["trend"] == "declining"),
            "evidence_count": sum(m["evidence_count"] for m in assessed), "lowest_mastery": round(min(m["mastery"] for m in assessed), 4),
            "median_mastery": round(sorted(m["mastery"] for m in assessed)[len(assessed) // 2], 4),
        })
    return sorted(out, key=lambda r: (-r["share_below_target"], -r["learners_below_target"], r["name"]))
