"""
Demo Data Generator for Adaptive LMS.

Generates rich, realistic learner telemetry and performance archetypes:
1. High-mastery learner (Alice Adams): mastery >= 0.88 across all competencies, expert/proficient
2. High completion, low competency learner (Bob Bennett): 100% module progress, but shallow mastery (0.35-0.45)
3. Declining performance learner (Carol Clark): started strong (0.80), fell to 0.42 on advanced topics
4. Low-mastery, disengaged learner (Dan Davis): low activity, low mastery (0.28), high risk flag
5. Module with emerging skill gap: EVENT-STREAM has organization-wide deficit
6. At-risk flags with actionable recommendations
7. Telemetry learning events (module_start, content_view, assessment_attempt, session_end)

Run via:
    python scripts/generate_demo_data.py
    or: docker exec alms-api python scripts/generate_demo_data.py
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
        print("Generating Realistic Adaptive Learning Telemetry & Archetypes...")

        acme = session.query(Organization).filter_by(slug="acme-corp").first()
        if not acme:
            print("  [FAIL] Acme Corporation not found. Please run seed.py first.")
            return

        course = session.query(Course).filter_by(org_id=acme.id, code="PY-DIST-101").first()
        modules = session.query(Module).filter_by(course_id=course.id).order_by(Module.sequence_order).all()
        competencies = {c.code: c for c in session.query(Competency).filter_by(org_id=acme.id).all()}

        alice = session.query(User).filter_by(email="alice.learner@acme.com").first()
        bob = session.query(User).filter_by(email="bob.learner@acme.com").first()
        carol = session.query(User).filter_by(email="carol.learner@acme.com").first()
        dan = session.query(User).filter_by(email="dan.learner@acme.com").first()

        now = datetime.utcnow()

        # =====================================================================
        # ARCHETYPE 1: High Mastery Learner (Alice Adams)
        # =====================================================================
        print("  -> Configuring Archetype 1: Alice Adams (High Mastery / Fast Learner)")
        alice_enrollment = session.query(Enrollment).filter_by(user_id=alice.id, course_id=course.id).first()
        if alice_enrollment:
            alice_enrollment.progress_pct = 95.0
            alice_enrollment.status = "completed"
            alice_enrollment.completed_at = now - timedelta(days=1)

        for comp_code, mastery in [("ASYNC-PY", 0.92), ("EVENT-STREAM", 0.88), ("DB-OPT", 0.85)]:
            comp = competencies.get(comp_code)
            if not comp:
                continue
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

            # Progression history
            for step, score in enumerate([0.55, 0.70, 0.82, mastery]):
                hist = CompetencyHistory(
                    id=uuid.uuid4(),
                    learner_competency_id=lc.id,
                    mastery_score=score,
                    recorded_at=now - timedelta(days=5 - step),
                )
                session.add(hist)

        # =====================================================================
        # ARCHETYPE 2: High Completion, Low Competency Learner (Bob Bennett)
        # =====================================================================
        print("  -> Configuring Archetype 2: Bob Bennett (100% Completion / Shallow Mastery)")
        bob_enrollment = session.query(Enrollment).filter_by(user_id=bob.id, course_id=course.id).first()
        if bob_enrollment:
            bob_enrollment.progress_pct = 100.0
            bob_enrollment.status = "completed"
            bob_enrollment.completed_at = now - timedelta(days=2)

        for comp_code, mastery in [("ASYNC-PY", 0.42), ("EVENT-STREAM", 0.38), ("DB-OPT", 0.45)]:
            comp = competencies.get(comp_code)
            if not comp:
                continue
            lc = LearnerCompetency(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=bob.id,
                competency_id=comp.id,
                mastery_score=mastery,
                confidence_score=0.88,
                data_points_count=22,
                status="developing",
                last_assessed_at=now - timedelta(days=2),
            )
            session.add(lc)
            session.flush()

            for step, score in enumerate([0.30, 0.38, 0.40, mastery]):
                hist = CompetencyHistory(
                    id=uuid.uuid4(),
                    learner_competency_id=lc.id,
                    mastery_score=score,
                    recorded_at=now - timedelta(days=6 - step),
                )
                session.add(hist)

            # Skill gap created due to low mastery despite high completion
            gap = SkillGap(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=bob.id,
                competency_id=comp.id,
                current_mastery=mastery,
                target_mastery=0.80,
                gap_size=round(0.80 - mastery, 2),
                severity="high",
                detected_at=now - timedelta(days=2),
            )
            session.add(gap)

        # =====================================================================
        # ARCHETYPE 3: Declining Performance Learner (Carol Clark)
        # =====================================================================
        print("  -> Configuring Archetype 3: Carol Clark (Started Strong / Steep Decline)")
        carol_enrollment = session.query(Enrollment).filter_by(user_id=carol.id, course_id=course.id).first()
        if carol_enrollment:
            carol_enrollment.progress_pct = 60.0
            carol_enrollment.last_activity_at = now - timedelta(days=3)

        for comp_code, mastery, start_m in [("ASYNC-PY", 0.78, 0.85), ("EVENT-STREAM", 0.42, 0.75)]:
            comp = competencies.get(comp_code)
            if not comp:
                continue
            lc = LearnerCompetency(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=carol.id,
                competency_id=comp.id,
                mastery_score=mastery,
                confidence_score=0.85,
                data_points_count=14,
                status="developing" if mastery < 0.50 else "competent",
                last_assessed_at=now - timedelta(days=3),
            )
            session.add(lc)
            session.flush()

            for step, score in enumerate([start_m, start_m - 0.1, start_m - 0.2, mastery]):
                hist = CompetencyHistory(
                    id=uuid.uuid4(),
                    learner_competency_id=lc.id,
                    mastery_score=score,
                    recorded_at=now - timedelta(days=10 - (step * 2)),
                )
                session.add(hist)

        # Flag Carol as at-risk
        carol_risk = LearnerRisk(
            id=uuid.uuid4(),
            org_id=acme.id,
            user_id=carol.id,
            course_id=course.id,
            risk_level="high",
            risk_score=0.74,
            risk_factors=[
                "Steep decline in Event Streaming assessment scores (dropped 33% across 3 attempts)",
                "No learning activity logged for 3 consecutive days after failing quiz",
                "High hesitation time detected on message streaming questions (>140s avg)",
            ],
            recommended_actions=[
                "Assign foundational remediation on Redis consumer groups and offset management",
                "Trigger automated manager notification to schedule 1-on-1 check-in",
                "Provide interactive guided sandbox exercise before next quiz attempt",
            ],
            is_resolved=False,
            detected_at=now - timedelta(days=3),
        )
        session.add(carol_risk)

        # =====================================================================
        # ARCHETYPE 4: Low-Mastery Disengaged Learner (Dan Davis)
        # =====================================================================
        print("  -> Configuring Archetype 4: Dan Davis (Disengaged / Critical Risk)")
        dan_enrollment = session.query(Enrollment).filter_by(user_id=dan.id, course_id=course.id).first()
        if dan_enrollment:
            dan_enrollment.progress_pct = 15.0
            dan_enrollment.last_activity_at = now - timedelta(days=12)

        for comp_code, mastery in [("ASYNC-PY", 0.28), ("EVENT-STREAM", 0.20)]:
            comp = competencies.get(comp_code)
            if not comp:
                continue
            lc = LearnerCompetency(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=dan.id,
                competency_id=comp.id,
                mastery_score=mastery,
                confidence_score=0.62,
                data_points_count=5,
                status="novice",
                last_assessed_at=now - timedelta(days=12),
            )
            session.add(lc)
            session.flush()

        dan_risk = LearnerRisk(
            id=uuid.uuid4(),
            org_id=acme.id,
            user_id=dan.id,
            course_id=course.id,
            risk_level="critical",
            risk_score=0.92,
            risk_factors=[
                "Inactivity duration exceeds 12 consecutive days",
                "Course progress stalled at 15%",
                "Failed Module 1 diagnostics with multiple skipped questions",
            ],
            recommended_actions=[
                "Send personalized re-engagement notification with simplified catch-up plan",
                "Alert engineering manager to review workload and training allocation",
            ],
            is_resolved=False,
            detected_at=now - timedelta(days=10),
        )
        session.add(dan_risk)

        # =====================================================================
        # 5. Cohort-Wide Emerging Skill Gap
        # =====================================================================
        print("  -> Configuring Cohort Emerging Skill Gap (EVENT-STREAM deficit)")
        comp_events = competencies.get("EVENT-STREAM")
        if comp_events:
            cohort_gap = SkillGap(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=None,  # Cohort-wide gap
                team_id=None,
                competency_id=comp_events.id,
                current_mastery=0.48,
                target_mastery=0.80,
                gap_size=0.32,
                severity="critical",
                detected_at=now - timedelta(days=4),
            )
            session.add(cohort_gap)

        # =====================================================================
        # 6. Learning Events Telemetry
        # =====================================================================
        print("  -> Emitting Granular Learning Event Telemetry...")
        event_records = [
            # Alice
            LearningEvent(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=alice.id,
                course_id=course.id,
                module_id=modules[0].id,
                event_type="assessment_attempt",
                payload={"assessment_id": str(uuid.uuid4()), "score": 1.0, "time_spent_seconds": 45, "result": "pass"},
                timestamp=now - timedelta(days=3),
                processed=True,
            ),
            LearningEvent(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=alice.id,
                course_id=course.id,
                module_id=modules[1].id,
                event_type="module_complete",
                payload={"progress_pct": 100, "duration_minutes": 52},
                timestamp=now - timedelta(days=2),
                processed=True,
            ),
            # Bob
            LearningEvent(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=bob.id,
                course_id=course.id,
                module_id=modules[0].id,
                event_type="assessment_attempt",
                payload={"score": 0.40, "time_spent_seconds": 18, "result": "fail", "fast_guess": True},
                timestamp=now - timedelta(days=4),
                processed=True,
            ),
            # Carol
            LearningEvent(
                id=uuid.uuid4(),
                org_id=acme.id,
                user_id=carol.id,
                course_id=course.id,
                module_id=modules[1].id,
                event_type="assessment_attempt",
                payload={"score": 0.35, "time_spent_seconds": 140, "result": "fail", "hesitation": True},
                timestamp=now - timedelta(days=3),
                processed=True,
            ),
        ]
        session.add_all(event_records)

        # =====================================================================
        # 7. Grounded AI Insight
        # =====================================================================
        print("  -> Generating Sample Grounded AI Executive Insight...")
        insight = AIInsight(
            id=uuid.uuid4(),
            org_id=acme.id,
            report_type="executive",
            scope_type="cohort",
            scope_id=course.id,
            narrative_text=(
                "Cohort performance analysis for PY-DIST-101 reveals a high-risk bifurcation in learning outcomes. "
                "While 25% of learners (e.g. Alice Adams) demonstrate accelerated mastery (>0.88), 50% of the cohort "
                "is encountering a severe conceptual bottleneck in Event-Driven Message Streaming (EVENT-STREAM, gap 0.32). "
                "Notably, learner Bob Bennett has achieved 100% course completion while maintaining a critical competency deficit "
                "(mastery 0.38), indicating rapid skimming rather than knowledge retention. "
                "Learner Carol Clark displays a 33% performance regression and has been flagged for targeted remediation. "
                "Immediate curriculum reinforcement on Redis Streams consumer groups is recommended prior to Module 3 release."
            ),
            structured_data={
                "cohort_size": 4,
                "avg_mastery": 0.54,
                "at_risk_count": 2,
                "top_gap_competency": "EVENT-STREAM",
                "gap_magnitude": 0.32,
            },
            confidence_score=0.91,
            citations=[
                {
                    "source_type": "competency_assessment",
                    "source_id": str(competencies["EVENT-STREAM"].id),
                    "snippet": "EVENT-STREAM cohort average mastery score is 0.48 against target benchmark of 0.80.",
                    "score": 0.96,
                },
                {
                    "source_type": "learner_risk",
                    "source_id": str(carol_risk.id),
                    "snippet": "Learner Carol Clark risk score 0.74 due to 33% score decline and 3-day inactivity.",
                    "score": 0.94,
                },
                {
                    "source_type": "enrollment_anomaly",
                    "source_id": str(bob_enrollment.id if bob_enrollment else uuid.uuid4()),
                    "snippet": "Bob Bennett: 100% completion with developing mastery (0.38) and fast completion velocity.",
                    "score": 0.89,
                },
            ],
            model_used="gpt-4o-mini",
        )
        session.add(insight)

        session.commit()
        print("\n[OK] Successfully Generated Complete Telemetry & Archetypes Demo Dataset!")

    except Exception as e:
        session.rollback()
        print(f"\n[FAIL] Generating demo data failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    generate_demo_telemetry()
