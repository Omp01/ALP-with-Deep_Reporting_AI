"""
Centralized Assessment & Flashcard Scoring Engine.

Implements mathematically explainable, auditable scoring policies:
- Attempt-decay scoring for video flashcards: fewer attempts receive higher marks.
- Versioned formula audit snapshots stored per submission.
- Dynamic normalized overall score weighting across Quiz, Assignment, and Flashcard.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

# Version identifiers for auditing
SCORING_FORMULA_ID = "attempt_decay_v1"
SCORING_FORMULA_VERSION = "1.0.0"

# Default configuration parameters
DEFAULT_RETRY_PENALTY_P = 0.25
DEFAULT_MIN_SCORE_FLOOR_PCT = 0.20

DEFAULT_OVERALL_WEIGHTS = {
    "quiz": 0.40,
    "assignment": 0.40,
    "flashcard": 0.20,
}


@dataclass
class FlashcardScoreBreakdown:
    score: float
    max_marks: float
    attempt_number: int
    attempt_factor: float
    accuracy_factor: float
    penalty_p: float
    formula_id: str
    formula_version: str
    formula_expression: str
    reason: str
    raw_details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_flashcard_score(
    max_marks: float,
    attempt_number: int,
    is_correct: bool,
    penalty_p: float = DEFAULT_RETRY_PENALTY_P,
    min_floor_pct: float = DEFAULT_MIN_SCORE_FLOOR_PCT,
    accuracy_override: Optional[float] = None,
) -> FlashcardScoreBreakdown:
    """
    Computes attempt-decay score for a flashcard checkpoint:
    
        Score = Max Marks * Attempt Factor * Accuracy Factor
        Attempt Factor = 1 / (1 + P * (A - 1))
        
    Where:
        A = attempt number (>= 1)
        P = configurable retry penalty (default 0.25)
        Accuracy Factor = 1.0 (correct) or 0.0 (incorrect) or partial override (0..1)
    """
    eff_attempt = max(1, attempt_number)
    eff_penalty = max(0.0, penalty_p)
    
    # Attempt factor: 1 / (1 + P * (A - 1))
    attempt_factor = round(1.0 / (1.0 + eff_penalty * (eff_attempt - 1)), 4)
    
    if accuracy_override is not None:
        accuracy_factor = max(0.0, min(1.0, float(accuracy_override)))
    else:
        accuracy_factor = 1.0 if is_correct else 0.0

    formula_expression = (
        f"{max_marks:.1f} × [1 / (1 + {eff_penalty} × ({eff_attempt} - 1))] × {accuracy_factor:.1f}"
    )

    if not is_correct and accuracy_factor == 0.0:
        final_score = 0.0
        reason = (
            f"Incorrect answer on attempt {eff_attempt}. "
            f"No marks awarded (0.00 / {max_marks:.2f})."
        )
    else:
        raw_score = max_marks * attempt_factor * accuracy_factor
        # Floor ensures learner still gets at least a floor percentage for eventual correctness
        floor_score = max_marks * min_floor_pct * accuracy_factor
        final_score = round(max(raw_score, floor_score), 2)
        
        if eff_attempt == 1:
            reason = (
                f"Full marks awarded on first attempt (100% accuracy factor): "
                f"{final_score:.2f} / {max_marks:.2f}."
            )
        else:
            reason = (
                f"Correct answer achieved on attempt {eff_attempt}. "
                f"Applied configured retry penalty P={eff_penalty} (Attempt Factor: {attempt_factor:.4f}): "
                f"{final_score:.2f} / {max_marks:.2f}."
            )

    raw_details = {
        "formula_id": SCORING_FORMULA_ID,
        "formula_version": SCORING_FORMULA_VERSION,
        "max_marks": max_marks,
        "attempt_number": eff_attempt,
        "penalty_p": eff_penalty,
        "attempt_factor": attempt_factor,
        "accuracy_factor": accuracy_factor,
        "formula_expression": formula_expression,
        "marks_awarded": final_score,
        "reason": reason,
    }

    return FlashcardScoreBreakdown(
        score=final_score,
        max_marks=max_marks,
        attempt_number=eff_attempt,
        attempt_factor=attempt_factor,
        accuracy_factor=accuracy_factor,
        penalty_p=eff_penalty,
        formula_id=SCORING_FORMULA_ID,
        formula_version=SCORING_FORMULA_VERSION,
        formula_expression=formula_expression,
        reason=reason,
        raw_details=raw_details,
    )


def calculate_overall_assessment_score(
    quiz_avg: Optional[float],
    assignment_avg: Optional[float],
    flashcard_avg: Optional[float],
    custom_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Computes the composite Overall Assessment Score across Quiz, Assignment, and Flashcard.
    Dynamically normalizes weights over the components that exist in the learner's curriculum
    so the total effective weight is always 100% (1.0).
    """
    base_weights = custom_weights or DEFAULT_OVERALL_WEIGHTS
    
    components = {}
    active_weights = {}

    if quiz_avg is not None:
        components["quiz"] = round(quiz_avg, 2)
        active_weights["quiz"] = base_weights.get("quiz", 0.40)

    if assignment_avg is not None:
        components["assignment"] = round(assignment_avg, 2)
        active_weights["assignment"] = base_weights.get("assignment", 0.40)

    if flashcard_avg is not None:
        components["flashcard"] = round(flashcard_avg, 2)
        active_weights["flashcard"] = base_weights.get("flashcard", 0.20)

    if not components:
        return {
            "overall_score": 0.0,
            "weights_used": {},
            "components": {},
        }

    total_weight = sum(active_weights.values())
    if total_weight <= 0:
        total_weight = 1.0

    normalized_weights = {
        k: round(w / total_weight, 4) for k, w in active_weights.items()
    }

    overall = sum(components[k] * normalized_weights[k] for k in components)

    return {
        "overall_score": round(overall, 2),
        "weights_used": normalized_weights,
        "components": components,
    }
