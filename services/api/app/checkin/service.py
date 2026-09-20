"""
Login check-ins: start (which returns at once while a model writes the quiz), read, submit, skip, history.

Privacy: a check-in is read and written only by its learner. The self-report scores are never included in events, in team or
organization reports, or in anything a manager or administrator can open.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.checkin import psychometric, quiz as quiz_mod, report as report_mod
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.events import store as event_store
from app.ingestion import prompts
from app.ingestion.ai import TASK_CHECKIN, brief, complete_structured
from app.ingestion.errors import AIOutputInvalid, AIUnavailable
from app.models import Checkin, Course, Enrollment, User

logger = logging.getLogger("api.checkin")
PROMPT_VERSION = "checkin_v1"
RESUME_HOURS = 3

_session_factory: Callable[[], Any] = AsyncSessionLocal
_tasks: set = set()


def set_session_factory(factory: Optional[Callable[[], Any]]) -> None:
    """Tests give the background generation the same engine the request handlers use."""
    global _session_factory
    _session_factory = factory or AsyncSessionLocal


class CheckinError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ------------------------------------------------------------------------------------------ start
async def _pick_course(db: AsyncSession, org_id: UUID, user_id: UUID, requested: Optional[UUID]) -> Optional[Course]:
    """The requested course if the learner is enrolled in it, otherwise the enrolled course checked in on least recently."""
    enrolled = (await db.execute(
        select(Course).join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user_id, Enrollment.org_id == org_id, Enrollment.status == "active", Course.org_id == org_id)
    )).scalars().all()
    if requested is not None:
        return next((c for c in enrolled if c.id == requested), None)
    if not enrolled:
        return None
    last = dict((await db.execute(
        select(Checkin.course_id, func.max(Checkin.created_at)).where(Checkin.learner_id == user_id, Checkin.org_id == org_id).group_by(Checkin.course_id)
    )).all())
    random.shuffle(enrolled)                                    # ties (never checked in) are broken at random
    return min(enrolled, key=lambda c: last.get(c.id) or datetime.min)


async def start(db: AsyncSession, org_id: UUID, user: User, course_id: Optional[UUID] = None, fresh: bool = False) -> Checkin:
    now = datetime.utcnow()
    today = (await db.execute(select(func.count()).select_from(Checkin).where(
        Checkin.learner_id == user.id, Checkin.org_id == org_id, Checkin.created_at > now - timedelta(days=1)))).scalar_one()
    unfinished = (await db.execute(select(Checkin).where(
        Checkin.learner_id == user.id, Checkin.org_id == org_id, Checkin.status.in_(["generating", "ready"]),
        Checkin.created_at > now - timedelta(hours=RESUME_HOURS)).order_by(Checkin.created_at.desc()))).scalars().all()

    if unfinished and not fresh:
        return unfinished[0]
    if today >= settings.checkin_max_per_day:
        raise CheckinError("rate_limited", f"You have started {today} check-ins in the last 24 hours, which is the limit.", 429)
    for old in unfinished:                                       # a new login replaces an abandoned check-in
        old.status, old.error_code, old.error_message = "skipped", "replaced", "Replaced by a newer check-in."

    course = await _pick_course(db, org_id, user.id, course_id)
    row = Checkin(org_id=org_id, learner_id=user.id, course_id=course.id if course else None, status="generating", created_at=now)
    if course is None:
        row.status, row.error_code = "failed", "no_course"
        row.error_message = "You are not enrolled in a course that can be checked in on." if course_id is None else "You are not enrolled in that course."
    db.add(row)
    await db.commit()
    if row.status == "generating":
        if settings.checkin_run_inline:
            await run_generation(row.id)
            await db.refresh(row)
        else:
            task = asyncio.create_task(run_generation(row.id))
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)
    return row


# ------------------------------------------------------------------------------------ generation
async def _previous(db: AsyncSession, org_id: UUID, user_id: UUID, limit: int) -> List[Checkin]:
    return list((await db.execute(select(Checkin).where(
        Checkin.learner_id == user_id, Checkin.org_id == org_id, Checkin.status == "completed"
    ).order_by(Checkin.created_at.desc()).limit(limit))).scalars().all())


async def run_generation(checkin_id: UUID) -> None:
    async with _session_factory() as db:
        row = await db.get(Checkin, checkin_id)
        if row is None or row.status != "generating":
            return
        try:
            await asyncio.wait_for(_generate(db, row), timeout=settings.checkin_generation_timeout_seconds)
        except asyncio.TimeoutError:
            await _fail(db, row, "timeout", "Writing the check-in took too long. Please try again.")
        except quiz_mod.NotEnoughMaterial as exc:
            await _fail(db, row, "no_material", str(exc))
        except AIUnavailable as exc:
            await _fail(db, row, "ai_unavailable", str(exc))
        except AIOutputInvalid as exc:
            await _fail(db, row, "ai_invalid", str(exc))
        except Exception as exc:  # never leave a check-in generating forever
            logger.exception("check-in generation failed")
            await _fail(db, row, "error", f"Something went wrong writing the check-in: {brief(exc)}"[:400])


async def _fail(db: AsyncSession, row: Checkin, code: str, message: str) -> None:
    checkin_id = row.id                                          # read before the rollback expires the instance
    await db.rollback()
    row = await db.get(Checkin, checkin_id)
    if row is not None and row.status == "generating":
        row.status, row.error_code, row.error_message = "failed", code, message
        await db.commit()


async def _generate(db: AsyncSession, row: Checkin) -> None:
    course = await db.get(Course, row.course_id)
    passages = await quiz_mod.course_passages(db, row.org_id, row.course_id)
    earlier = await _previous(db, row.org_id, row.learner_id, settings.checkin_history_avoid)
    used = {k for c in earlier if c.course_id == row.course_id for k in (c.provenance or {}).get("passages_used", [])}
    avoid_q = [q["text"] for c in earlier if c.course_id == row.course_id for q in (c.quiz or [])]
    avoid_items = [i["text"] for c in earlier for i in (c.psychometric or [])]
    subject = f"{course.title}. {(course.description or '')[:120]}"
    nonce = prompts.new_nonce()

    async def write_items():
        return await complete_structured(
            TASK_CHECKIN, psychometric.SYSTEM, psychometric.items_prompt(subject, settings.checkin_items_per_construct, avoid_items, nonce),
            psychometric.ItemsOut, max_tokens=2500, temperature=0.8)

    # Both calls finish before anything is raised, so a failure in one never leaves the other using the session while it is rolled back.
    results = await asyncio.gather(
        quiz_mod.write_quiz(db, row.org_id, course.title, passages, avoid_q, used, random.Random()), write_items(), return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    quiz_outcome, items_result = results
    if len(quiz_outcome.questions) < settings.checkin_min_questions:
        reasons = "; ".join(sorted({r["reason"] for r in quiz_outcome.rejected})[:3]) or "none were returned"
        raise AIOutputInvalid(f"Only {len(quiz_outcome.questions)} question(s) passed verification against the course material ({reasons}). Please try again.")
    items, problems = psychometric.validate_items(items_result.value.items, settings.checkin_items_per_construct)  # type: ignore[attr-defined]
    if not psychometric.complete_enough(items):
        raise AIOutputInvalid("The self-report statements were not usable: " + "; ".join(problems[:3]))

    row.quiz, row.psychometric = quiz_outcome.questions, items
    row.provenance = {
        "prompt_version": PROMPT_VERSION, "quiz_model": f"{quiz_outcome.provider}", "items_model": items_result.provider,
        "rejected_questions": quiz_outcome.rejected[:10], "item_problems": problems[:10], "passages_used": quiz_outcome.passages_used,
    }
    row.status, row.ready_at = "ready", datetime.utcnow()
    await db.commit()


# --------------------------------------------------------------------------------------- reading
def _course_block(course: Optional[Course]) -> Optional[Dict[str, Any]]:
    return {"id": str(course.id), "title": course.title} if course else None


async def view(db: AsyncSession, row: Checkin) -> Dict[str, Any]:
    """What the learner may see. The correct answers, explanations and source passages stay hidden until the check-in is submitted."""
    if row.status == "generating" and row.created_at < datetime.utcnow() - timedelta(seconds=settings.checkin_generation_timeout_seconds + 30):
        row.status, row.error_code, row.error_message = "failed", "timeout", "Writing the check-in took too long. Please try again."
        await db.commit()
    course = await db.get(Course, row.course_id) if row.course_id else None
    out: Dict[str, Any] = {
        "id": str(row.id), "status": row.status, "course": _course_block(course), "created_at": row.created_at.isoformat() + "Z",
        "completed_at": row.completed_at.isoformat() + "Z" if row.completed_at else None,
        "error": {"code": row.error_code, "message": row.error_message} if row.error_code and row.status in ("failed", "skipped") else None,
    }
    if row.status == "ready":
        out["quiz"] = [{"id": q["id"], "text": q["text"], "content_title": q.get("content_title"),
                        "options": [{"id": o["id"], "text": o["text"]} for o in q["options"]]} for q in row.quiz]
        out["self_report"] = {"statements": [{"id": i["id"], "text": i["text"]} for i in row.psychometric],
                              "scale": {"min": psychometric.SCALE_MIN, "max": psychometric.SCALE_MAX, "labels": psychometric.SCALE_LABELS},
                              "disclaimer": psychometric.DISCLAIMER}
    if row.status == "completed":
        out["report"] = row.report
        out["provenance"] = {"quiz_model": (row.provenance or {}).get("quiz_model"), "items_model": (row.provenance or {}).get("items_model"),
                             "prompt_version": (row.provenance or {}).get("prompt_version")}
    return out


async def get(db: AsyncSession, org_id: UUID, user_id: UUID, checkin_id: UUID) -> Optional[Checkin]:
    row = await db.get(Checkin, checkin_id)
    return row if row is not None and row.org_id == org_id and row.learner_id == user_id else None


async def history(db: AsyncSession, org_id: UUID, user_id: UUID, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(Checkin).where(Checkin.org_id == org_id, Checkin.learner_id == user_id)
                             .order_by(Checkin.created_at.desc()).limit(limit))).scalars().all()
    titles = {c.id: c.title for c in (await db.execute(select(Course).where(Course.id.in_([r.course_id for r in rows if r.course_id])))).scalars()} if rows else {}
    out = []
    for r in rows:
        quiz_part = ((r.report or {}).get("quiz") or {})
        out.append({
            "id": str(r.id), "status": r.status, "created_at": r.created_at.isoformat() + "Z", "course_title": titles.get(r.course_id),
            "quiz_percent": quiz_part.get("percent"), "quiz_correct": quiz_part.get("correct"), "quiz_total": quiz_part.get("total"),
            "self_report": {k: v["score"] for k, v in ((r.report or {}).get("self_report") or {}).items() if v.get("scored")} if r.status == "completed" else {},
        })
    return out


# -------------------------------------------------------------------------------------- submitting
def _clean_answers(row: Checkin, quiz_answers: Dict[str, Any], self_answers: Dict[str, Any]):
    questions = {q["id"]: {o["id"] for o in q["options"]} for q in row.quiz}
    for qid, oid in quiz_answers.items():
        if qid not in questions or (oid is not None and oid not in questions[qid]):
            raise CheckinError("invalid_answer", f"'{str(qid)[:40]}' is not a question or option of this check-in.", 422)
    statements = {i["id"] for i in row.psychometric}
    for sid, value in self_answers.items():
        if sid not in statements or isinstance(value, bool) or not isinstance(value, int) or not psychometric.SCALE_MIN <= value <= psychometric.SCALE_MAX:
            raise CheckinError("invalid_answer", f"'{str(sid)[:40]}' is not a statement of this check-in, or its rating is not {psychometric.SCALE_MIN}-{psychometric.SCALE_MAX}.", 422)
    return {k: v for k, v in quiz_answers.items() if v is not None}, dict(self_answers)


async def submit(db: AsyncSession, org_id: UUID, user: User, checkin_id: UUID, quiz_answers: Dict[str, Any], self_answers: Dict[str, Any], want_note: bool = True) -> Dict[str, Any]:
    row = (await db.execute(select(Checkin).where(Checkin.id == checkin_id, Checkin.org_id == org_id, Checkin.learner_id == user.id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise CheckinError("not_found", "Check-in not found.", 404)
    if row.status != "ready":
        raise CheckinError("not_ready", f"This check-in is {row.status} and cannot be submitted.", 409)
    quiz_answers, self_answers = _clean_answers(row, quiz_answers, self_answers)

    quiz_scores = report_mod.score_quiz(row.quiz, quiz_answers)
    earlier = await _previous(db, org_id, user.id, 1)
    previous = earlier[0] if earlier else None
    previous_self = {k: v for k, v in (((previous.report or {}).get("self_report")) or {}).items()} if previous else None
    self_scores = psychometric.score_all(row.psychometric, self_answers, previous_self, settings.checkin_change_threshold)
    previous_pct = (((previous.report or {}).get("quiz") or {}).get("percent")) if previous else None
    course = await db.get(Course, row.course_id) if row.course_id else None

    observed = report_mod.observations(quiz_scores, self_scores, previous_pct)
    note = await report_mod.coaching_note(quiz_scores, self_scores, observed, course.title if course else "") if want_note else None
    row.answers = {"quiz": quiz_answers, "self_report": self_answers}
    row.scores = {"quiz_percent": quiz_scores["percent"], "self_report": {k: v.get("score") for k, v in self_scores.items()}}
    row.report = report_mod.build_report(quiz_scores, self_scores, note, previous_pct, course.title if course else None)
    row.status, row.completed_at = "completed", datetime.utcnow()
    await event_store.record(
        db, org_id=org_id, user_id=user.id, event_type="checkin_completed", course_id=row.course_id, attach_session=False,
        payload={"checkin_id": str(row.id), "correct": quiz_scores["correct"], "total": quiz_scores["total"], "quiz_percent": quiz_scores["percent"]},
    )
    await db.commit()
    return await view(db, row)


async def skip(db: AsyncSession, org_id: UUID, user: User, checkin_id: UUID) -> Dict[str, Any]:
    row = await get(db, org_id, user.id, checkin_id)
    if row is None:
        raise CheckinError("not_found", "Check-in not found.", 404)
    if row.status in ("generating", "ready"):
        row.status, row.error_code, row.error_message = "skipped", "skipped_by_learner", "Skipped."
        await db.commit()
    return await view(db, row)
