"""
Publishing reviewed content.

Nothing an administrator has not seen reaches learners. Publishing applies exactly the
decisions made in review:

  * competencies marked "create" are created (with a code that is unique in the tenant),
    those marked "link" are attached, those marked "skip" are ignored;
  * the content is mapped to those competencies (and the module and course to the ones
    they did not already develop);
  * APPROVED question candidates become a real quiz (`Quiz` + questions + options), presented
    in the course as a quiz lesson item linked through `quizzes.content_item_id`;
  * the content item becomes `published`.

Publishing again after more questions are approved appends them to the same quiz.
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Competency,
    ContentCompetency,
    ContentItem,
    CourseCompetency,
    IngestionJob,
    Module,
    ModuleCompetency,
    QuestionCandidate,
    Quiz,
    QuizOption,
    QuizQuestion,
)

MINUTES_PER_QUESTION = 1.5
MIN_QUIZ_MINUTES = 5
DEFAULT_TARGET_MASTERY = 0.8


@dataclass
class Readiness:
    can_publish: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PublishResult:
    competencies_created: int = 0
    competencies_linked: int = 0
    questions_published: int = 0
    quiz_item_id: Optional[UUID] = None
    already_published: bool = False


def has_presentable_content(item: ContentItem) -> bool:
    """Would a learner see something? A lesson with nothing to show must not be published."""
    kind = (item.content_type or "").upper()
    if kind in ("VIDEO", "AUDIO"):
        return bool(item.content_url or item.source_url)
    if kind == "DOCUMENT":
        return bool(item.content_url or item.raw_text or item.text_content)
    return bool((item.text_content or item.raw_text or "").strip())


async def readiness(db: AsyncSession, item: ContentItem) -> Readiness:
    blockers: List[str] = []
    warnings: List[str] = []

    if item.status == "processing":
        blockers.append("Processing is still running.")
    if not (item.title or "").strip():
        blockers.append("The content needs a title.")
    if not has_presentable_content(item):
        blockers.append("There is nothing for a learner to see yet (no media, text or document).")

    counts = dict(
        (await db.execute(
            select(QuestionCandidate.status, func.count()).where(QuestionCandidate.content_item_id == item.id).group_by(QuestionCandidate.status)
        )).all()
    )
    analysis = item.analysis or {}
    if not analysis.get("objectives"):
        warnings.append("No learning objectives yet. Learners will see none on the course page.")
    if not any(c.get("action") in ("link", "create") for c in analysis.get("competencies", [])):
        warnings.append("No competencies are attached, so this content will not contribute evidence to any skill.")
    if not counts.get("approved", 0) and not counts.get("published", 0):
        warnings.append("No approved questions, so no quiz will be created.")
    if counts.get("pending", 0):
        warnings.append(f"{counts['pending']} generated question(s) have not been reviewed and will not be published.")

    return Readiness(can_publish=not blockers, blockers=blockers, warnings=warnings)


async def _unique_code(db: AsyncSession, org_id: UUID, wanted: str) -> str:
    code, n = wanted, 2
    while (await db.execute(select(Competency.id).where(Competency.org_id == org_id, func.lower(Competency.code) == code.lower()))).first():
        code, n = f"{wanted}-{n}", n + 1
    return code


async def _apply_competencies(db: AsyncSession, item: ContentItem, module: Module, result: PublishResult) -> Dict[str, UUID]:
    """Create/link per the reviewed decisions. Returns competency name -> id for the questions."""
    analysis = dict(item.analysis or {})
    resolved: List[Dict[str, Any]] = []
    ids_by_name: Dict[str, UUID] = {}

    for entry in analysis.get("competencies", []):
        entry = dict(entry)
        action = entry.get("action")
        competency: Optional[Competency] = None

        if action == "link" and entry.get("competency_id"):
            competency = (await db.execute(
                select(Competency).where(Competency.id == UUID(entry["competency_id"]), Competency.org_id == item.org_id)
            )).scalar_one_or_none()
            if competency is None:  # linked to something that no longer exists: treat as new
                action = entry["action"] = "create"

        if action == "create":
            code = await _unique_code(db, item.org_id, entry.get("code") or f"general.{uuid.uuid4().hex[:6]}")
            competency = Competency(
                org_id=item.org_id, code=code, name=entry["name"], description=entry.get("description") or None,
                taxonomy_level=entry.get("bloom_level") or "understand", domain=entry.get("domain"),
                difficulty=float(entry.get("difficulty", 0.5)),
            )
            db.add(competency)
            await db.flush()
            result.competencies_created += 1
            entry.update(action="link", competency_id=str(competency.id), code=competency.code, created_at_publish=True)
        elif competency is not None:
            result.competencies_linked += 1

        if competency is not None:
            ids_by_name[entry["name"]] = competency.id
            await _map_competency(db, item, module, competency)
        resolved.append(entry)

    analysis["competencies"] = resolved
    item.analysis = analysis
    return ids_by_name


async def _map_competency(db: AsyncSession, item: ContentItem, module: Module, competency: Competency) -> None:
    if not (await db.execute(select(ContentCompetency).where(
            ContentCompetency.content_item_id == item.id, ContentCompetency.competency_id == competency.id))).first():
        db.add(ContentCompetency(content_item_id=item.id, competency_id=competency.id, weight=1.0))
    if not (await db.execute(select(ModuleCompetency).where(
            ModuleCompetency.module_id == module.id, ModuleCompetency.competency_id == competency.id))).first():
        db.add(ModuleCompetency(module_id=module.id, competency_id=competency.id, weight=1.0))
    if not (await db.execute(select(CourseCompetency).where(
            CourseCompetency.course_id == module.course_id, CourseCompetency.competency_id == competency.id))).first():
        db.add(CourseCompetency(course_id=module.course_id, competency_id=competency.id,
                                target_mastery=DEFAULT_TARGET_MASTERY, is_primary=False))


async def _publish_questions(
    db: AsyncSession, item: ContentItem, module: Module, ids_by_name: Dict[str, UUID], approved: List[QuestionCandidate],
    result: PublishResult,
) -> None:
    if not approved:
        return

    metadata = dict(item.item_metadata or {})
    quiz: Optional[Quiz] = None
    quiz_item: Optional[ContentItem] = None
    if metadata.get("quiz_content_item_id"):
        quiz_item = await db.get(ContentItem, UUID(metadata["quiz_content_item_id"]))
        if quiz_item is not None:
            quiz = (await db.execute(select(Quiz).where(Quiz.content_item_id == quiz_item.id))).scalar_one_or_none()

    if quiz is None:
        next_order = (await db.execute(select(func.coalesce(func.max(ContentItem.order_index), 0)).where(ContentItem.module_id == module.id))).scalar() + 1
        minutes = max(MIN_QUIZ_MINUTES, math.ceil(len(approved) * MINUTES_PER_QUESTION))
        quiz_item = ContentItem(
            org_id=item.org_id, course_id=module.course_id, module_id=module.id,
            title=f"Check your understanding: {item.title}"[:255], content_type="QUIZ",
            description=f"Questions on \"{item.title}\".", status="published", order_index=next_order,
            duration_seconds=minutes * 60, source_type="authored",
        )
        db.add(quiz_item)
        await db.flush()
        quiz = Quiz(
            org_id=item.org_id, course_id=module.course_id, module_id=module.id, content_item_id=quiz_item.id,
            title=quiz_item.title, description=quiz_item.description, time_limit_mins=minutes,
            passing_score=70.0, max_attempts=3, is_adaptive=False,
        )
        db.add(quiz)
        await db.flush()
        metadata["quiz_content_item_id"] = str(quiz_item.id)
        item.item_metadata = metadata

    existing = (await db.execute(select(func.count()).select_from(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id))).scalar() or 0
    for offset, candidate in enumerate(approved):
        competency_id = candidate.competency_id or ids_by_name.get(candidate.competency_name or "")
        question = QuizQuestion(
            quiz_id=quiz.id, competency_id=competency_id, question_text=candidate.question_text,
            question_type=candidate.question_type or "multiple_choice", points=10, order_index=existing + offset, explanation=candidate.explanation,
            difficulty=candidate.difficulty, expected_answer=candidate.expected_answer, rubric=candidate.rubric,
        )
        db.add(question)
        await db.flush()
        for index, option in enumerate(candidate.options):
            db.add(QuizOption(question_id=question.id, option_text=option["text"], is_correct=bool(option["is_correct"]), order_index=index))
        candidate.status = "published"
        candidate.published_question_id = question.id
        candidate.competency_id = competency_id
        result.questions_published += 1
    result.quiz_item_id = quiz_item.id


async def publish_content(db: AsyncSession, item: ContentItem, module: Module, user_id: UUID) -> PublishResult:
    """Apply the reviewed decisions and publish. Caller has already checked `readiness`."""
    result = PublishResult(already_published=item.status == "published")

    ids_by_name = await _apply_competencies(db, item, module, result)

    approved = list((await db.execute(
        select(QuestionCandidate).where(QuestionCandidate.content_item_id == item.id, QuestionCandidate.status == "approved")
        .order_by(QuestionCandidate.created_at)
    )).scalars())
    await _publish_questions(db, item, module, ids_by_name, approved, result)

    item.status = "published"
    item.analysis = {**(item.analysis or {}), "published_at": datetime.utcnow().isoformat(), "published_by": str(user_id)}

    job = (await db.execute(
        select(IngestionJob).where(IngestionJob.content_item_id == item.id).order_by(IngestionJob.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if job is not None and job.status in ("ready_for_review", "needs_attention"):
        job.status, job.completed_at = "completed", datetime.utcnow()
    await db.flush()
    return result
