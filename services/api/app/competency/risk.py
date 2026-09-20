"""
The risk engine (spec section 49).

Risk is explained, not scored by a model. Each factor below is a documented rule over stored data; a factor that fires adds
its points and a sentence containing the real figures; the total maps to a level. The 0..1 `risk_score` is only the point
total scaled (total / 10, capped), kept so lists can be sorted; the reasons are the substance.

    persistent low mastery     competencies with enough evidence and confidence, still below 0.50
    negative trend             competencies whose mastery has fallen over recent evidence
    repeated failed attempts   failed, fully graded attempts at the same assessment
    high retries               much of the evidence comes from second and later attempts
    long time on task          far longer than the mapped content is expected to take
    inactive learning          no learning event for days while enrolled (real event timestamps)
    prerequisite gaps          a competency whose prerequisite is below the mastery it must reach

No factor uses completion percentage or any generated number.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

LOW_MASTERY = 0.50
LOW_MASTERY_MIN_EVIDENCE = 3
LOW_MASTERY_MIN_CONFIDENCE = 0.40
HIGH_RETRY_RATE = 0.40
HIGH_RETRY_MIN_EVIDENCE = 5
LONG_TIME_FACTOR = 2.0
INACTIVE_DAYS = 7
VERY_INACTIVE_DAYS = 14
SCORE_SCALE = 10.0
LEVEL_BANDS = ((8, "critical"), (5, "high"), (3, "medium"), (0, "low"))

ACTIONS = {
    "persistent_low_mastery": "Arrange targeted support on the named competencies before the learner moves on.",
    "negative_trend": "Check in with the learner: their recent answers are getting worse, not better.",
    "repeated_failed_attempts": "Review why the assessment is failing (the material, the questions, or a prerequisite) before another attempt.",
    "high_retries": "Offer worked examples or hints; the learner is relying on repeated attempts.",
    "long_time_on_task": "Look for a specific obstacle: the time spent is well beyond what the content is expected to need.",
    "inactive_learning": "Contact the learner: there has been no learning activity for some time.",
    "prerequisite_gaps": "Address the prerequisite competency first; later material depends on it.",
}


@dataclass
class CompetencyFact:
    competency_id: str
    name: str
    mastery: float
    confidence: float
    trend: str
    trend_delta: Optional[float]
    evidence_count: int
    retry_count: int
    time_on_task_seconds: int
    expected_time_seconds: int
    evidence_ids: Sequence[str] = field(default_factory=tuple)
    blocked_by: Sequence[str] = field(default_factory=tuple)      # names of prerequisites below their required mastery


@dataclass
class RiskInput:
    competencies: Sequence[CompetencyFact]
    failed_attempts: Dict[str, int]                # assessment title -> failed, fully graded attempts
    days_since_activity: Optional[float]           # None: no learning event on record
    days_enrolled: float


@dataclass
class Factor:
    code: str
    description: str
    points: int
    value: Optional[float] = None
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class RiskAssessment:
    level: str
    points: int
    score: float
    factors: List[Factor]
    actions: List[str]
    note: Optional[str] = None

    def details(self) -> List[Dict[str, Any]]:
        return [f.__dict__ for f in self.factors]


def level_for(points: int) -> str:
    for floor, label in LEVEL_BANDS:
        if points >= floor:
            return label
    return "low"


def _names(items: Sequence[str], limit: int = 3) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def assess(data: RiskInput) -> RiskAssessment:
    factors: List[Factor] = []
    facts = list(data.competencies)

    low = [c for c in facts if c.mastery < LOW_MASTERY and c.evidence_count >= LOW_MASTERY_MIN_EVIDENCE and c.confidence >= LOW_MASTERY_MIN_CONFIDENCE]
    if low:
        worst = min(low, key=lambda c: c.mastery)
        factors.append(Factor("persistent_low_mastery", f"{len(low)} competenc{'y' if len(low) == 1 else 'ies'} below {LOW_MASTERY:.2f} with enough evidence: "
                              + _names([f"{c.name} ({c.mastery:.2f})" for c in sorted(low, key=lambda c: c.mastery)]),
                              3 if len(low) >= 2 else 2, worst.mastery, [i for c in low for i in c.evidence_ids][:6]))

    declining = [c for c in facts if c.trend == "declining"]
    if declining:
        factors.append(Factor("negative_trend", f"Mastery is falling in {len(declining)} competenc{'y' if len(declining) == 1 else 'ies'}: "
                              + _names([f"{c.name} ({c.trend_delta:+.2f})" for c in declining]),
                              3 if len(declining) >= 2 else 2, min((c.trend_delta or 0) for c in declining), [i for c in declining for i in c.evidence_ids][:6]))

    repeated = {title: n for title, n in data.failed_attempts.items() if n >= 2}
    if repeated:
        title, n = max(repeated.items(), key=lambda kv: kv[1])
        factors.append(Factor("repeated_failed_attempts", f"{n} failed attempts at \"{title}\"" + (f" (and repeated failures on {len(repeated) - 1} other assessment{'s' if len(repeated) > 2 else ''})" if len(repeated) > 1 else ""),
                              2 if n >= 3 else 1, float(n)))

    evidence_total = sum(c.evidence_count for c in facts)
    retries = sum(c.retry_count for c in facts)
    if evidence_total >= HIGH_RETRY_MIN_EVIDENCE and retries / evidence_total >= HIGH_RETRY_RATE:
        factors.append(Factor("high_retries", f"{retries} of {evidence_total} answers ({round(100 * retries / evidence_total)}%) were second or later attempts", 1, retries / evidence_total))

    spent = sum(c.time_on_task_seconds for c in facts)
    expected = sum(c.expected_time_seconds for c in facts)
    if expected > 0 and spent > LONG_TIME_FACTOR * expected:
        factors.append(Factor("long_time_on_task", f"{round(spent / 60)} minutes spent against about {round(expected / 60)} expected for the mapped content", 1, float(spent)))

    if data.days_since_activity is None:
        if data.days_enrolled >= INACTIVE_DAYS:
            factors.append(Factor("inactive_learning", f"No learning activity recorded in the {int(data.days_enrolled)} days since enrolment", 3, data.days_enrolled))
    elif data.days_since_activity >= INACTIVE_DAYS:
        factors.append(Factor("inactive_learning", f"No learning activity for {int(data.days_since_activity)} days", 3 if data.days_since_activity >= VERY_INACTIVE_DAYS else 2, data.days_since_activity))

    blocked = [c for c in facts if c.blocked_by]
    if blocked:
        factors.append(Factor("prerequisite_gaps", "Prerequisite below the required mastery for: "
                              + _names([f"{c.name} (needs {c.blocked_by[0]})" for c in blocked]), 2, float(len(blocked))))

    points = sum(f.points for f in factors)
    note = None
    if not facts and data.days_since_activity is None:
        note = "No evidence has been recorded for this learner in this course yet, so most risk factors cannot be assessed."
    return RiskAssessment(level=level_for(points), points=points, score=round(min(1.0, points / SCORE_SCALE), 3), factors=factors,
                          actions=[ACTIONS[f.code] for f in factors], note=note)
