"""
Demo Data Generator for Adaptive LMS (Stage 2: 5 Real Production Courses).

Generates rich, realistic learner telemetry and performance archetypes:
1. High-mastery learner (Alice Adams): mastery >= 0.88 across Python and GenAI competencies
2. High completion, low competency learner (Bob Bennett): 100% course progress, but shallow mastery (0.35-0.45) with conceptual errors
3. Declining performance learner (Carol Clark): started strong (0.80), fell to 0.42 on advanced distributed streaming
4. Low-mastery, disengaged learner (Dan Davis): low activity, low mastery (0.28), high risk alert
5. Module with emerging skill gap: python.oop & de.stream_processing has organization-wide deficit
6. Immutable learning telemetry events (session_started, video_progress, article_completed, answer_submitted, etc.)
"""

import sys
import os
import uuid
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "services", "api"))

from app.core.database import SessionLocal
from app.models import (
    Organization,
    User,
    Course,
    Module,
    Competency,
    Enrollment,
    LearnerCompetency,
    CompetencyHistory,
    SkillGap,
    LearnerRisk,
    LearningEvent,
    AdaptiveSession,
    SessionSequenceStep,
    AIInsight,
)


def generate_demo_telemetry():
    session = SessionLocal()
    try:
        print("Generating Realistic Adaptive Learning Telemetry for 5 Courses...")

        acme = session.query(Organization).filter_by(slug="acme-corp").first()
        if not acme:
            print("  [FAIL] Acme Corporation not found. Please run seed.py first.")
            return

        courses = {c.code: c for c in session.query(Course).filter_by(org_id=acme.id).all()}
        competencies = {c.code: c for c in session.query(Competency).filter_by(org_id=acme.id).all()}

        alice = session.query(User).filter_by(email="alice.learner@acme.com").first()
        bob = session.query(User).filter_by(email="bob.learner@acme.com").first()
        carol = session.query(User).filter_by(email="carol.learner@acme.com").first()
        dan = session.query(User).filter_by(email="dan.learner@acme.com").first()

        now = datetime.utcnow()
        py_course = courses.get("PY-FUND-101")
        de_course = courses.get("DE-PIPELINES-301")
        ml_course = courses.get("ML-CORE-401")

        # =====================================================================
        # ARCHETYPE 1: High Mastery Learner (Alice Adams)
        # =====================================================================
        print("  -> Configuring Archetype 1: Alice Adams (High Mastery / Fast Learner)")
        for comp_code, mastery in [("python.functions", 0.94), ("python.oop", 0.88), ("genai.rag_architecture", 0.91)]:
            comp = competencies.get(comp_code)
            if not comp:
                continue
            lc = session.query(LearnerCompetency).filter_by(user_id=alice.id, competency_id=comp.id).first()
            if not lc:
                lc = LearnerCompetency(
                    id=uuid.uuid4(),
                    org_id=acme.id,
                    user_id=alice.id,
                    competency_id=comp.id,
                    mastery_score=mastery,
                    confidence_score=0.94,
                    data_points_count=18,
                    status="expert" if mastery >= 0.90 else "proficient",
                    last_assessed_at=now - timedelta(days=1),
                )
                session.add(lc)
                session.flush()

                for score in [0.55, 0.70, 0.82, mastery]:
                    session.add(CompetencyHistory(
                        id=uuid.uuid4(),
                        learner_competency_id=lc.id,
                        mastery_score=score,
                        recorded_at=now - timedelta(days=4),
                    ))

        # =====================================================================
        # ARCHETYPE 2: High Completion, Low Competency Learner (Bob Bennett)
        # =====================================================================
        print("  -> Configuring Archetype 2: Bob Bennett (Shallow Completion / Low Mastery)")
        if py_course:
            bob_enr = session.query(Enrollment).filter_by(user_id=bob.id, course_id=py_course.id).first()
            if bob_enr:
                bob_enr.progress_pct = 100.0
                bob_enr.status = "completed"

        for comp_code, mastery in [("python.functions", 0.42), ("python.oop", 0.38)]:
            comp = competencies.get(comp_code)
            if not comp:
                continue
            lc = session.query(LearnerCompetency).filter_by(user_id=bob.id, competency_id=comp.id).first()
            if not lc:
                lc = LearnerCompetency(
                    id=uuid.uuid4(),
                    org_id=acme.id,
                    user_id=bob.id,
                    competency_id=comp.id,
                    mastery_score=mastery,
                    confidence_score=0.88,
                    data_points_count=22,
                    status="developing",
                    last_assessed_at=now - timedelta(hours=6),
                )
                session.add(lc)
                session.flush()

        # =====================================================================
        # ARCHETYPE 3: Declining Performance Learner (Carol Clark)
        # =====================================================================
        print("  -> Configuring Archetype 3: Carol Clark (Declining Performance)")
        comp_stream = competencies.get("de.stream_processing")
        if comp_stream:
            lc = session.query(LearnerCompetency).filter_by(user_id=carol.id, competency_id=comp_stream.id).first()
            if not lc:
                lc = LearnerCompetency(
                    id=uuid.uuid4(),
                    org_id=acme.id,
                    user_id=carol.id,
                    competency_id=comp_stream.id,
                    mastery_score=0.44,
                    confidence_score=0.85,
                    data_points_count=14,
                    status="developing",
                    last_assessed_at=now - timedelta(hours=3),
                )
                session.add(lc)
                session.flush()

                for score in [0.80, 0.72, 0.58, 0.44]:
                    session.add(CompetencyHistory(
                        id=uuid.uuid4(),
                        learner_competency_id=lc.id,
                        mastery_score=score,
                        recorded_at=now - timedelta(days=2),
                    ))

        # =====================================================================
        # ARCHETYPE 4: Low Activity / High Risk Learner (Dan Davis)
        # =====================================================================
        print("  -> Configuring Archetype 4: Dan Davis (Disengaged / High Risk)")
        comp_metrics = competencies.get("ml.evaluation_metrics")
        if comp_metrics:
            lc = session.query(LearnerCompetency).filter_by(user_id=dan.id, competency_id=comp_metrics.id).first()
            if not lc:
                lc = LearnerCompetency(
                    id=uuid.uuid4(),
                    org_id=acme.id,
                    user_id=dan.id,
                    competency_id=comp_metrics.id,
                    mastery_score=0.28,
                    confidence_score=0.70,
                    data_points_count=6,
                    status="novice",
                    last_assessed_at=now - timedelta(days=12),
                )
                session.add(lc)
                session.flush()

        # At-Risk Records
        if ml_course and py_course:
            session.add_all([
                LearnerRisk(
                    id=uuid.uuid4(),
                    org_id=acme.id,
                    user_id=dan.id,
                    course_id=ml_course.id,
                    risk_level="high",
                    risk_score=0.88,
                    risk_factors=["prolonged_inactivity", "low_mastery", "stagnation"],
                    recommended_actions=["Schedule 1-on-1 diagnostic review with manager and assign remedial foundations lab."],
                    is_resolved=False,
                    detected_at=now - timedelta(days=3),
                ),
                LearnerRisk(
                    id=uuid.uuid4(),
                    org_id=acme.id,
                    user_id=bob.id,
                    course_id=py_course.id,
                    risk_level="medium",
                    risk_score=0.62,
                    risk_factors=["shallow_completion", "conceptual_misconceptions"],
                    recommended_actions=["Trigger adaptive remediation for Python Functions & Closures before advancing."],
                    is_resolved=False,
                    detected_at=now - timedelta(days=1),
                ),
            ])

        # Emerging Cohort Skill Gaps
        if comp_stream:
            session.add(SkillGap(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=None,
                team_id=None,
                competency_id=comp_stream.id,
                current_mastery=0.48,
                target_mastery=0.80,
                gap_size=0.32,
                severity="high",
                detected_at=now - timedelta(days=2),
            ))

        # Telemetry Events for Auditability
        session.add_all([
            LearningEvent(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=alice.id,
                event_type="video_completed",
                payload={"content_id": "video-1", "watch_duration_seconds": 480, "progress_percentage": 100},
                timestamp=now - timedelta(days=1),
                processed=True,
            ),
            LearningEvent(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=bob.id,
                event_type="answer_submitted",
                payload={
                    "question_id": "q-oop-1",
                    "correct": False,
                    "error_type": "CONCEPTUAL",
                    "response_time_ms": 4200,
                    "attempt_number": 2,
                },
                timestamp=now - timedelta(hours=5),
                processed=True,
            ),
            LearningEvent(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=carol.id,
                event_type="answer_submitted",
                payload={
                    "question_id": "q-stream-1",
                    "correct": False,
                    "error_type": "PROCEDURAL",
                    "response_time_ms": 6800,
                    "attempt_number": 1,
                },
                timestamp=now - timedelta(hours=2),
                processed=True,
            ),
        ])

        session.commit()
        print("  [OK] Realistic Multi-Course Telemetry, Archetypes, and Risk Signals Generated Successfully!")

    except Exception as e:
        session.rollback()
        print(f"  [FAIL] Failed generating demo telemetry: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    generate_demo_telemetry()
