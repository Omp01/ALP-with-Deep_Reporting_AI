import pytest
from app.services.scoring import (
    calculate_flashcard_score,
    calculate_overall_assessment_score,
    SCORING_FORMULA_ID,
    SCORING_FORMULA_VERSION,
)

def test_attempt_decay_values():
    # Attempt 1 -> 10.0
    s1 = calculate_flashcard_score(max_marks=10.0, attempt_number=1, is_correct=True, penalty_p=0.25)
    assert s1.score == 10.0
    assert s1.attempt_factor == 1.0
    assert s1.accuracy_factor == 1.0
    assert s1.formula_id == SCORING_FORMULA_ID
    assert s1.formula_version == SCORING_FORMULA_VERSION

    # Attempt 2 -> 8.0
    s2 = calculate_flashcard_score(max_marks=10.0, attempt_number=2, is_correct=True, penalty_p=0.25)
    assert s2.score == 8.0
    assert s2.attempt_factor == 0.8
    assert "Applied configured retry penalty" in s2.reason

    # Attempt 3 -> 6.67
    s3 = calculate_flashcard_score(max_marks=10.0, attempt_number=3, is_correct=True, penalty_p=0.25)
    assert s3.score == 6.67
    assert s3.attempt_factor == 0.6667

    # Attempt 4 -> 5.71
    s4 = calculate_flashcard_score(max_marks=10.0, attempt_number=4, is_correct=True, penalty_p=0.25)
    assert s4.score == 5.71

def test_incorrect_attempt():
    s_wrong = calculate_flashcard_score(max_marks=10.0, attempt_number=1, is_correct=False)
    assert s_wrong.score == 0.0
    assert s_wrong.accuracy_factor == 0.0
    assert "No marks awarded" in s_wrong.reason

def test_overall_score_normalization():
    # Standard 3 components: Quiz (40%), Assignment (40%), Flashcard (20%)
    res = calculate_overall_assessment_score(quiz_avg=80.0, assignment_avg=90.0, flashcard_avg=100.0)
    # 80 * 0.4 + 90 * 0.4 + 100 * 0.2 = 32 + 36 + 20 = 88.0
    assert res["overall_score"] == 88.0

    # Only Quiz and Flashcard present: weights rebalance (40/60 -> 66.7%, 20/60 -> 33.3%)
    res_no_assign = calculate_overall_assessment_score(quiz_avg=90.0, assignment_avg=None, flashcard_avg=60.0)
    assert sum(res_no_assign["weights_used"].values()) == pytest.approx(1.0, 0.01)
    # 90 * (4/6) + 60 * (2/6) = 60 + 20 = 80.0
    assert res_no_assign["overall_score"] == 80.0
