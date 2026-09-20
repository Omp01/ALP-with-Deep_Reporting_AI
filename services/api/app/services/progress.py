"""
Learner progress: how far through a course a learner really is.

Two rules shape this module.

1. Progress is DERIVED, never stored as a number someone typed. A course's
   percentage is completed lesson items / published lesson items, computed from
   `content_progress` rows. `enrollments.progress_pct` is kept only as a cache of
   that result (so existing readers keep working) and is rewritten from it.

2. Completion is credited by the party that can actually know it.
     - Video, article, document: reported by the player (real playback reached the
       threshold, or the learner marked a reading as done).
     - Quiz: only a submitted attempt that passes. The client cannot claim it.
     - Assignment: only a submission. The client cannot claim it.
   Time spent is clamped to real elapsed time, so a client cannot invent hours.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContentItem, ContentProgress, Enrollment
from app.events import store as event_store

# A video or reading at or beyond this percent counts as completed.
COMPLETION_THRESHOLD = 90.0
# Most time one progress report may add. Players send a heartbeat every ~15 s.
MAX_TIME_CREDIT_SECONDS = 60
# Content whose completion the server decides, not the client.
SERVER_VERIFIED_TYPES = {"QUIZ", "ASSIGNMENT"}
PUBLISHED = "published"


# ---------------------------------------------------------------------------
# Pure helpers (unit tested)
# ---------------------------------------------------------------------------
def completion_percent(completed: int, total: int) -> float:
    """Percent of lesson items completed, one decimal; 0 when the course has none."""
    if total <= 0:
        return 0.0
    return round(min(100.0, 100.0 * completed / total), 1)


def credited_time(
    reported: int, seconds_since_last_report: Optional[float], cap: int = MAX_TIME_CREDIT_SECONDS
) -> int:
    """
    Seconds of learning time to credit for one progress report.

    Never more than the report claims, never more than `cap` (a heartbeat's worth by
    default), and (when an earlier report exists) never more than the wall-clock time
    that has actually passed since it.
    """
    credit = min(max(reported, 0), cap)
    if seconds_since_last_report is not None:
        credit = min(credit, max(0, int(seconds_since_last_report)))
    return credit


def wants_completion(status: str, percent: float) -> bool:
    return status == "completed" or percent >= COMPLETION_THRESHOLD


# ---------------------------------------------------------------------------
# Derived course progress
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CourseProgress:
    total_items: int
    completed_items: int
    time_spent_seconds: int

    @property
    def percent(self) -> float:
        return completion_percent(self.completed_items, self.total_items)


async def progress_for_courses(
    db: AsyncSession, org_id: UUID, user_id: UUID, course_ids: Iterable[UUID]
) -> Dict[UUID, CourseProgress]:
    """Derived progress for several courses in one query. Courses with no items map to zeros."""
    ids = list(course_ids)
    if not ids:
        return {}
    rows = await db.execute(
        select(
            ContentItem.course_id,
            func.count(ContentItem.id),
            func.coalesce(func.sum(case((ContentProgress.status == "completed", 1), else_=0)), 0),
            func.coalesce(func.sum(ContentProgress.time_spent_seconds), 0),
        )
        .select_from(ContentItem)
        .outerjoin(
            ContentProgress,
            and_(ContentProgress.content_item_id == ContentItem.id, ContentProgress.user_id == user_id),
        )
        .where(
            ContentItem.org_id == org_id,
            ContentItem.course_id.in_(ids),
            ContentItem.status == PUBLISHED,
        )
        .group_by(ContentItem.course_id)
    )
    result = {cid: CourseProgress(0, 0, 0) for cid in ids}
    for course_id, total, completed, seconds in rows.all():
        result[course_id] = CourseProgress(int(total), int(completed), int(seconds))
    return result


async def sync_enrollment(
    db: AsyncSession, org_id: UUID, user_id: UUID, course_id: UUID, now: Optional[datetime] = None
) -> None:
    """Rewrite the enrollment's cached percentage and status from the derived value."""
    now = now or datetime.utcnow()
    enrollment = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.org_id == org_id, Enrollment.user_id == user_id, Enrollment.course_id == course_id
            )
        )
    ).scalar_one_or_none()
    if enrollment is None:
        return

    progress = (await progress_for_courses(db, org_id, user_id, [course_id]))[course_id]
    enrollment.progress_pct = progress.percent
    enrollment.last_activity_at = now
    if progress.total_items > 0 and progress.completed_items >= progress.total_items:
        if enrollment.status != "completed":
            enrollment.status = "completed"
            enrollment.completed_at = now
    elif enrollment.status == "completed":  # new content was added after completion
        enrollment.status = "active"
        enrollment.completed_at = None


# ---------------------------------------------------------------------------
# Recording progress on one lesson item
# ---------------------------------------------------------------------------
@dataclass
class ProgressResult:
    record: ContentProgress
    started: bool
    newly_completed: bool


async def record_progress(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    item: ContentItem,
    status: str,
    percent: float,
    time_spent_seconds: int = 0,
    position_seconds: Optional[int] = None,
    verified: bool = False,
    time_credit_cap: int = MAX_TIME_CREDIT_SECONDS,
    now: Optional[datetime] = None,
    attach_session: bool = True,
) -> ProgressResult:
    """
    Record progress on one lesson item and keep everything derived from it in step.

    `verified=True` is passed only by server code that has itself established the
    fact (a passed quiz attempt, a submitted assignment). Such callers may also raise
    `time_credit_cap`, because they measured the elapsed time themselves.
    """
    now = now or datetime.utcnow()
    percent = min(max(percent, 0.0), 100.0)

    completing = wants_completion(status, percent)
    if item.content_type.upper() in SERVER_VERIFIED_TYPES and not verified:
        completing = False
        percent = min(percent, COMPLETION_THRESHOLD - 1)  # cannot self-report past the threshold

    record = (
        await db.execute(
            select(ContentProgress).where(
                ContentProgress.user_id == user_id, ContentProgress.content_item_id == item.id
            )
        )
    ).scalar_one_or_none()

    started = record is None
    was_completed = bool(record and record.status == "completed")

    if record is None:
        record = ContentProgress(
            org_id=org_id,
            user_id=user_id,
            content_item_id=item.id,
            status="not_started",
            progress_percent=0.0,
            time_spent_seconds=0,
            position_seconds=0,
            last_accessed_at=now,
            created_at=now,
        )
        db.add(record)
        elapsed: Optional[float] = None
    else:
        elapsed = (now - record.last_accessed_at).total_seconds()

    record.time_spent_seconds += credited_time(time_spent_seconds, elapsed, time_credit_cap)
    record.last_accessed_at = now
    if position_seconds is not None:
        record.position_seconds = max(0, position_seconds)

    if was_completed:
        pass  # completed stays completed at 100%
    elif completing:
        record.status = "completed"
        record.progress_percent = 100.0
        record.completed_at = now
    else:
        record.progress_percent = max(record.progress_percent, percent)
        record.status = "in_progress" if (record.progress_percent > 0 or status == "in_progress") else "not_started"
    await db.flush()

    newly_completed = record.status == "completed" and not was_completed
    payload = {"content_type": item.content_type, "title": item.title}
    refs = dict(org_id=org_id, user_id=user_id, course_id=item.course_id, module_id=item.module_id, content_id=item.id, attach_session=attach_session)
    if started:
        await event_store.record(db, event_type="content_started", payload=payload, timestamp=now, **refs)
    if newly_completed:
        # One microsecond later, so that when a start and its completion arrive in the same report
        # the history still reads "started" then "completed".
        completed = await event_store.record(
            db, event_type="content_completed", payload={**payload, "time_spent_seconds": record.time_spent_seconds},
            timestamp=now + timedelta(microseconds=1), **refs,
        )
        # The typed views of the same fact. Analytics count `content_completed`; these exist so media
        # and reading analyses can select their own kind, and point back at the event they refine.
        typed = {"VIDEO": "video_completed", "ARTICLE": "article_completed"}.get((item.content_type or "").upper())
        if typed:
            await event_store.record(
                db, event_type=typed, timestamp=now + timedelta(microseconds=2),
                payload={"derived_from": str(completed.event.id), "content_type": item.content_type,
                         "time_spent_seconds": record.time_spent_seconds}, **refs,
            )

    if item.course_id:
        await sync_enrollment(db, org_id, user_id, item.course_id, now)
    return ProgressResult(record, started, newly_completed)
