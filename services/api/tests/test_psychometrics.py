"""
Unit Tests for Psychometric Learning Assessment and Reporting Framework.

Validates:
1. Response normalization across Likert 5, Likert 7, binary, slider, and reverse-keying.
2. Confidence-Performance Gap and Calibration Quadrant classification.
3. Learning Evidence Index (LEI) calculation with dynamic weight re-balancing.
4. Content Friction Index (CFI) computation and topic friction flagging.
"""

import pytest
from app.services.psychometrics_service import (
    normalize_response,
    classify_calibration_quadrant,
    calculate_learning_evidence_index,
    compute_content_friction_index,
)


def test_response_normalization_likert_5():
    """Test 5-point Likert scale normalization to 0-100."""
    assert normalize_response({"value": 1}, scale_type="likert_5", scale_min=1, scale_max=5) == 0.0
    assert normalize_response({"value": 3}, scale_type="likert_5", scale_min=1, scale_max=5) == 50.0
    assert normalize_response({"value": 5}, scale_type="likert_5", scale_min=1, scale_max=5) == 100.0


def test_response_normalization_reverse_keying():
    """Test reverse-keyed normalization: inverted scale."""
    assert normalize_response({"value": 1}, scale_type="likert_5", scale_min=1, scale_max=5, is_reverse_keyed=True) == 100.0
    assert normalize_response({"value": 3}, scale_type="likert_5", scale_min=1, scale_max=5, is_reverse_keyed=True) == 50.0
    assert normalize_response({"value": 5}, scale_type="likert_5", scale_min=1, scale_max=5, is_reverse_keyed=True) == 0.0


def test_response_normalization_likert_7():
    """Test 7-point Likert scale normalization."""
    assert normalize_response({"value": 1}, scale_type="likert_7", scale_min=1, scale_max=7) == 0.0
    assert normalize_response({"value": 4}, scale_type="likert_7", scale_min=1, scale_max=7) == 50.0
    assert normalize_response({"value": 7}, scale_type="likert_7", scale_min=1, scale_max=7) == 100.0


def test_response_normalization_binary():
    """Test binary yes/no normalization."""
    assert normalize_response({"value": "yes"}, scale_type="binary") == 100.0
    assert normalize_response({"value": "true"}, scale_type="binary") == 100.0
    assert normalize_response({"value": 1}, scale_type="binary") == 100.0
    assert normalize_response({"value": "no"}, scale_type="binary") == 0.0
    assert normalize_response({"value": 0}, scale_type="binary") == 0.0


def test_response_normalization_slider():
    """Test continuous slider normalization."""
    assert normalize_response({"value": 73.5}, scale_type="slider") == 73.5
    assert normalize_response({"value": 120}, scale_type="slider") == 100.0
    assert normalize_response({"value": -10}, scale_type="slider") == 0.0


def test_calibration_quadrant_calibrated_mastery():
    """Confidence high (>70), Performance high (>70), gap within +/- 20."""
    gap, quadrant, rec = classify_calibration_quadrant(confidence=85.0, performance=82.0)
    assert gap == 3.0
    assert quadrant == "calibrated_mastery"
    assert "Strong self-awareness" in rec


def test_calibration_quadrant_blind_spot():
    """Confidence high, Performance low -> Gap > +15."""
    gap, quadrant, rec = classify_calibration_quadrant(confidence=90.0, performance=55.0)
    assert gap == 35.0
    assert quadrant == "blind_spot"
    assert "higher than objective mastery" in rec


def test_calibration_quadrant_underestimated_competence():
    """Performance high, Confidence low -> Gap < -15."""
    gap, quadrant, rec = classify_calibration_quadrant(confidence=50.0, performance=85.0)
    assert gap == -35.0
    assert quadrant == "underestimated_competence"
    assert "exceeds subjective confidence" in rec


def test_calibration_quadrant_accurate_struggle():
    """Performance low, Confidence low, gap within +/- 20."""
    gap, quadrant, rec = classify_calibration_quadrant(confidence=40.0, performance=45.0)
    assert gap == -5.0
    assert quadrant == "accurate_struggle"
    assert "Targeted concept reviews" in rec


def test_calculate_learning_evidence_index_all_components():
    """Verify LEI weighted sum calculation when all 5 components are present."""
    lei, details = calculate_learning_evidence_index(
        overall_score=80.0,
        faa=90.0,
        flashcard_score=70.0,
        assignment_score=85.0,
        confidence_gap=10.0, # alignment: max(0, 100 - |10|*2) = 80.0
    )
    # Expected components:
    # Knowledge: 80 * 0.35 = 28.0
    # FAA: 90 * 0.25 = 22.5
    # Retention: 70 * 0.15 = 10.5
    # Application: 85 * 0.15 = 12.75
    # Alignment: 80 * 0.10 = 8.0
    # Total = 28.0 + 22.5 + 10.5 + 12.75 + 8.0 = 81.75 -> round(81.8)
    assert abs(lei - 81.8) < 0.2
    assert details["formula_version"] == "1.0.0"
    assert details["components"]["knowledge_evidence"]["raw_value"] == 80.0
    assert details["components"]["alignment_evidence"]["raw_value"] == 80.0


def test_calculate_learning_evidence_index_dynamic_rebalancing():
    """Verify LEI rebalances weights cleanly when flashcards or assignments are absent."""
    lei, details = calculate_learning_evidence_index(
        overall_score=80.0,
        faa=80.0,
        flashcard_score=None,
        assignment_score=None,
        confidence_gap=0.0, # alignment = 100
    )
    # Active weights: Knowledge (0.35), FAA (0.25), Alignment (0.10) => sum = 0.70
    # Rebalanced weights:
    # Knowledge: 0.35 / 0.70 = 0.50 -> 80 * 0.5 = 40.0
    # FAA: 0.25 / 0.70 = 0.3571 -> 80 * 0.3571 = 28.57
    # Alignment: 0.10 / 0.70 = 0.1429 -> 100 * 0.1429 = 14.29
    # Total = 40.0 + 28.57 + 14.29 = 82.86 -> round(82.9)
    assert abs(lei - 82.9) < 0.2
    assert details["weights"]["retention"] == 0.0
    assert details["weights"]["application"] == 0.0
    assert abs(sum(details["weights"].values()) - 1.0) < 0.001


def test_content_friction_index():
    """Verify Content Friction Index computation and friction flag."""
    # High friction: High cognitive effort (80), low perceived understanding (30), low accuracy (40), retries (3)
    high_cfi, is_flagged, breakd = compute_content_friction_index(
        avg_cognitive_effort=80.0,
        avg_perceived_understanding=30.0,
        avg_accuracy=40.0,
        avg_attempts=3.0,
    )
    assert high_cfi > 70.0
    assert is_flagged is True

    # Low friction: Low cognitive effort (20), high understanding (90), high accuracy (95), attempts (1)
    low_cfi, is_not_flagged, breakd_low = compute_content_friction_index(
        avg_cognitive_effort=20.0,
        avg_perceived_understanding=90.0,
        avg_accuracy=95.0,
        avg_attempts=1.0,
    )
    assert low_cfi < 30.0
    assert is_not_flagged is False
