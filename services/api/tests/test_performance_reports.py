"""
Tests for Learner & Manager Performance Reports,
Score Transparency, and Attempt Decay Logic.
"""

import pytest
from uuid import uuid4
from datetime import datetime

from app.schemas.performance_reports import (
    LearnerPerformanceReport,
    ManagerCohortPerformanceReport,
    QuestionAttemptItem,
    TopicMasteryItem,
)
from app.schemas.video_checkpoint import (
    CheckpointRemediation,
    VideoCheckpointAnswerResponse,
)
from app.services.scoring import (
    calculate_flashcard_score,
    calculate_overall_assessment_score,
    DEFAULT_MIN_SCORE_FLOOR_PCT,
)


def test_score_floor_enforcement():
    """Verify minimum score floor prevents score from dropping below configured floor when eventually correct."""
    # Attempt 50 with penalty 0.25 would ordinarily decay to 1 / (1 + 12.25) ~ 0.075 (0.75 pts)
    # With floor pct = 0.20 of 10.0, floor is 2.0 pts
    score_res = calculate_flashcard_score(
        max_marks=10.0,
        attempt_number=50,
        is_correct=True,
        penalty_p=0.25,
        min_floor_pct=0.20,
    )
    assert score_res.score == 2.0
    assert score_res.attempt_number == 50
    assert score_res.raw_details["marks_awarded"] == 2.0


def test_remediation_schema_structure():
    """Verify CheckpointRemediation schema attributes and serialization."""
    remediation = CheckpointRemediation(
        topic="Python Generator Functions",
        video_title="Deep Dive: Python Iterators & Generators",
        content_item_id=uuid4(),
        timestamp_start_seconds=125.0,
        timestamp_end_seconds=180.0,
        section_label="02:05 - 03:00",
        explanation="Generators yield values lazily rather than loading them into memory.",
        action_url="/learner/learning?item_id=test&start=125",
    )
    assert remediation.topic == "Python Generator Functions"
    assert remediation.section_label == "02:05 - 03:00"
    assert remediation.timestamp_start_seconds == 125.0


def test_flashcard_answer_response_schema():
    """Verify VideoCheckpointAnswerResponse with score details and remediation."""
    remediation = CheckpointRemediation(
        topic="Closures in JavaScript",
        video_title="Advanced JS Scope",
        content_item_id=uuid4(),
        timestamp_start_seconds=45.0,
        timestamp_end_seconds=90.0,
        section_label="00:45 - 01:30",
    )
    ans = VideoCheckpointAnswerResponse(
        checkpoint_id=uuid4(),
        is_correct=False,
        status="incorrect",
        selected_option_id="B",
        correct_option_id="A",
        score=0.0,
        max_score=10.0,
        attempt_number=1,
        formula_id="attempt_decay_v1",
        formula_version="1.0.0",
        calculation_details={"reason": "Incorrect on attempt 1"},
        reason="Incorrect on attempt 1",
        remediation=remediation,
        explanation="Closures retain outer scope references.",
        all_checkpoints_completed=False,
    )
    assert ans.is_correct is False
    assert ans.score == 0.0
    assert ans.remediation is not None
    assert ans.remediation.topic == "Closures in JavaScript"


def test_learner_performance_report_schema():
    """Verify LearnerPerformanceReport schema instantiation and topic mastery aggregation."""
    user_id = uuid4()
    topic_items = [
        TopicMasteryItem(
            topic="Asynchronous Python",
            mastery_percent=92.5,
            total_questions=4,
            correct_count=4,
            average_attempts=1.0,
            status="strong",
        ),
        TopicMasteryItem(
            topic="Memory Management",
            mastery_percent=55.0,
            total_questions=3,
            correct_count=1,
            average_attempts=2.33,
            status="weak",
        ),
    ]

    report = LearnerPerformanceReport(
        user_id=user_id,
        user_name="Omprakash Pandey",
        user_email="omprakash@example.com",
        overall_score=84.5,
        quiz_score=88.0,
        assignment_score=85.0,
        flashcard_score=80.0,
        weights_used={"quiz": 0.40, "assignment": 0.40, "flashcard": 0.20},
        first_attempt_accuracy=78.5,
        average_attempts=1.28,
        total_items_attempted=7,
        questions_requiring_retries=2,
        topic_mastery=topic_items,
        strong_topics=["Asynchronous Python"],
        weak_topics=["Memory Management"],
        improvement_trend="improving",
        attempt_history=[],
    )

    assert report.overall_score == 84.5
    assert len(report.topic_mastery) == 2
    assert report.strong_topics == ["Asynchronous Python"]
    assert report.weak_topics == ["Memory Management"]


def test_overall_score_empty_components():
    """Verify overall score handles empty assessment components gracefully."""
    res = calculate_overall_assessment_score(
        quiz_avg=None,
        assignment_avg=None,
        flashcard_avg=None,
    )
    assert res["overall_score"] == 0.0
    assert res["components"] == {}
