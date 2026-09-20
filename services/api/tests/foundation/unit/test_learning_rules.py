"""Pure tests for progress rules, media resolution and view helpers (no database)."""

import uuid
from datetime import datetime, timedelta

import pytest

from app.services.course_metrics import duration_minutes
from app.services.learning_views import (
    activity_label,
    choose_resume,
    item_kind,
    weak_competency_reason,
)
from app.services.media import parse_youtube_id, resolve_media
from app.services.progress import (
    COMPLETION_THRESHOLD,
    MAX_TIME_CREDIT_SECONDS,
    completion_percent,
    credited_time,
    wants_completion,
)

pytestmark = pytest.mark.unit


# --- progress -----------------------------------------------------------------
@pytest.mark.parametrize(
    "completed, total, expected",
    [(0, 0, 0.0), (0, 5, 0.0), (1, 3, 33.3), (2, 3, 66.7), (5, 5, 100.0), (7, 5, 100.0)],
)
def test_completion_percent(completed, total, expected):
    assert completion_percent(completed, total) == expected


def test_completion_threshold_boundary():
    assert not wants_completion("in_progress", COMPLETION_THRESHOLD - 0.1)
    assert wants_completion("in_progress", COMPLETION_THRESHOLD)
    assert wants_completion("completed", 0)


def test_time_credit_never_exceeds_the_heartbeat_cap():
    assert credited_time(3600, None) == MAX_TIME_CREDIT_SECONDS
    assert credited_time(15, None) == 15


def test_time_credit_never_exceeds_real_elapsed_time():
    assert credited_time(60, 4.9) == 4       # only 4 real seconds passed since the last report
    assert credited_time(60, 0) == 0
    assert credited_time(30, 500) == 30      # long gap: claim is the limit


def test_time_credit_ignores_negative_claims_and_clock_skew():
    assert credited_time(-10, None) == 0
    assert credited_time(30, -5) == 0


def test_quiz_can_be_given_a_larger_cap_by_the_server():
    assert credited_time(900, 900, cap=1800) == 900


# --- resume choice ---------------------------------------------------------------
def _ids(n):
    return [uuid.uuid4() for _ in range(n)]


def test_resume_prefers_the_most_recently_touched_in_progress_item():
    a, b, c = _ids(3)
    now = datetime(2026, 9, 20, 12, 0)
    ordered = [(a, "in_progress", now - timedelta(days=2)), (b, "completed", now), (c, "in_progress", now - timedelta(hours=1))]
    assert choose_resume(ordered) == c


def test_resume_falls_back_to_the_first_unfinished_item():
    a, b, c = _ids(3)
    ordered = [(a, "completed", None), (b, "not_started", None), (c, "not_started", None)]
    assert choose_resume(ordered) == b


def test_resume_is_none_when_everything_is_complete_or_empty():
    a, b = _ids(2)
    assert choose_resume([(a, "completed", None), (b, "completed", None)]) is None
    assert choose_resume([]) is None


# --- media -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=aJc5MuJbOr0",
        "https://youtube.com/watch?v=aJc5MuJbOr0&t=30s",
        "https://m.youtube.com/watch?v=aJc5MuJbOr0",
        "https://youtu.be/aJc5MuJbOr0",
        "https://youtu.be/aJc5MuJbOr0?si=xyz",
        "https://www.youtube.com/embed/aJc5MuJbOr0",
        "https://www.youtube.com/shorts/aJc5MuJbOr0",
        "https://www.youtube-nocookie.com/embed/aJc5MuJbOr0",
    ],
)
def test_parse_youtube_id_accepts_common_forms(url):
    assert parse_youtube_id(url) == "aJc5MuJbOr0"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "not a url",
        "javascript:alert(1)",
        "https://evil.example.com/watch?v=aJc5MuJbOr0",
        "https://www.youtube.com.evil.example.com/watch?v=aJc5MuJbOr0",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=aJc5MuJbOr0<script>",
        "ftp://www.youtube.com/watch?v=aJc5MuJbOr0",
        "https://www.youtube.com/watch",
    ],
)
def test_parse_youtube_id_rejects_everything_else(url):
    assert parse_youtube_id(url) is None


def _resolve(**overrides):
    args = dict(content_type="VIDEO", source_type="authored", content_url=None, source_url=None, file_endpoint="/f")
    args.update(overrides)
    return resolve_media(**args)


def test_resolve_prefers_youtube_from_source_url_or_content_url():
    assert _resolve(source_url="https://youtu.be/aJc5MuJbOr0").video_id == "aJc5MuJbOr0"
    assert _resolve(content_url="https://www.youtube.com/watch?v=aJc5MuJbOr0").provider == "youtube"


def test_resolve_uploads_go_through_the_authenticated_file_endpoint():
    media = _resolve(source_type="upload", content_url="org/job_lecture.pdf", file_endpoint="/api/v1/learning/content/1/file",
                     file_mime_type="application/pdf")
    assert (media.provider, media.url, media.mime_type) == ("file", "/api/v1/learning/content/1/file", "application/pdf")


def test_resolve_direct_media_urls():
    assert _resolve(content_url="https://cdn.example.com/a/b.mp4").provider == "html5_video"
    assert _resolve(content_type="AUDIO", content_url="https://cdn.example.com/a.mp3").provider == "html5_audio"


def test_resolve_returns_none_for_unrecognised_or_unsafe_urls():
    assert _resolve(content_url="https://cdn.example.com/page.html") is None
    assert _resolve(content_url="javascript:alert(1)") is None
    assert _resolve() is None


# --- helpers -----------------------------------------------------------------------
@pytest.mark.parametrize(
    "content_type, kind",
    [("VIDEO", "lesson"), ("article", "lesson"), ("DOCUMENT", "lesson"), ("QUIZ", "assessment"),
     ("ASSIGNMENT", "assignment"), ("LAB", "assignment"), ("", "lesson")],
)
def test_item_kind(content_type, kind):
    assert item_kind(content_type) == kind


def test_duration_prefers_override_then_rounds_content_up_and_never_invents():
    assert duration_minutes(90, 12345) == 90
    assert duration_minutes(None, 1201) == 21
    assert duration_minutes(None, 60) == 1
    assert duration_minutes(None, 0) is None


def test_activity_labels():
    assert activity_label("content_completed", {"title": "SQL Joins"}) == "Completed SQL Joins"
    assert activity_label("assessment_completed", {"score": 72.4}) == "Finished an assessment (score 72%)"
    assert activity_label("assessment_completed", {}) == "Finished an assessment"
    assert activity_label("question_answered", {}) is None  # too granular to list


def test_weak_competency_reason_states_the_stored_number():
    assert "42%" in weak_competency_reason("SQL Joins", 0.42)
    assert "SQL Joins" in weak_competency_reason("SQL Joins", 0.42)
