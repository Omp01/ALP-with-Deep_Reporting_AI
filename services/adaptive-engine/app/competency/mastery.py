"""
Competency Mastery Calculation Module.
Implements the multi-factor weighted evidence formula, confidence scoring, and trend evaluation.
"""
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import numpy as np
from app.core.config import settings


DIFFICULTY_WEIGHTS = {
    "beginner": 0.8,
    "intermediate": 1.0,
    "advanced": 1.25,
}


def calculate_recency_factor(last_updated: Optional[datetime], current_time: Optional[datetime] = None) -> float:
    """
    Calculates exponential decay based on elapsed hours.
    Fresh activity within 24h = ~1.0; 7 days without activity decays to ~0.65.
    """
    if not last_updated:
        return 1.0
    now = current_time or datetime.utcnow()
    hours = max(0.0, (now - last_updated).total_seconds() / 3600.0)
    # Half-life of approx 168 hours (7 days)
    decay_rate = 0.0041
    return float(math.exp(-decay_rate * hours))


def calculate_bkt_mastery(
    prior_p_l: float,
    observations: List[bool],
    p_transit: float = 0.15,
    p_guess: float = 0.20,
    p_slip: float = 0.10,
) -> float:
    """
    Computes Bayesian Knowledge Tracing (Corbett & Anderson BKT) probability of mastery.
    """
    p_l = prior_p_l
    for obs in observations:
        if obs:
            # P(L|obs=correct) = P(L)*(1-S) / (P(L)*(1-S) + (1-P(L))*G)
            numerator = p_l * (1.0 - p_slip)
            denominator = numerator + (1.0 - p_l) * p_guess
        else:
            # P(L|obs=incorrect) = P(L)*S / (P(L)*S + (1-P(L))*(1-G))
            numerator = p_l * p_slip
            denominator = numerator + (1.0 - p_l) * (1.0 - p_guess)

        p_l_given_obs = numerator / max(1e-6, denominator)
        # Transition: P(L_t) = P(L|obs) + (1 - P(L|obs)) * P(T)
        p_l = p_l_given_obs + (1.0 - p_l_given_obs) * p_transit

    return float(max(0.0, min(1.0, p_l)))


def calculate_mastery(
    recent_attempts: List[Dict[str, Any]],
    current_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Computes mastery score from recent learner attempts using Bayesian Knowledge Tracing
    combined with the multi-factor weighted formula:
    mastery = (
        w_correct * correctness_score
      + w_diff    * difficulty_bonus
      + w_recency * recency_factor
      - w_error   * repeated_error_penalty
      + w_consist * consistency_bonus
    ) / normalizer
    """
    if not recent_attempts:
        return {
            "mastery": 0.0,
            "bkt_mastery": 0.0,
            "recent_accuracy": 0.0,
            "avg_response_time_ms": 0.0,
            "retry_rate": 0.0,
            "error_distribution": {},
        }

    # 1. Correctness score
    correct_count = sum(1 for a in recent_attempts if a.get("correct") is True)
    total_count = len(recent_attempts)
    correctness_score = correct_count / total_count

    # 2. Difficulty bonus
    diff_scores = [
        DIFFICULTY_WEIGHTS.get(a.get("difficulty", "intermediate").lower(), 1.0)
        for a in recent_attempts
    ]
    # Normalize difficulty relative to 1.0 baseline
    difficulty_bonus = min(1.0, np.mean(diff_scores) / 1.25)

    # 3. Recency factor
    timestamps = [
        a["timestamp"] if isinstance(a["timestamp"], datetime)
        else datetime.fromisoformat(str(a["timestamp"]))
        for a in recent_attempts if "timestamp" in a
    ]
    latest_ts = max(timestamps) if timestamps else None
    recency_factor = calculate_recency_factor(latest_ts, current_time)

    # 4. Repeated error penalty
    errors = [a.get("error_type") for a in recent_attempts if a.get("correct") is False and a.get("error_type")]
    error_distribution: Dict[str, int] = {}
    for err in errors:
        error_distribution[err] = error_distribution.get(err, 0) + 1

    max_repeated_err = max(error_distribution.values()) if error_distribution else 0
    repeated_error_penalty = (max_repeated_err / total_count) if total_count > 0 else 0.0

    # 5. Consistency bonus (1.0 - variance of correctness windows)
    scores = [1.0 if a.get("correct") is True else 0.0 for a in recent_attempts]
    std_dev = float(np.std(scores)) if len(scores) > 1 else 0.2
    consistency_bonus = max(0.0, 1.0 - std_dev)

    # Weighted combination
    w_sum = (
        settings.w_correct
        + settings.w_diff
        + settings.w_recency
        + settings.w_consist
    )
    raw_mastery = (
        settings.w_correct * correctness_score
        + settings.w_diff * difficulty_bonus
        + settings.w_recency * recency_factor
        - settings.w_error * repeated_error_penalty
        + settings.w_consist * consistency_bonus
    )
    normalized_mastery = max(0.0, min(1.0, raw_mastery / w_sum))

    # 6. Bayesian Knowledge Tracing
    bkt_score = calculate_bkt_mastery(
        prior_p_l=0.1,
        observations=[bool(a.get("correct")) for a in recent_attempts],
    )
    # Blend 60% Multi-Factor + 40% BKT
    blended_mastery = 0.60 * normalized_mastery + 0.40 * bkt_score

    # Latency & retry metrics
    response_times = [a["duration_ms"] for a in recent_attempts if a.get("duration_ms")]
    avg_latency = float(np.mean(response_times)) if response_times else 0.0

    retried_count = sum(1 for a in recent_attempts if a.get("attempt_number", 1) > 1)
    retry_rate = retried_count / total_count

    return {
        "mastery": round(float(blended_mastery), 4),
        "bkt_mastery": round(float(bkt_score), 4),
        "recent_accuracy": round(float(correctness_score), 4),
        "avg_response_time_ms": round(avg_latency, 1),
        "retry_rate": round(float(retry_rate), 4),
        "error_distribution": error_distribution,
    }


def calculate_confidence(evidence_count: int) -> float:
    """Confidence scales asymptotically with evidence volume."""
    return round(min(1.0, evidence_count / settings.required_evidence_count), 4)


def determine_trend(recent_scores: List[float]) -> str:
    """
    Evaluates trajectory across recent assessment performances.
    Returns: 'improving', 'stable', or 'declining'.
    """
    if len(recent_scores) < 3:
        return "stable"
    
    # Linear slope across indexed scores
    x = np.arange(len(recent_scores))
    y = np.array(recent_scores)
    slope = float(np.polyfit(x, y, 1)[0])

    if slope > 0.05:
        return "improving"
    elif slope < -0.05:
        return "declining"
    return "stable"
