"""
Assembles the learner-facing views: course overview, player payload and home.

All figures come from stored rows or from the derivations in `progress.py`. The pure
helpers at the top (ordering, resume choice, wording) are unit tested; the async
builders below them compose those with queries.
"""

import mimetypes
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AIInsight,
    Assignment,
    AssignmentSubmission,
    Competency,
    CompetencyPrerequisite,
    ContentCompetency,
    ContentItem,
    ContentProgress,
    Course,
    CourseCompetency,
    Enrollment,
    LearnerCompetency,
    LearningEvent,
    Module,
    Quiz,
    User,
)
from app.schemas import learning as s
from app.services import progress as progress_service
from app.services.course_metrics import duration_minutes
from app.services.media import resolve_media

# A competency below this mastery is treated as needing reinforcement.
WEAK_MASTERY = 0.6
MAX_RECOMMENDATIONS = 3
RECENT_ACTIVITY_LIMIT = 8
INSIGHT_PREVIEW_CHARS = 420
READING_TYPES = ("VIDEO", "ARTICLE", "DOCUMENT", "TEXT")


class NotFound(Exception):
    """The resource does not exist, is not visible to the caller, or belongs to another tenant."""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def item_kind(content_type: str) -> str:
    kind = (content_type or "").upper()
    if kind == "QUIZ":
        return "assessment"
    if kind in ("ASSIGNMENT", "LAB"):
        return "assignment"
    return "lesson"


def order_items(modules: Sequence[Module], items: Iterable[ContentItem]) -> List[ContentItem]:
    """Course order: by module sequence, then item order, then creation time."""
    module_rank = {m.id: (m.sequence_order, str(m.id)) for m in modules}
    return sorted(
        items,
        key=lambda i: (module_rank.get(i.module_id, (10**9, "")), i.order_index, i.created_at or datetime.min),
    )


def choose_resume(ordered: Sequence[Tuple[UUID, str, Optional[datetime]]]) -> Optional[UUID]:
    """
    Where should the learner pick up?

    `ordered` is (item_id, progress_status, last_accessed) in course order.
    1. The most recently touched item that is still in progress;
    2. otherwise the first item not yet completed;
    3. otherwise None (the course is finished, or empty).
    """
    in_progress = [(item_id, at) for item_id, status, at in ordered if status == "in_progress" and at]
    if in_progress:
        return max(in_progress, key=lambda pair: pair[1])[0]
    for item_id, status, _ in ordered:
        if status != "completed":
            return item_id
    return None


def weak_competency_reason(name: str, mastery: float) -> str:
    return f"Your {name} mastery is {round(mastery * 100)}%, and this covers it."


ACTIVITY_LABELS = {
    "content_started": "Started {title}",
    "content_completed": "Completed {title}",
    "assessment_started": "Started assessment {title}",
    "assessment_completed": "Finished an assessment{score}",
    "assignment_submitted": "Submitted an assignment",
}


def activity_label(event_type: str, payload: Optional[dict]) -> Optional[str]:
    """Human wording for an event, or None for events too granular to list."""
    template = ACTIVITY_LABELS.get(event_type)
    if template is None:
        return None
    payload = payload or {}
    score = payload.get("score")
    return template.format(
        title=payload.get("title") or "a lesson",
        score=f" (score {round(score)}%)" if isinstance(score, (int, float)) else "",
    )


# ---------------------------------------------------------------------------
# Shared queries
# ---------------------------------------------------------------------------
async def _load_course(db: AsyncSession, org_id: UUID, course_id: UUID, is_author: bool) -> Course:
    course = (
        await db.execute(
            select(Course)
            .where(and_(Course.id == course_id, Course.org_id == org_id))
            .options(selectinload(Course.instructor))
        )
    ).scalar_one_or_none()
    if course is None or (not is_author and course.status != "published"):
        raise NotFound("Course not found")
    return course


async def _visible_items(
    db: AsyncSession, org_id: UUID, course_id: UUID, is_author: bool
) -> Tuple[List[Module], List[ContentItem]]:
    modules = (
        await db.execute(
            select(Module).where(and_(Module.course_id == course_id, Module.org_id == org_id)).order_by(Module.sequence_order)
        )
    ).scalars().all()
    query = select(ContentItem).where(
        and_(ContentItem.org_id == org_id, ContentItem.module_id.in_([m.id for m in modules] or [None]))
    )
    if not is_author:
        query = query.where(ContentItem.status == progress_service.PUBLISHED)
    items = (await db.execute(query)).scalars().all()
    return list(modules), order_items(modules, items)


async def _progress_by_item(
    db: AsyncSession, user_id: UUID, item_ids: Sequence[UUID]
) -> Dict[UUID, ContentProgress]:
    if not item_ids:
        return {}
    rows = (
        await db.execute(
            select(ContentProgress).where(
                ContentProgress.user_id == user_id, ContentProgress.content_item_id.in_(item_ids)
            )
        )
    ).scalars().all()
    return {r.content_item_id: r for r in rows}


# ---------------------------------------------------------------------------
# Course overview
# ---------------------------------------------------------------------------
async def build_overview(
    db: AsyncSession, *, org_id: UUID, user: User, course_id: UUID, is_author: bool
) -> s.CourseOverview:
    course = await _load_course(db, org_id, course_id, is_author)
    modules, items = await _visible_items(db, org_id, course_id, is_author)
    item_ids = [i.id for i in items]
    progress = await _progress_by_item(db, user.id, item_ids)

    quiz_ids = {
        row.content_item_id: row.id
        for row in (
            await db.execute(select(Quiz.id, Quiz.content_item_id).where(Quiz.content_item_id.in_(item_ids or [None])))
        ).all()
    }
    assignment_ids = {
        row.content_item_id: row.id
        for row in (
            await db.execute(
                select(Assignment.id, Assignment.content_item_id).where(Assignment.content_item_id.in_(item_ids or [None]))
            )
        ).all()
    }

    def summarise(item: ContentItem) -> s.ItemSummary:
        record = progress.get(item.id)
        return s.ItemSummary(
            id=item.id,
            module_id=item.module_id,
            title=item.title,
            content_type=item.content_type,
            kind=item_kind(item.content_type),
            source_type=item.source_type,
            duration_seconds=item.duration_seconds or 0,
            order_index=item.order_index,
            publication_status=item.status,
            progress_status=record.status if record else "not_started",
            progress_percent=record.progress_percent if record else 0.0,
            quiz_id=quiz_ids.get(item.id),
            assignment_id=assignment_ids.get(item.id),
        )

    summaries = {i.id: summarise(i) for i in items}
    module_overviews: List[s.ModuleOverview] = []
    for module in modules:
        module_items = [summaries[i.id] for i in items if i.module_id == module.id]
        module_overviews.append(
            s.ModuleOverview(
                id=module.id,
                title=module.title,
                description=module.description,
                sequence_order=module.sequence_order,
                lessons=sum(1 for i in module_items if i.kind == "lesson"),
                assessments=sum(1 for i in module_items if i.kind != "lesson"),
                total_items=len(module_items),
                completed_items=sum(1 for i in module_items if i.progress_status == "completed"),
                known_duration_seconds=sum(i.duration_seconds for i in module_items),
                items=module_items,
            )
        )

    # Competencies developed by the course, with the learner's own mastery where evidence exists.
    course_comps = (
        await db.execute(
            select(CourseCompetency, Competency)
            .join(Competency, Competency.id == CourseCompetency.competency_id)
            .where(and_(CourseCompetency.course_id == course_id, Competency.org_id == org_id))
            .order_by(CourseCompetency.is_primary.desc(), Competency.name)
        )
    ).all()
    comp_ids = [c.id for _, c in course_comps]
    mastery = await _mastery_by_competency(db, org_id, user.id, comp_ids)
    developed = [
        s.CompetencyDeveloped(
            id=c.id, code=c.code, name=c.name, description=c.description, domain=c.domain,
            difficulty=c.difficulty, target_mastery=cc.target_mastery,
            mastery=mastery[c.id].mastery_score if c.id in mastery else None,
            confidence=mastery[c.id].confidence_score if c.id in mastery else None,
        )
        for cc, c in course_comps
    ]

    prerequisites = await _prerequisites_outside_course(db, org_id, user.id, comp_ids, {c.id: c.name for _, c in course_comps})

    # Objectives: prefer what content analysis extracted; fall back to what the competencies say.
    analysed = [
        objective.strip()
        for item in items
        for objective in ((item.analysis or {}).get("objectives") or [])
        if isinstance(objective, str) and objective.strip()
    ]
    objectives = list(dict.fromkeys(analysed))
    source = "content_analysis" if objectives else "none"
    if not objectives:
        objectives = [c.description for _, c in course_comps if c.description]
        source = "competency_descriptions" if objectives else "none"

    enrollment = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.org_id == org_id, Enrollment.user_id == user.id, Enrollment.course_id == course_id,
                Enrollment.status.in_(["active", "completed"]),
            )
        )
    ).scalar_one_or_none()
    enrollment_count = (
        await db.execute(select(func.count(Enrollment.id)).where(Enrollment.org_id == org_id, Enrollment.course_id == course_id))
    ).scalar() or 0

    completed = sum(1 for i in summaries.values() if i.progress_status == "completed")
    resume_id = choose_resume(
        [(i.id, summaries[i.id].progress_status, progress[i.id].last_accessed_at if i.id in progress else None) for i in items]
    )
    resume_title = summaries[resume_id].title if resume_id else None
    total_seconds = sum(i.duration_seconds or 0 for i in items)

    return s.CourseOverview(
        course=s.CourseHeader(
            id=course.id, title=course.title, code=course.code, description=course.description, status=course.status,
            category=course.category, difficulty=course.difficulty, thumbnail_url=course.thumbnail_url,
            instructor_name=course.instructor.full_name if course.instructor else None,
            rating=course.rating, duration_minutes=duration_minutes(course.duration_minutes, total_seconds),
            enrollment_count=enrollment_count, module_count=len(modules), item_count=len(items),
        ),
        is_enrolled=enrollment is not None,
        enrollment_status=enrollment.status if enrollment else None,
        is_preview=is_author and (course.status != "published" or any(i.status != "published" for i in items)),
        objectives=objectives,
        objectives_source=source,
        competencies=developed,
        prerequisites=prerequisites,
        modules=module_overviews,
        progress=s.ProgressOverview(
            total_items=len(items),
            completed_items=completed,
            percent=progress_service.completion_percent(completed, len(items)),
            time_spent_seconds=sum(r.time_spent_seconds for r in progress.values()),
            resume_item_id=resume_id,
            resume_item_title=resume_title,
        ),
    )


async def _mastery_by_competency(
    db: AsyncSession, org_id: UUID, user_id: UUID, competency_ids: Sequence[UUID]
) -> Dict[UUID, LearnerCompetency]:
    if not competency_ids:
        return {}
    rows = (
        await db.execute(
            select(LearnerCompetency).where(
                LearnerCompetency.org_id == org_id,
                LearnerCompetency.user_id == user_id,
                LearnerCompetency.competency_id.in_(competency_ids),
                LearnerCompetency.basis == "evidence",          # state left by the earlier engine is not shown
                LearnerCompetency.data_points_count > 0,
            )
        )
    ).scalars().all()
    return {r.competency_id: r for r in rows}


async def _prerequisites_outside_course(
    db: AsyncSession, org_id: UUID, user_id: UUID, course_comp_ids: Sequence[UUID], course_comp_names: Dict[UUID, str]
) -> List[s.PrerequisiteRequirement]:
    """
    Competencies the course builds on but does not itself teach.

    A prerequisite of one of the course's competencies that the course also develops
    is not a *course* prerequisite (the course covers it), so it is left out.
    """
    if not course_comp_ids:
        return []
    edges = (
        await db.execute(
            select(CompetencyPrerequisite).where(
                CompetencyPrerequisite.org_id == org_id, CompetencyPrerequisite.competency_id.in_(course_comp_ids)
            )
        )
    ).scalars().all()
    outside = [e for e in edges if e.prerequisite_id not in set(course_comp_ids)]
    if not outside:
        return []

    prereq_ids = list({e.prerequisite_id for e in outside})
    named = {
        c.id: c
        for c in (await db.execute(select(Competency).where(Competency.id.in_(prereq_ids), Competency.org_id == org_id))).scalars().all()
    }
    mastery = await _mastery_by_competency(db, org_id, user_id, prereq_ids)

    result: List[s.PrerequisiteRequirement] = []
    for prereq_id in prereq_ids:
        needed_by = [e for e in outside if e.prerequisite_id == prereq_id]
        required = max(e.min_mastery for e in needed_by)
        record = mastery.get(prereq_id)
        result.append(
            s.PrerequisiteRequirement(
                competency_id=prereq_id, code=named[prereq_id].code, name=named[prereq_id].name,
                required_for=sorted({course_comp_names[e.competency_id] for e in needed_by}),
                min_mastery=required,
                mastery=record.mastery_score if record else None,
                met=(record.mastery_score >= required) if record else None,
            )
        )
    return sorted(result, key=lambda r: r.name)


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
async def build_player(
    db: AsyncSession, *, org_id: UUID, user: User, item_id: UUID, is_author: bool
) -> s.PlayerPayload:
    item = (
        await db.execute(select(ContentItem).where(and_(ContentItem.id == item_id, ContentItem.org_id == org_id)))
    ).scalar_one_or_none()
    if item is None or (not is_author and item.status != progress_service.PUBLISHED):
        raise NotFound("Content item not found")

    module = await db.get(Module, item.module_id)
    if module is None or module.org_id != org_id:
        raise NotFound("Content item not found")
    course = await _load_course(db, org_id, module.course_id, is_author)
    modules, ordered = await _visible_items(db, org_id, course.id, is_author)

    ids = [i.id for i in ordered]
    index = ids.index(item.id) if item.id in ids else 0

    record = (await _progress_by_item(db, user.id, [item.id])).get(item.id)

    quiz_id = (await db.execute(select(Quiz.id).where(Quiz.content_item_id == item.id))).scalar_one_or_none()

    assignment_info: Optional[s.AssignmentInfo] = None
    assignment = (
        await db.execute(select(Assignment).where(Assignment.content_item_id == item.id, Assignment.org_id == org_id))
    ).scalar_one_or_none()
    if assignment is not None:
        submission = (
            await db.execute(
                select(AssignmentSubmission)
                .where(AssignmentSubmission.assignment_id == assignment.id, AssignmentSubmission.learner_id == user.id)
                .order_by(desc(AssignmentSubmission.submitted_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        assignment_info = s.AssignmentInfo(
            id=assignment.id, instructions=assignment.instructions, difficulty=assignment.difficulty,
            max_score=assignment.max_score, rubric=assignment.rubric or {},
            submission_status=submission.status if submission else None,
            submission_text=submission.submission_text if submission else None,
            submission_url=submission.submission_url if submission else None,
            submitted_at=submission.submitted_at if submission else None,
            score=submission.score if submission else None,
            feedback=submission.feedback if submission else None,
        )

    competency_names = (
        await db.execute(
            select(Competency.name)
            .join(ContentCompetency, ContentCompetency.competency_id == Competency.id)
            .where(ContentCompetency.content_item_id == item.id, Competency.org_id == org_id)
            .order_by(Competency.name)
        )
    ).scalars().all()

    filename = (item.content_url or "").rsplit("/", 1)[-1]
    media = resolve_media(
        content_type=item.content_type,
        source_type=item.source_type,
        content_url=item.content_url,
        source_url=item.source_url,
        file_endpoint=f"/api/v1/learning/content/{item.id}/file",
        file_mime_type=mimetypes.guess_type(filename)[0],
    )

    return s.PlayerPayload(
        item=s.PlayerItem(
            id=item.id, course_id=course.id, module_id=item.module_id, title=item.title, description=item.description,
            content_type=item.content_type, kind=item_kind(item.content_type), source_type=item.source_type,
            duration_seconds=item.duration_seconds or 0,
            text_content=item.text_content or item.raw_text,
            transcript=item.transcript,
            media=s.MediaInfo(provider=media.provider, video_id=media.video_id, url=media.url, mime_type=media.mime_type) if media else None,
            quiz_id=quiz_id,
            assignment=assignment_info,
            competency_names=list(competency_names),
        ),
        progress=s.PlayerProgress(
            status=record.status if record else "not_started",
            progress_percent=record.progress_percent if record else 0.0,
            position_seconds=record.position_seconds if record else 0,
            time_spent_seconds=record.time_spent_seconds if record else 0,
        ),
        course_title=course.title,
        module_title=module.title,
        position=index + 1,
        total=len(ordered),
        previous_id=ids[index - 1] if index > 0 else None,
        next_id=ids[index + 1] if index + 1 < len(ids) else None,
    )


# ---------------------------------------------------------------------------
# Learner home
# ---------------------------------------------------------------------------
async def build_home(db: AsyncSession, *, org_id: UUID, user: User) -> s.LearnerHome:
    enrollments = (
        await db.execute(
            select(Enrollment, Course)
            .join(Course, Course.id == Enrollment.course_id)
            .where(
                Enrollment.org_id == org_id, Enrollment.user_id == user.id,
                Enrollment.status.in_(["active", "completed"]), Course.status == "published",
            )
            .order_by(desc(Enrollment.last_activity_at))
        )
    ).all()
    derived = await progress_service.progress_for_courses(db, org_id, user.id, [c.id for _, c in enrollments])

    in_progress: List[s.InProgressCourse] = []
    continue_learning: Optional[s.ContinueLearning] = None
    for enrollment, course in enrollments:  # most recent activity first
        p = derived[course.id]
        if p.total_items == 0 or p.completed_items >= p.total_items:
            continue
        in_progress.append(
            s.InProgressCourse(
                course_id=course.id, title=course.title, category=course.category, difficulty=course.difficulty,
                thumbnail_url=course.thumbnail_url, progress_percent=p.percent,
                completed_items=p.completed_items, total_items=p.total_items,
            )
        )
        if continue_learning is None:
            modules, ordered = await _visible_items(db, org_id, course.id, is_author=False)
            progress = await _progress_by_item(db, user.id, [i.id for i in ordered])
            resume_id = choose_resume(
                [(i.id, progress[i.id].status if i.id in progress else "not_started",
                  progress[i.id].last_accessed_at if i.id in progress else None) for i in ordered]
            )
            target = next((i for i in ordered if i.id == resume_id), None)
            module_title = next((m.title for m in modules if target and m.id == target.module_id), None)
            continue_learning = s.ContinueLearning(
                course_id=course.id, course_title=course.title, module_title=module_title,
                item_id=target.id if target else None, item_title=target.title if target else None,
                item_type=target.content_type if target else None,
                progress_percent=p.percent, last_activity_at=enrollment.last_activity_at,
            )

    competencies = (
        await db.execute(
            select(LearnerCompetency, Competency)
            .join(Competency, Competency.id == LearnerCompetency.competency_id)
            .where(LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user.id,
                   LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0)
            .order_by(desc(LearnerCompetency.updated_at))
            .limit(8)
        )
    ).all()

    activity = await _recent_activity(db, org_id, user.id)
    insight = await _latest_insight(db, org_id, user.id)
    recommendations = await _recommendations(db, org_id, user.id, enrolled_course_ids={c.id for _, c in enrollments})

    completed_items = (
        await db.execute(
            select(func.count(ContentProgress.id)).where(
                ContentProgress.org_id == org_id, ContentProgress.user_id == user.id, ContentProgress.status == "completed"
            )
        )
    ).scalar() or 0
    time_spent = (
        await db.execute(
            select(func.coalesce(func.sum(ContentProgress.time_spent_seconds), 0)).where(
                ContentProgress.org_id == org_id, ContentProgress.user_id == user.id
            )
        )
    ).scalar() or 0

    return s.LearnerHome(
        continue_learning=continue_learning,
        in_progress=in_progress,
        recommendations=recommendations,
        competencies=[
            s.HomeCompetency(
                id=c.id, name=c.name, domain=c.domain, mastery=lc.mastery_score, confidence=lc.confidence_score,
                evidence_count=lc.data_points_count, updated_at=lc.updated_at,
            )
            for lc, c in competencies
        ],
        recent_activity=activity,
        insight=insight,
        stats=s.HomeStats(
            enrolled_courses=len(enrollments),
            # Derived from lesson records, not the enrollment's stored status.
            completed_courses=sum(
                1 for _, c in enrollments
                if derived[c.id].total_items > 0 and derived[c.id].completed_items >= derived[c.id].total_items
            ),
            completed_items=int(completed_items),
            time_spent_seconds=int(time_spent),
        ),
    )


async def _recent_activity(db: AsyncSession, org_id: UUID, user_id: UUID) -> List[s.ActivityItem]:
    events = (
        await db.execute(
            select(LearningEvent)
            .where(
                LearningEvent.org_id == org_id, LearningEvent.user_id == user_id,
                LearningEvent.event_type.in_(list(ACTIVITY_LABELS)),
            )
            .order_by(desc(LearningEvent.timestamp))
            .limit(RECENT_ACTIVITY_LIMIT)
        )
    ).scalars().all()
    course_ids = {e.course_id for e in events if e.course_id}
    titles = (
        {c.id: c.title for c in (await db.execute(select(Course).where(Course.id.in_(course_ids)))).scalars().all()}
        if course_ids else {}
    )
    result = []
    for event in events:
        label = activity_label(event.event_type, event.payload)
        if label:
            result.append(
                s.ActivityItem(
                    event_type=event.event_type, label=label,
                    course_title=titles.get(event.course_id), timestamp=event.timestamp,
                )
            )
    return result


async def _latest_insight(db: AsyncSession, org_id: UUID, user_id: UUID) -> Optional[s.HomeInsight]:
    insight = (
        await db.execute(
            select(AIInsight)
            .where(AIInsight.org_id == org_id, AIInsight.scope_type == "learner", AIInsight.scope_id == user_id)
            .order_by(desc(AIInsight.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if insight is None:
        return None
    text = insight.narrative_text.strip()
    if len(text) > INSIGHT_PREVIEW_CHARS:
        text = text[:INSIGHT_PREVIEW_CHARS].rsplit(" ", 1)[0] + "…"
    return s.HomeInsight(id=insight.id, narrative=text, created_at=insight.created_at, model_used=insight.model_used)


async def _recommendations(
    db: AsyncSession, org_id: UUID, user_id: UUID, enrolled_course_ids: set
) -> List[s.Recommendation]:
    """
    Deterministic, explainable recommendations.

    1. For each competency the learner is weak in (mastery below WEAK_MASTERY,
       weakest first), the first unfinished piece of published reading/viewing
       content mapped to that competency.
    2. Any remaining slots: published courses the learner has not enrolled in, most
       enrolled first. Never fabricated: every entry states the stored fact behind it.
    """
    recommendations: List[s.Recommendation] = []
    seen_content: set = set()

    weak = (
        await db.execute(
            select(LearnerCompetency, Competency)
            .join(Competency, Competency.id == LearnerCompetency.competency_id)
            .where(
                LearnerCompetency.org_id == org_id, LearnerCompetency.user_id == user_id,
                LearnerCompetency.mastery_score < WEAK_MASTERY,
                LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0,
            )
            .order_by(LearnerCompetency.mastery_score.asc())
            .limit(6)
        )
    ).all()

    for learner_comp, comp in weak:
        if len(recommendations) >= MAX_RECOMMENDATIONS:
            break
        row = (
            await db.execute(
                select(ContentItem, Course)
                .join(ContentCompetency, ContentCompetency.content_item_id == ContentItem.id)
                .join(Course, Course.id == ContentItem.course_id)
                .outerjoin(
                    ContentProgress,
                    and_(ContentProgress.content_item_id == ContentItem.id, ContentProgress.user_id == user_id),
                )
                .where(
                    ContentCompetency.competency_id == comp.id,
                    ContentItem.org_id == org_id,
                    ContentItem.status == progress_service.PUBLISHED,
                    ContentItem.content_type.in_(READING_TYPES),
                    Course.status == "published",
                    or_(ContentProgress.status.is_(None), ContentProgress.status != "completed"),
                )
                .order_by(ContentItem.order_index)
                .limit(3)
            )
        ).all()
        for item, course in row:
            if item.id in seen_content:
                continue
            seen_content.add(item.id)
            recommendations.append(
                s.Recommendation(
                    kind="content", reason_type="weak_competency",
                    reason=weak_competency_reason(comp.name, learner_comp.mastery_score),
                    course_id=course.id, course_title=course.title, content_id=item.id,
                    content_title=item.title, content_type=item.content_type,
                    competency_id=comp.id, competency_name=comp.name, mastery=learner_comp.mastery_score,
                )
            )
            break

    if len(recommendations) < MAX_RECOMMENDATIONS:
        counts = (
            select(Enrollment.course_id.label("course_id"), func.count(Enrollment.id).label("n"))
            .where(Enrollment.org_id == org_id)
            .group_by(Enrollment.course_id)
            .subquery()
        )
        query = (
            select(Course, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.course_id == Course.id)
            .where(Course.org_id == org_id, Course.status == "published")
            .order_by(func.coalesce(counts.c.n, 0).desc(), Course.created_at.desc())
            .limit(MAX_RECOMMENDATIONS - len(recommendations))
        )
        if enrolled_course_ids:  # NOT IN over an empty/NULL list would match nothing
            query = query.where(Course.id.notin_(list(enrolled_course_ids)))
        candidates = (await db.execute(query)).all()
        for course, n in candidates:
            recommendations.append(
                s.Recommendation(
                    kind="course",
                    reason_type="popular_in_org" if n else "available",
                    reason=(f"{n} {'colleague is' if n == 1 else 'colleagues are'} enrolled." if n else "Available in your catalog; you have not started it."),
                    course_id=course.id, course_title=course.title,
                )
            )
    return recommendations
