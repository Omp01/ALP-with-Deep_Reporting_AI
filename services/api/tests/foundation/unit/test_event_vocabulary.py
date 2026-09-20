"""
The event vocabulary, payload validation, evidence rules, cursors and client-time bounds:
pure logic, no database.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1.events import bound_client_time
from app.events import evidence, queries
from app.events.vocabulary import (
    DEPRECATED, HELD_FROM_LEGACY_ENGINE, LEARNER, MAX_PAYLOAD_BYTES, SERVER, SPECS, VocabularyError, check_references,
    learner_types, normalise, published_to_stream, spec_for, validate_payload,
)
from shared.events.types import EventType

NOW = datetime(2026, 9, 21, 12, 0, 0)


# ----------------------------------------------------------------------------- vocabulary
def test_every_current_event_type_has_a_policy_and_only_legacy_names_do_not():
    unspecified = {t.value for t in EventType} - set(SPECS)
    assert unspecified == DEPRECATED, "a new EventType needs an entry in app/events/vocabulary.py"


def test_the_spec_vocabulary_is_present():
    wanted = {
        "lesson_opened", "video_started", "video_progress", "video_completed", "article_opened", "article_completed",
        "assessment_started", "question_shown", "question_answered", "assessment_completed", "answer_submitted",
        "answer_graded", "retry_started", "hint_requested", "assignment_opened", "assignment_submitted",
        "assignment_graded", "adaptive_decision_made", "competency_updated", "recommendation_generated",
    }
    assert wanted <= set(SPECS)


def test_a_browser_can_report_interaction_but_never_evidence():
    assert set(learner_types()) == {
        "lesson_opened", "video_started", "video_paused", "video_resumed", "video_progress", "article_opened",
        "question_shown", "hint_requested", "assignment_opened",
    }
    for evidence_type in ("question_answered", "assessment_completed", "content_completed", "assignment_graded",
                          "competency_updated", "answer_graded", "session_completed"):
        assert SPECS[evidence_type].source == SERVER


@pytest.mark.parametrize("old, new", [("question_viewed", "question_shown"), ("answer_retried", "retry_started"),
                                      ("video_played", "video_resumed"), ("  LESSON_OPENED ", "lesson_opened")])
def test_legacy_names_are_accepted_and_stored_under_the_current_name(old, new):
    assert normalise(old) == new
    spec_for(normalise(old))


@pytest.mark.parametrize("name, code", [("article_read", "deprecated_event_type"), ("made_up", "unknown_event_type"), ("", "unknown_event_type")])
def test_unknown_and_retired_types_are_refused(name, code):
    with pytest.raises(VocabularyError) as info:
        spec_for(normalise(name))
    assert info.value.code == code


def test_references_a_type_needs_are_enforced():
    with pytest.raises(VocabularyError) as info:
        check_references("question_answered", {"assessment_id": uuid.uuid4()})
    assert info.value.code == "missing_reference" and "question_id" in str(info.value)
    check_references("question_answered", {"assessment_id": uuid.uuid4(), "question_id": uuid.uuid4()})
    check_references("session_started", {})


def test_the_legacy_mastery_handler_is_not_fed_events_it_misreads():
    """Audit C1/C2: it reads a `correct` key these events do not carry, so they are stored but not streamed to it."""
    assert HELD_FROM_LEGACY_ENGINE == {"question_answered", "assignment_submitted"}
    assert not published_to_stream("question_answered") and not published_to_stream("assignment_submitted")
    assert published_to_stream("content_completed") and published_to_stream("assessment_completed") and published_to_stream("lesson_opened")
    assert not published_to_stream("made_up")


# ------------------------------------------------------------------------------- payloads
def test_learner_payloads_are_strict():
    assert validate_payload("lesson_opened", {}) == {"source": "direct"}
    assert validate_payload("video_progress", {"position_seconds": 30, "percent": 12.5})["percent"] == 12.5
    for bad in ({"position_seconds": -1, "percent": 5}, {"position_seconds": 5, "percent": 101}, {"position_seconds": 5},
                {"position_seconds": 5, "percent": 5, "extra": "smuggled"}):
        with pytest.raises(VocabularyError) as info:
            validate_payload("video_progress", bad)
        assert info.value.code == "invalid_payload"


def test_the_error_names_the_offending_field():
    with pytest.raises(VocabularyError) as info:
        validate_payload("lesson_opened", {"source": "carrier-pigeon"})
    assert "source" in str(info.value)


def test_server_payloads_are_checked_for_what_evidence_needs_but_may_carry_more():
    attempt = str(uuid.uuid4())
    good = {"attempt_id": attempt, "attempt_number": 1, "is_correct": False, "points_awarded": 0.0, "answered": True,
            "question_type": "multiple_choice", "future_field": "kept"}
    stored = validate_payload("question_answered", good)
    assert stored["future_field"] == "kept" and stored["difficulty"] is None and stored["response_time_ms"] is None
    with pytest.raises(VocabularyError):
        validate_payload("question_answered", {k: v for k, v in good.items() if k != "is_correct"})


def test_payloads_are_bounded_and_must_be_objects():
    with pytest.raises(VocabularyError) as info:
        validate_payload("recommendation_generated", {"blob": "x" * (MAX_PAYLOAD_BYTES + 1)})
    assert info.value.code == "payload_too_large"
    with pytest.raises(VocabularyError):
        validate_payload("recommendation_generated", ["not", "an", "object"])  # type: ignore[arg-type]


def test_stored_payloads_are_json_safe():
    stored = validate_payload("recommendation_generated", {"id": uuid.uuid4(), "when": NOW})
    assert isinstance(stored["id"], str) and isinstance(stored["when"], str)


# ----------------------------------------------------------------------------- evidence
def test_a_correct_answer_has_no_error_type_and_a_wrong_one_is_honestly_unknown():
    assert evidence.error_type_for(is_correct=True, answered=True) is None
    assert evidence.error_type_for(is_correct=False, answered=True) == "unknown"
    assert evidence.error_type_for(is_correct=False, answered=False) == "unknown"


def test_error_types_are_not_assigned_from_timing_or_position():
    """No heuristic guesses a cause: the same wrong answer is 'unknown' however fast it was."""
    results = {evidence.error_type_for(is_correct=False, answered=True, question_type=t) for t in ("multiple_choice", "true_false")}
    assert results == {"unknown"}


@pytest.mark.parametrize("reported, elapsed, expected", [
    (None, 60_000, (None, None)),
    (4_000, 60_000, (4_000, "client")),
    (90_000, 60_000, (60_000, "client_clamped")),
    (-5, 60_000, (None, None)),
    (5_000, None, (5_000, "client")),
])
def test_response_time_is_held_to_real_elapsed_time(reported, elapsed, expected):
    assert evidence.response_time(reported, elapsed) == expected


# --------------------------------------------------------------------------- client time
def test_client_timestamps_are_believed_only_when_plausible():
    assert bound_client_time(None, NOW) == NOW
    assert bound_client_time(NOW - timedelta(minutes=5), NOW) == NOW - timedelta(minutes=5)
    assert bound_client_time(NOW + timedelta(seconds=30), NOW) == NOW + timedelta(seconds=30)      # small skew is fine
    assert bound_client_time(NOW + timedelta(hours=3), NOW) == NOW                                  # future: server time
    assert bound_client_time(NOW - timedelta(days=3), NOW) == NOW                                   # long ago: server time


def test_timezone_aware_client_timestamps_are_converted_to_naive_utc():
    aware = datetime(2026, 9, 21, 14, 30, tzinfo=timezone(timedelta(hours=2)))
    assert bound_client_time(aware, datetime(2026, 9, 21, 12, 31)) == datetime(2026, 9, 21, 12, 30)


# ----------------------------------------------------------------------------- cursors
def test_cursors_round_trip_and_reject_garbage():
    event_id = uuid.uuid4()
    stamp = datetime(2026, 9, 21, 12, 0, 0, 123456)
    assert queries.decode_cursor(queries.encode_cursor(stamp, event_id)) == (stamp, event_id)
    for bad in ("", "not-base64!!", "e30", queries.encode_cursor(stamp, event_id)[:-6]):
        with pytest.raises(queries.QueryError):
            queries.decode_cursor(bad)
