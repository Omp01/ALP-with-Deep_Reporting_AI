"""
The deterministic mastery update (spec section 20).

    previous mastery  +  one piece of evidence  ->  new mastery

This module is pure: no database, no clock, no randomness, no model calls. The same inputs always give the same output,
so any stored update can be recomputed and checked (`service.verify`). It is the ONLY place a mastery figure is
calculated. A language model may produce the *signal* (how much evidence of the skill an answer shows); it never
produces mastery.

The method is Bayesian Knowledge Tracing with soft evidence.

Classic BKT has four numbers: the chance the skill is already known (prior), the chance it is learned on each
opportunity (learn), the chance of a wrong answer despite knowing it (slip), and the chance of a right answer without
knowing it (guess). For an answer observed as correct or incorrect, Bayes' rule gives the new probability of mastery.
Here the evidence is not always all-or-nothing (a written answer can be 0.65 right, a grader can be 87% sure), so:

    1. Adjust slip and guess for the question:
         harder question  -> a right answer is stronger evidence (lower guess), a wrong one weaker (higher slip)
         guess is 1 / number of options for a multiple-choice question when that is known
    2. Bayes posterior if the answer were fully correct (pc) and if it were fully incorrect (pi)
         pc = L(1-slip) / ( L(1-slip) + (1-L)guess )
         pi = L slip    / ( L slip    + (1-L)(1-guess) )
    3. Blend by the signal s (0..1):                      post = s*pc + (1-s)*pi
    4. Blend by the evidence weight w (0..1) so that weak evidence moves mastery little:
                                                           post_w = w*post + (1-w)*L
    5. Learning between opportunities:                     L_new = post_w + (1-post_w)*learn

where L is the previous mastery (or the prior for the first evidence) and w is the source's confidence multiplied by
a discount for repeated attempts (a second try at the same questions is weaker evidence: the learner has seen them).

Confidence is a separate number: how much evidence stands behind the estimate, not how high it is.
    confidence = n_eff / (n_eff + K)      n_eff = sum of evidence weights

Every constant is a documented parameter (docs/COMPETENCY_ENGINE.md) and is stored with each update.
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence

METHOD = "bkt_soft_v1"

FLOOR, CEILING = 0.001, 0.999


@dataclass(frozen=True)
class MasteryParams:
    prior: float = 0.20          # chance the skill is known before any evidence
    learn: float = 0.15          # chance of learning it at each opportunity
    slip: float = 0.10           # wrong answer although known (before the difficulty adjustment)
    guess: float = 0.20          # right answer although not known (before the adjustment; overridden by 1/options)
    retry_weight: float = 0.60   # multiplier on the weight for each earlier attempt (attempt 2: x0.6, attempt 3: x0.36 ...)
    confidence_k: float = 3.0    # evidence weight at which confidence reaches one half
    trend_window: int = 5        # updates back to compare for the trend
    trend_min_updates: int = 3   # fewer updates than this: "insufficient_data"
    trend_threshold: float = 0.05

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class Evidence:
    """What the update needs to know about one piece of evidence."""
    signal: float                          # 0..1
    confidence: float = 1.0                # trust in the source: 1.0 for deterministic grading or a person
    difficulty: Optional[float] = None     # 0..1; None = unknown, treated as 0.5 (no adjustment)
    attempt_number: Optional[int] = None   # None or 1 = first attempt
    guess_floor: Optional[float] = None    # chance of a right answer by guessing, when known


@dataclass(frozen=True)
class UpdateResult:
    previous_mastery: Optional[float]      # None: this was the first evidence and the prior was used
    new_mastery: float
    previous_confidence: Optional[float]
    new_confidence: float
    weight: float
    effective_evidence: float
    slip: float                            # after the difficulty adjustment
    guess: float
    posterior: float                       # step 3
    params: Dict[str, float]               # everything needed to redo the calculation


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def adjusted_slip_guess(params: MasteryParams, difficulty: Optional[float], guess_floor: Optional[float]) -> tuple:
    d = 0.5 if difficulty is None else clamp(difficulty)
    guess = params.guess if guess_floor is None else clamp(guess_floor, 0.0, 0.95)
    guess = clamp(guess * (1.5 - d), 0.01, 0.5)
    slip = clamp(params.slip * (0.5 + d), 0.01, 0.4)
    return slip, guess


def evidence_weight(params: MasteryParams, evidence: Evidence) -> float:
    attempts_before = max(0, (evidence.attempt_number or 1) - 1)
    return clamp(evidence.confidence) * (params.retry_weight ** attempts_before)


def confidence_of(effective_evidence: float, params: MasteryParams) -> float:
    return effective_evidence / (effective_evidence + params.confidence_k) if effective_evidence > 0 else 0.0


def update(
    previous_mastery: Optional[float],
    previous_effective_evidence: float,
    evidence: Evidence,
    params: MasteryParams = MasteryParams(),
) -> UpdateResult:
    """One deterministic update. `previous_mastery` None means there is no state yet: the prior is used."""
    level = params.prior if previous_mastery is None else clamp(previous_mastery, FLOOR, CEILING)
    slip, guess = adjusted_slip_guess(params, evidence.difficulty, evidence.guess_floor)
    signal = clamp(evidence.signal)
    weight = evidence_weight(params, evidence)

    posterior_correct = level * (1 - slip) / (level * (1 - slip) + (1 - level) * guess)
    posterior_incorrect = level * slip / (level * slip + (1 - level) * (1 - guess))
    posterior = signal * posterior_correct + (1 - signal) * posterior_incorrect
    weighted = weight * posterior + (1 - weight) * level
    # The chance of learning at this opportunity is scaled by the evidence weight: an answer that carries no weight (an unsure grader, a
    # repeated attempt) must not raise mastery just because it happened. Without this, a run of wrong retried answers climbed.
    new_mastery = clamp(weighted + (1 - weighted) * params.learn * weight, FLOOR, CEILING)

    effective = previous_effective_evidence + weight
    previous_confidence = None if previous_mastery is None else confidence_of(previous_effective_evidence, params)
    return UpdateResult(
        previous_mastery=None if previous_mastery is None else round(clamp(previous_mastery), 6),
        new_mastery=round(new_mastery, 6),
        previous_confidence=None if previous_confidence is None else round(previous_confidence, 6),
        new_confidence=round(confidence_of(effective, params), 6),
        weight=round(weight, 6),
        effective_evidence=round(effective, 6),
        slip=round(slip, 6),
        guess=round(guess, 6),
        posterior=round(posterior, 6),
        params=params.as_dict(),
    )


def status_of(mastery: float) -> str:
    """Words for a mastery probability. The bands are display only; nothing is decided from them."""
    if mastery < 0.30:
        return "novice"
    if mastery < 0.60:
        return "developing"
    if mastery < 0.80:
        return "competent"
    if mastery < 0.90:
        return "proficient"
    return "expert"


def trend_of(masteries_oldest_first: Sequence[float], params: MasteryParams = MasteryParams()) -> tuple:
    """
    ('improving' | 'declining' | 'stable' | 'insufficient_data', delta).

    Compares the latest mastery with the one `trend_window` updates earlier (or the first, when there are fewer).
    Needs at least `trend_min_updates` updates. The trend is a fact about stored history, never inferred from a level.
    """
    values: List[float] = list(masteries_oldest_first)
    if len(values) < params.trend_min_updates:
        return "insufficient_data", None
    reference = values[max(0, len(values) - 1 - params.trend_window)]
    delta = round(values[-1] - reference, 4)
    if delta > params.trend_threshold:
        return "improving", delta
    if delta < -params.trend_threshold:
        return "declining", delta
    return "stable", delta


def recent_accuracy(signals_weights_newest_first: Sequence[tuple], window: int = 10) -> Optional[float]:
    """Weighted mean signal over the last `window` pieces of evidence; None when there is none."""
    rows = list(signals_weights_newest_first)[:window]
    total = sum(w for _, w in rows)
    if not rows or total <= 0:
        return None
    return round(sum(s * w for s, w in rows) / total, 4)


def fold(evidences: Sequence[Evidence], params: MasteryParams = MasteryParams()) -> List[UpdateResult]:
    """Apply evidence in order from no state: the reference computation a stored chain must equal."""
    results: List[UpdateResult] = []
    mastery: Optional[float] = None
    effective = 0.0
    for evidence in evidences:
        result = update(mastery, effective, evidence, params)
        results.append(result)
        mastery, effective = result.new_mastery, result.effective_evidence
    return results
