"""
Adaptive Sequencing Policy Engine.
Evaluates learner mastery, confidence, error patterns, and trajectory to emit deterministic pedagogical decisions.
"""
from typing import Dict, Any, Tuple
from app.core.config import settings


def evaluate_adaptive_policy(
    mastery: float,
    confidence: float,
    trend: str,
    consecutive_correct: int = 0,
    error_distribution: Dict[str, int] = None,
) -> Tuple[str, str, str]:
    """
    Evaluates learner state against the pedagogical policy rules.
    Returns: (decision, reason, recommended_difficulty)
    """
    error_distribution = error_distribution or {}

    # Check modality fatigue (same error category repeated >= 3 times)
    for err_type, count in error_distribution.items():
        if count >= 3:
            return (
                "change_modality",
                f"Learner exhibited repeated {err_type} misconceptions ({count}x). Switch pedagogical modality.",
                "intermediate",
            )

    # Fast-path acceleration (high accuracy streak)
    if consecutive_correct >= settings.skip_consecutive_correct and mastery >= settings.skip_mastery_threshold:
        return (
            "skip",
            f"Demonstrated consistent mastery ({consecutive_correct} consecutive correct answers, mastery {mastery:.2f}). Skipping introductory modules.",
            "advanced",
        )

    # Remediation policy
    if mastery < settings.remediation_threshold:
        return (
            "remediate",
            f"Mastery ({mastery:.2f}) below threshold ({settings.remediation_threshold:.2f}). Stepping down difficulty for foundational remediation.",
            "beginner",
        )

    # Advancement policy
    if mastery >= settings.advancement_mastery_threshold and confidence >= settings.advancement_confidence_threshold:
        return (
            "advance",
            f"High mastery ({mastery:.2f}) and confidence ({confidence:.2f}) reached. Advancing to next competency milestone.",
            "advanced",
        )

    # Review / revisit policy for downward trends
    if trend == "declining":
        return (
            "revisit",
            f"Declining performance trend detected despite baseline mastery ({mastery:.2f}). Re-visiting core concepts.",
            "intermediate",
        )

    # Standard progression
    return (
        "continue",
        f"Stable progression maintained (mastery: {mastery:.2f}, confidence: {confidence:.2f}). Continuing with sequence.",
        "intermediate",
    )
