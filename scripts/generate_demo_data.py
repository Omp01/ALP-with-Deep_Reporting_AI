"""
Demo data for Adaptive LMS: synthetic learner history, run through the real competency engine.

Earlier versions of this script wrote mastery numbers, risk scores and skill gaps straight into the tables. Nothing was
behind them, which is exactly what the platform must never show. This version writes only what a learner would produce,
evidence, and lets the engine derive everything else:

    synthetic answers (source_type = 'seed_history')  ->  app.competency.service.apply  ->  mastery, confidence, trend
    risk records                                      ->  app.services.risk_service (the same rules as production)

Everything created here is SYNTHETIC. It is labelled as such in the evidence table (`source_type = 'seed_history'`) so a
report can say so, and it has no `source_event_id` because no real event stands behind it. The outcomes (for example that
Bob ends up weak in python.functions) come from the engine, not from a number chosen here: the answers are what is chosen.

Archetypes
    Alice  correct answers, a slow start: high mastery, improving
    Bob    completed the course but keeps answering wrongly, often on retries: weak competencies
    Carol  strong start, then a run of wrong answers on streaming: declining
    Dan    a few wrong answers, then nothing for two weeks: low mastery and inactive

Run after seed.py:   python scripts/generate_demo_data.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "services", "api"))

from sqlalchemy import select

from app.competency import service as competency_service
from app.core.database import AsyncSessionLocal
from app.events import store as event_store
from app.models import Competency, ContentItem, Course, CourseCompetency, Enrollment, LearnerCompetency, Organization, User
from app.services import risk_service

# (signal, difficulty, attempt_number, error_type). Days are counted back from now, oldest first, spread evenly.
Answer = Tuple[float, float, int, Optional[str]]

ARCHETYPES: Dict[str, Dict[str, object]] = {
    "alice.learner@acme.com": {
        "span_days": 9, "answers": {
            "python.functions": [(0, .4, 1, "knowledge_gap"), (1, .5, 1, None), (1, .5, 1, None), (1, .6, 1, None), (1, .6, 1, None), (1, .7, 1, None), (1, .7, 1, None), (1, .7, 1, None)],
            "python.oop": [(1, .5, 1, None), (1, .5, 1, None), (0, .6, 1, "careless_error"), (1, .6, 1, None), (1, .7, 1, None), (1, .7, 1, None)],
            "genai.rag_architecture": [(1, .5, 1, None), (1, .6, 1, None), (1, .6, 1, None), (1, .7, 1, None), (1, .7, 1, None)],
        },
    },
    "bob.learner@acme.com": {
        "span_days": 14, "answers": {
            "python.functions": [(0, .4, 1, "conceptual_misunderstanding"), (0, .5, 1, "conceptual_misunderstanding"), (1, .5, 1, None), (0, .5, 1, "conceptual_misunderstanding"),
                                 (0, .6, 1, "procedural_error"), (1, .5, 2, None), (0, .6, 2, "conceptual_misunderstanding"), (0, .6, 2, "conceptual_misunderstanding"), (0, .6, 3, "conceptual_misunderstanding")],
            "python.oop": [(0, .5, 1, "conceptual_misunderstanding"), (0, .6, 1, "conceptual_misunderstanding"), (0, .6, 1, "knowledge_gap"), (1, .5, 1, None),
                           (0, .6, 2, "conceptual_misunderstanding"), (0, .6, 2, "conceptual_misunderstanding"), (0, .5, 3, "conceptual_misunderstanding")],
        },
    },
    "carol.learner@acme.com": {
        "span_days": 12, "answers": {
            "de.stream_processing": [(1, .5, 1, None), (1, .6, 1, None), (1, .6, 1, None), (1, .7, 1, None), (0, .7, 1, "procedural_error"), (0, .7, 1, "procedural_error"),
                                     (0, .7, 1, "procedural_error"), (0, .7, 1, "conceptual_misunderstanding"), (0, .7, 2, "procedural_error")],
        },
    },
    "dan.learner@acme.com": {
        "span_days": 4, "ends_days_ago": 14, "answers": {
            "ml.evaluation_metrics": [(0, .5, 1, "knowledge_gap"), (0, .5, 1, "knowledge_gap"), (1, .5, 1, None), (0, .6, 1, "knowledge_gap")],
        },
    },
}


def timeline(answers: List[Answer], span_days: float, ends_days_ago: float, now: datetime) -> List[datetime]:
    """Evenly spaced moments, the last `ends_days_ago` days ago and the first `span_days` earlier than that."""
    end = now - timedelta(days=ends_days_ago)
    start = end - timedelta(days=span_days)
    if len(answers) == 1:
        return [end]
    step = (end - start) / (len(answers) - 1)
    return [start + step * i for i in range(len(answers))]


async def generate_demo_telemetry() -> None:
    print("Generating synthetic learner history through the competency engine...")
    async with AsyncSessionLocal() as db:
        try:
            acme = (await db.execute(select(Organization).where(Organization.slug == "acme-corp"))).scalar_one_or_none()
            if acme is None:
                print("  [FAIL] The primary organization (slug acme-corp) not found. Please run seed.py first.")
                return
            competencies = {c.code: c for c in (await db.execute(select(Competency).where(Competency.org_id == acme.id))).scalars()}
            now = datetime.utcnow()
            applied = skipped = 0
            last_activity: Dict[tuple, datetime] = {}          # (learner, course) -> when they last answered

            for email, plan in ARCHETYPES.items():
                user = (await db.execute(select(User).where(User.email == email, User.org_id == acme.id))).scalar_one_or_none()
                if user is None:
                    print(f"  [SKIP] {email} not found")
                    continue
                for code, answers in plan["answers"].items():          # type: ignore[union-attr]
                    competency = competencies.get(code)
                    if competency is None:
                        print(f"  [SKIP] competency {code} not found")
                        continue
                    state = (await db.execute(select(LearnerCompetency).where(
                        LearnerCompetency.user_id == user.id, LearnerCompetency.competency_id == competency.id))).scalar_one_or_none()
                    if state is not None and state.basis == "evidence" and state.data_points_count > 0:
                        skipped += 1                                    # already has real or seeded evidence: leave it alone
                        continue
                    moments = timeline(answers, float(plan["span_days"]), float(plan.get("ends_days_ago", 1)), now)     # type: ignore[arg-type]
                    for (signal, difficulty, attempt, error_type), when in zip(answers, moments):
                        await competency_service.apply(db, competency_service.EvidenceInput(
                            org_id=acme.id, user_id=user.id, competency_id=competency.id, source_type="seed_history", signal=float(signal),
                            confidence=1.0, occurred_at=when, difficulty=difficulty, attempt_number=attempt, error_type=error_type,
                        ), emit_event=False)
                        applied += 1
                    # the course this competency belongs to, and when the learner last worked in it
                    course_id = (await db.execute(
                        select(CourseCompetency.course_id).join(Enrollment, Enrollment.course_id == CourseCompetency.course_id)
                        .where(CourseCompetency.competency_id == competency.id, Enrollment.user_id == user.id).limit(1))).scalar_one_or_none()
                    if course_id is not None:
                        key = (user.id, course_id)
                        last_activity[key] = max(last_activity.get(key, moments[-1]), moments[-1])

            # Bob has completed the course's content; the point of his story is that this says nothing about mastery.
            py = (await db.execute(select(Course).where(Course.code == "PY-FUND-101", Course.org_id == acme.id))).scalar_one_or_none()
            bob = (await db.execute(select(User).where(User.email == "bob.learner@acme.com"))).scalar_one_or_none()
            if py is not None and bob is not None:
                enrolment = (await db.execute(select(Enrollment).where(Enrollment.user_id == bob.id, Enrollment.course_id == py.id))).scalar_one_or_none()
                if enrolment is not None:
                    enrolment.progress_pct = 100.0

            # A learner who answered questions also opened lessons: record when they last did, so the inactivity rule has a real
            # event to measure from (it looks at events, not at evidence).
            for (user_id, course_id), when in last_activity.items():
                lesson = (await db.execute(select(ContentItem).where(ContentItem.course_id == course_id).order_by(ContentItem.order_index).limit(1))).scalar_one_or_none()
                if lesson is not None:
                    await event_store.record(db, org_id=acme.id, user_id=user_id, event_type="lesson_opened", course_id=course_id, module_id=lesson.module_id,
                                             content_id=lesson.id, timestamp=when, payload={"source": "direct"}, attach_session=False)

            # Dan enrolled three weeks ago and has been silent for two.
            dan = (await db.execute(select(User).where(User.email == "dan.learner@acme.com"))).scalar_one_or_none()
            ml = (await db.execute(select(Course).where(Course.code == "ML-CORE-401", Course.org_id == acme.id))).scalar_one_or_none()
            if ml is not None and dan is not None:
                enrolment = (await db.execute(select(Enrollment).where(Enrollment.user_id == dan.id, Enrollment.course_id == ml.id))).scalar_one_or_none()
                if enrolment is not None and (dan.id, ml.id) in last_activity:
                    enrolment.enrolled_at, enrolment.last_activity_at = now - timedelta(days=21), last_activity[(dan.id, ml.id)]

            await db.commit()
            print(f"  [OK] Applied {applied} synthetic answers ({skipped} competencies already had evidence).")

            # Risk records come from the same rules production uses, over the evidence just written.
            result = await risk_service.scan_organization_risks(db, acme.id)
            await db.commit()
            print(f"  [OK] Risk scan evaluated {result['evaluated_enrollments']} enrolments ({result['high_or_critical_risks']} high or critical).")

            for email in ARCHETYPES:
                user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
                if user is None:
                    continue
                rows = (await db.execute(select(LearnerCompetency, Competency).join(Competency, Competency.id == LearnerCompetency.competency_id)
                                         .where(LearnerCompetency.user_id == user.id, LearnerCompetency.basis == "evidence"))).all()
                summary = ", ".join(f"{c.code} {s.mastery_score:.2f} ({s.trend})" for s, c in rows)
                print(f"     {email}: {summary or 'no evidence'}")
        except Exception as exc:
            await db.rollback()
            print(f"  [FAIL] Failed generating demo data: {exc}")
            raise


if __name__ == "__main__":
    asyncio.run(generate_demo_telemetry())
