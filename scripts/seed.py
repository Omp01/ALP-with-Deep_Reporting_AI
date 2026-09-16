"""
Database Seeding Script for Adaptive LMS.

Populates the database with:
- 2 Organizations (Acme Corporation, TechNova Systems)
- Multiple Users per organization across all 5 roles (system_admin, org_admin, instructor, manager, learner)
- Teams with manager assignments and learner memberships
- Courses with structured Modules
- Competencies mapped to courses and modules
- Assessment questions tagged with psychometric difficulty and competencies
- Initial enrollments

Run via:
    python scripts/seed.py
    or: docker exec alms-api python scripts/seed.py
"""

import sys
import os
import uuid
from datetime import datetime, timedelta

# Ensure python path includes services/api and shared
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "services", "api"))

from app.core.security import hash_password
from app.core.database import SessionLocal
from app.models import (
    Organization,
    User,
    Team,
    UserTeam,
    Course,
    Module,
    ContentItem,
    ContentChunk,
    Competency,
    CourseCompetency,
    ModuleCompetency,
    AssessmentItem,
    Enrollment,
    LearnerCompetency,
    CompetencyHistory,
    SkillGap,
    LearnerRisk,
)

DEFAULT_PASSWORD_HASH = hash_password("Password123!")


def seed_database():
    session = SessionLocal()
    try:
        print("Starting Adaptive LMS Database Seeding...")

        # ---------------------------------------------------------------------
        # 1. Organizations
        # ---------------------------------------------------------------------
        existing_org = session.query(Organization).filter_by(slug="acme-corp").first()
        if existing_org:
            print("  [INFO] Database already seeded. Skipping initial creation.")
            return

        acme_org = Organization(
            id=uuid.uuid4(),
            name="Acme Corporation",
            slug="acme-corp",
            is_active=True,
            settings={"theme": "light", "allowed_domains": ["acme.com"], "max_users": 500},
        )
        technova_org = Organization(
            id=uuid.uuid4(),
            name="TechNova Systems",
            slug="technova",
            is_active=True,
            settings={"theme": "light", "allowed_domains": ["technova.com"], "max_users": 200},
        )
        session.add_all([acme_org, technova_org])
        session.flush()
        print(f"  [OK] Created 2 Organizations: {acme_org.name}, {technova_org.name}")

        # ---------------------------------------------------------------------
        # 2. Users
        # ---------------------------------------------------------------------
        users = [
            # System Admin (Cross-tenant access)
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="sysadmin@adaptivelms.io",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Alexander SystemAdmin",
                role="system_admin",
                is_active=True,
            ),
            # Acme Corporation Users
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="admin@acme.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Arthur Admin",
                role="org_admin",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="sarah.instructor@acme.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Dr. Sarah Instructor",
                role="instructor",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="marcus.manager@acme.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Marcus Manager",
                role="manager",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="alice.learner@acme.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Alice Adams",
                role="learner",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="bob.learner@acme.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Bob Bennett",
                role="learner",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="carol.learner@acme.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Carol Clark",
                role="learner",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                email="dan.learner@acme.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Dan Davis",
                role="learner",
                is_active=True,
            ),
            # TechNova Systems Users
            User(
                id=uuid.uuid4(),
                org_id=technova_org.id,
                email="admin@technova.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Tara TechAdmin",
                role="org_admin",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=technova_org.id,
                email="david.instructor@technova.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="David Dean",
                role="instructor",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=technova_org.id,
                email="rachel.manager@technova.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Rachel Ray",
                role="manager",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=technova_org.id,
                email="elena.learner@technova.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Elena Evans",
                role="learner",
                is_active=True,
            ),
            User(
                id=uuid.uuid4(),
                org_id=technova_org.id,
                email="frank.learner@technova.com",
                password_hash=DEFAULT_PASSWORD_HASH,
                full_name="Frank Foster",
                role="learner",
                is_active=True,
            ),
        ]
        session.add_all(users)
        session.flush()
        print(f"  [OK] Created {len(users)} Users across 5 Roles")

        # Map users for easy reference
        u_map = {u.email: u for u in users}

        # ---------------------------------------------------------------------
        # 3. Teams
        # ---------------------------------------------------------------------
        team_frontend = Team(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            name="Frontend Engineering Team",
            description="Core client-side and web infrastructure squad",
            manager_id=u_map["marcus.manager@acme.com"].id,
        )
        team_data = Team(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            name="Data Platform Team",
            description="Data pipelines, analytics, and ML platform engineers",
            manager_id=u_map["marcus.manager@acme.com"].id,
        )
        team_cloud = Team(
            id=uuid.uuid4(),
            org_id=technova_org.id,
            name="Cloud Infrastructure Team",
            description="Site reliability, Kubernetes, and cloud infrastructure",
            manager_id=u_map["rachel.manager@technova.com"].id,
        )
        session.add_all([team_frontend, team_data, team_cloud])
        session.flush()

        # Memberships
        memberships = [
            UserTeam(user_id=u_map["alice.learner@acme.com"].id, team_id=team_frontend.id, org_id=acme_org.id),
            UserTeam(user_id=u_map["bob.learner@acme.com"].id, team_id=team_frontend.id, org_id=acme_org.id),
            UserTeam(user_id=u_map["carol.learner@acme.com"].id, team_id=team_data.id, org_id=acme_org.id),
            UserTeam(user_id=u_map["dan.learner@acme.com"].id, team_id=team_data.id, org_id=acme_org.id),
            UserTeam(user_id=u_map["elena.learner@technova.com"].id, team_id=team_cloud.id, org_id=technova_org.id),
            UserTeam(user_id=u_map["frank.learner@technova.com"].id, team_id=team_cloud.id, org_id=technova_org.id),
        ]
        session.add_all(memberships)
        session.flush()
        print("  [OK] Created 3 Teams and user team memberships")

        # ---------------------------------------------------------------------
        # 4. Competencies Framework
        # ---------------------------------------------------------------------
        comp_async = Competency(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            name="Asynchronous Python & Concurrency",
            code="ASYNC-PY",
            description="Mastery of asyncio event loops, coroutines, tasks, and async context managers",
            taxonomy_level="apply",
        )
        comp_events = Competency(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            name="Event-Driven Message Streaming",
            code="EVENT-STREAM",
            description="Architecture of distributed event streams, pub/sub patterns, and consumer groups with Redis/Kafka",
            taxonomy_level="analyze",
        )
        comp_db = Competency(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            name="Database Query & Index Optimization",
            code="DB-OPT",
            description="Relational indexing, execution plans, connection pooling, and ORM query optimization",
            taxonomy_level="evaluate",
        )
        comp_rag = Competency(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            name="Vector Embeddings & Semantic Search",
            code="VEC-RAG",
            description="Embedding models, similarity distance metrics, pgvector indexing, and grounding techniques",
            taxonomy_level="create",
        )
        session.add_all([comp_async, comp_events, comp_db, comp_rag])
        session.flush()
        print("  [OK] Created 4 Competencies in framework")

        # ---------------------------------------------------------------------
        # 5. Courses & Modules
        # ---------------------------------------------------------------------
        course_python = Course(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            title="Full-Stack Python & Distributed Systems",
            code="PY-DIST-101",
            description="In-depth training on building resilient, scalable asynchronous microservices in Python.",
            status="published",
            created_by_id=u_map["sarah.instructor@acme.com"].id,
            course_metadata={"target_audience": "Software Engineers", "estimated_hours": 12},
        )
        session.add(course_python)
        session.flush()

        # Map competencies to course
        session.add_all([
            CourseCompetency(course_id=course_python.id, competency_id=comp_async.id, target_mastery=0.85, is_primary=True),
            CourseCompetency(course_id=course_python.id, competency_id=comp_events.id, target_mastery=0.80, is_primary=True),
            CourseCompetency(course_id=course_python.id, competency_id=comp_db.id, target_mastery=0.75, is_primary=False),
        ])

        # Modules
        mod1 = Module(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            course_id=course_python.id,
            title="Module 1: FastAPI & Async Coroutines",
            description="Deep dive into ASGI, asyncio tasks, non-blocking I/O, and lifespan management.",
            sequence_order=1,
            estimated_duration_mins=45,
        )
        mod2 = Module(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            course_id=course_python.id,
            title="Module 2: Event Streaming with Redis Streams",
            description="XADD, XREADGROUP, consumer group acknowledgements, and dead-letter handling.",
            sequence_order=2,
            estimated_duration_mins=60,
        )
        mod3 = Module(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            course_id=course_python.id,
            title="Module 3: Relational Persistence with SQLAlchemy Async",
            description="Managing async sessions, migrations with Alembic, and connection pool sizing.",
            sequence_order=3,
            estimated_duration_mins=50,
        )
        session.add_all([mod1, mod2, mod3])
        session.flush()

        # Module Competencies
        session.add_all([
            ModuleCompetency(module_id=mod1.id, competency_id=comp_async.id, weight=1.0),
            ModuleCompetency(module_id=mod2.id, competency_id=comp_events.id, weight=1.0),
            ModuleCompetency(module_id=mod3.id, competency_id=comp_db.id, weight=1.0),
        ])
        session.flush()

        # Content Items
        item1 = ContentItem(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            module_id=mod1.id,
            title="Modern Asynchronous Patterns in Python 3.11+",
            content_type="text",
            raw_text="Python's asyncio framework provides cooperative multitasking via an event loop. Understanding coroutines (async def) and tasks (asyncio.create_task) is essential for non-blocking I/O operations such as network calls and database queries.",
            chunk_count=1,
        )
        item2 = ContentItem(
            id=uuid.uuid4(),
            org_id=acme_org.id,
            module_id=mod2.id,
            title="Scalable Stream Processing with Consumer Groups",
            content_type="text",
            raw_text="Redis Streams provides append-only log semantics with consumer group partitioning. Using XACK ensures that messages are only marked as processed once downstream workers have committed changes.",
            chunk_count=1,
        )
        session.add_all([item1, item2])
        session.flush()

        # Content Chunks
        session.add_all([
            ContentChunk(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                content_item_id=item1.id,
                chunk_index=0,
                text_content=item1.raw_text,
                token_count=35,
            ),
            ContentChunk(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                content_item_id=item2.id,
                chunk_index=0,
                text_content=item2.raw_text,
                token_count=32,
            ),
        ])
        session.flush()
        print("  [OK] Created Courses, Modules, Content Items, and Chunks")

        # ---------------------------------------------------------------------
        # 6. Assessment Items
        # ---------------------------------------------------------------------
        assessments = [
            AssessmentItem(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                module_id=mod1.id,
                competency_id=comp_async.id,
                question_text="What happens if a CPU-intensive computation is executed directly inside an asyncio coroutine without using run_in_executor?",
                question_type="multiple_choice",
                options=[
                    {"id": "a", "text": "It runs in a separate thread automatically."},
                    {"id": "b", "text": "It blocks the entire event loop, delaying all concurrent tasks."},
                    {"id": "c", "text": "Python raises a BlockingIOError immediately."},
                    {"id": "d", "text": "It gets executed asynchronously in the background."},
                ],
                correct_answer={"answer": "b"},
                explanation="Because asyncio uses cooperative multitasking on a single thread, CPU-bound tasks block the event loop from advancing other coroutines unless offloaded to a process or thread pool.",
                difficulty_score=0.4,
                discrimination_index=1.2,
                is_ai_generated=False,
                quality_flag="approved",
            ),
            AssessmentItem(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                module_id=mod1.id,
                competency_id=comp_async.id,
                question_text="Which construct should be used to concurrently wait for multiple coroutines and return their results as a list?",
                question_type="multiple_choice",
                options=[
                    {"id": "a", "text": "asyncio.gather(*coroutines)"},
                    {"id": "b", "text": "asyncio.wait_all(*coroutines)"},
                    {"id": "c", "text": "asyncio.sync_tasks(*coroutines)"},
                    {"id": "d", "text": "asyncio.join(*coroutines)"},
                ],
                correct_answer={"answer": "a"},
                explanation="asyncio.gather takes awaitable objects and returns an aggregate list of results in corresponding order.",
                difficulty_score=0.3,
                discrimination_index=1.0,
                is_ai_generated=False,
                quality_flag="approved",
            ),
            AssessmentItem(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                module_id=mod2.id,
                competency_id=comp_events.id,
                question_text="In Redis Streams, which command confirms that a specific message was successfully processed by a consumer in a consumer group?",
                question_type="multiple_choice",
                options=[
                    {"id": "a", "text": "XDEL"},
                    {"id": "b", "text": "XACK"},
                    {"id": "c", "text": "XCONFIRM"},
                    {"id": "d", "text": "XCOMMIT"},
                ],
                correct_answer={"answer": "b"},
                explanation="XACK removes the message from the Pending Entries List (PEL) for that consumer group.",
                difficulty_score=0.5,
                discrimination_index=1.4,
                is_ai_generated=False,
                quality_flag="approved",
            ),
            AssessmentItem(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                module_id=mod3.id,
                competency_id=comp_db.id,
                question_text="When executing high-throughput queries on PostgreSQL, which index type is most optimal for equality lookups on high-cardinality UUID primary keys?",
                question_type="multiple_choice",
                options=[
                    {"id": "a", "text": "B-tree (default)"},
                    {"id": "b", "text": "BRIN index"},
                    {"id": "c", "text": "GIN index"},
                    {"id": "d", "text": "GiST index"},
                ],
                correct_answer={"answer": "a"},
                explanation="B-tree indexes provide O(log n) lookups and are the gold standard for unique equality operations.",
                difficulty_score=0.6,
                discrimination_index=1.1,
                is_ai_generated=False,
                quality_flag="approved",
            ),
        ]
        session.add_all(assessments)
        session.flush()
        print(f"  [OK] Created {len(assessments)} Assessment Items")

        # ---------------------------------------------------------------------
        # 7. Initial Enrollments
        # ---------------------------------------------------------------------
        learners = [
            u_map["alice.learner@acme.com"],
            u_map["bob.learner@acme.com"],
            u_map["carol.learner@acme.com"],
            u_map["dan.learner@acme.com"],
        ]
        for learner in learners:
            enrollment = Enrollment(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                user_id=learner.id,
                course_id=course_python.id,
                status="active",
                progress_pct=0.0,
                enrolled_at=datetime.utcnow() - timedelta(days=7),
                last_activity_at=datetime.utcnow(),
            )
            session.add(enrollment)
        session.commit()
        print(f"  [OK] Enrolled {len(learners)} Learners in Course {course_python.code}")

        print("\nDatabase Seeding Completed Successfully! 100% Ready.")

    except Exception as e:
        session.rollback()
        print(f"  [FAIL] Seeding failed with error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_database()
