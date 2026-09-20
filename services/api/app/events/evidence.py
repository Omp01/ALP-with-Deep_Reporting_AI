"""
Per-answer evidence that is derived by rule, never assigned at random.

Error types (spec section 17): conceptual_misunderstanding, procedural_error,
calculation_error, misreading, careless_error, knowledge_gap, unknown.

For an objective (multiple-choice) question the platform holds no information about WHY a
wrong option was chosen: options carry no error tags. Inferring a cause from timing or from
which distractor was picked would be a guess presented as evidence, so the rule is:

    correct answer            -> no error type
    incorrect (or blank)      -> "unknown"

A richer classification needs evidence the platform does not have yet (tagged distractors,
or the grading agent's reading of an open-ended answer in Phase 5). It is added where that
evidence exists, and until then "unknown" is the true answer.
"""

from typing import Optional, Tuple

ERROR_TYPES = (
    "conceptual_misunderstanding", "procedural_error", "calculation_error", "misreading",
    "careless_error", "knowledge_gap", "unknown",
)


def error_type_for(*, is_correct: bool, answered: bool, question_type: str = "multiple_choice") -> Optional[str]:
    if is_correct:
        return None
    return "unknown"


def response_time(reported_ms: Optional[int], attempt_elapsed_ms: Optional[int]) -> Tuple[Optional[int], Optional[str]]:
    """
    A player-reported time on one question, held to the attempt's real elapsed time.

    Returns (milliseconds, source). Nothing reported -> (None, None): unknown stays unknown.
    A report longer than the whole attempt cannot be true, so it is capped and labelled.
    """
    if reported_ms is None or reported_ms < 0:
        return None, None
    if attempt_elapsed_ms is not None and reported_ms > attempt_elapsed_ms:
        return max(attempt_elapsed_ms, 0), "client_clamped"
    return reported_ms, "client"
