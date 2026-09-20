"""Small pure helpers for derived course figures."""

from typing import Optional


def duration_minutes(override: Optional[int], total_seconds: int) -> Optional[int]:
    """
    Real duration of a course in minutes, or None when it cannot be known.

    An explicit author override wins. Otherwise it is the recorded content length
    rounded up, and a course with no timed content reports None rather than a
    made-up figure.
    """
    if override is not None:
        return override
    return -(-total_seconds // 60) if total_seconds > 0 else None
