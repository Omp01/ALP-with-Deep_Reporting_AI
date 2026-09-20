"""
Test harness for the foundation suite.

Integration tests run against a real PostgreSQL database that is created from
scratch for the session by running the project's actual Alembic migrations
(`alembic upgrade head`). That means the schema under test is the schema that
ships — including constraints — rather than a `create_all()` approximation, and
the migration chain itself is exercised on every run.

Safety: the database name must contain "test" and must differ from the
application's own database, otherwise the run aborts. The dev database is never
touched.

Configuration (all optional; defaults match the docker-compose dev database):
    TEST_DATABASE_NAME   name of the throwaway database (default: adaptive_lms_test)
"""

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
for path in (str(API_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

# --- Point the application at the test database BEFORE app.core.database is imported.
from app.core.config import settings  # noqa: E402

_dev_sync_url = make_url(settings.database_url_sync)
TEST_DB_NAME = os.getenv("TEST_DATABASE_NAME", "adaptive_lms_test")
if "test" not in TEST_DB_NAME or TEST_DB_NAME == _dev_sync_url.database:
    raise RuntimeError(
        f"Refusing to run: test database name '{TEST_DB_NAME}' must contain 'test' "
        f"and differ from the application database '{_dev_sync_url.database}'."
    )
TEST_SYNC_URL = _dev_sync_url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)
TEST_ASYNC_URL = make_url(settings.database_url).set(database=TEST_DB_NAME).render_as_string(hide_password=False)
settings.database_url_sync = TEST_SYNC_URL
settings.database_url = TEST_ASYNC_URL

import httpx  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.database import SessionLocal, get_db  # noqa: E402
from app.core.rbac import legacy_storage_value  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.models import (  # noqa: E402
    Competency,
    ContentItem,
    Course,
    Module,
    Organization,
    RoleDefinition,
    User,
    UserRole,
)


# ---------------------------------------------------------------------------
# Database lifecycle
# ---------------------------------------------------------------------------
def _admin_connection():
    url = _dev_sync_url.set(database="postgres")
    conn = psycopg2.connect(
        host=url.host, port=url.port, user=url.username, password=url.password, dbname=url.database
    )
    conn.autocommit = True
    return conn


def _recreate_database() -> None:
    conn = _admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (TEST_DB_NAME,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
            cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        conn.close()


def _run_migrations() -> None:
    env = {**os.environ, "DATABASE_URL_SYNC": TEST_SYNC_URL}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "database/alembic.ini", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture(scope="session")
def test_database():
    """Create the throwaway database and migrate it to head, once per session (integration tests only)."""
    _recreate_database()
    _run_migrations()
    yield TEST_DB_NAME


# ---------------------------------------------------------------------------
# Data factories (synchronous; used to arrange state directly in the database)
# ---------------------------------------------------------------------------
def _uid() -> str:
    return uuid.uuid4().hex[:8]


def make_org(session, slug: Optional[str] = None) -> Organization:
    slug = slug or f"org-{_uid()}"
    org = Organization(id=uuid.uuid4(), name=slug.title(), slug=slug, is_active=True, settings={})
    session.add(org)
    session.flush()
    return org


def make_user(session, org: Organization, roles: Iterable[str], *, email: Optional[str] = None,
              set_role_links: bool = True, legacy_role: Optional[str] = None) -> User:
    """Create a user with the given canonical roles (and matching legacy `users.role`)."""
    role_list = list(roles)
    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        email=email or f"user-{_uid()}@{org.slug}.test",
        password_hash="not-a-real-hash",
        full_name=f"User {_uid()}",
        role=legacy_role or legacy_storage_value(role_list),
        is_active=True,
    )
    session.add(user)
    session.flush()
    if set_role_links:
        catalogue = {r.code: r for r in session.query(RoleDefinition).all()}
        for code in role_list:
            session.add(UserRole(user_id=user.id, role_id=catalogue[code].id, org_id=org.id))
        session.flush()
    return user


def make_competency(session, org: Organization, code: Optional[str] = None, *, domain: str = "test",
                    difficulty: float = 0.5, taxonomy_level: str = "apply") -> Competency:
    code = code or f"{domain}.{_uid()}"
    comp = Competency(
        id=uuid.uuid4(), org_id=org.id, code=code, name=code.replace(".", " ").title(),
        taxonomy_level=taxonomy_level, domain=domain, difficulty=difficulty,
    )
    session.add(comp)
    session.flush()
    return comp


def make_course(session, org: Organization, owner: User, *, status: str = "published",
                content_seconds: Iterable[int] = (600, 900)) -> Course:
    code = f"C-{_uid()}"
    course = Course(id=uuid.uuid4(), org_id=org.id, title=f"Course {code}", code=code, status=status,
                    created_by_id=owner.id, instructor_id=owner.id)
    session.add(course)
    session.flush()
    module = Module(id=uuid.uuid4(), org_id=org.id, course_id=course.id, title="Module 1", sequence_order=1)
    session.add(module)
    session.flush()
    for index, seconds in enumerate(content_seconds):
        session.add(ContentItem(
            id=uuid.uuid4(), org_id=org.id, course_id=course.id, module_id=module.id,
            title=f"Item {index}", content_type="VIDEO", duration_seconds=seconds, order_index=index,
            status="published",
        ))
    session.flush()
    return course


def make_item(session, org: Organization, course: Course, module: Module, *, content_type: str = "ARTICLE",
              status: str = "published", seconds: int = 300, order_index: int = 0, title: Optional[str] = None,
              **extra) -> ContentItem:
    """Add one lesson item to a module."""
    item = ContentItem(
        id=uuid.uuid4(), org_id=org.id, course_id=course.id, module_id=module.id,
        title=title or f"{content_type.title()} {_uid()}", content_type=content_type, status=status,
        duration_seconds=seconds, order_index=order_index, **extra,
    )
    session.add(item)
    session.flush()
    return item


def make_quiz(session, org: Organization, course: Course, module: Module, item: ContentItem, *,
              questions: int = 2, passing_score: float = 70.0, competency: Optional[Competency] = None):
    """A quiz linked to its lesson item, with `questions` single-answer questions (option A is correct)."""
    from app.models import Quiz, QuizOption, QuizQuestion

    quiz = Quiz(id=uuid.uuid4(), org_id=org.id, course_id=course.id, module_id=module.id, title=item.title,
                passing_score=passing_score, time_limit_mins=10, max_attempts=5, content_item_id=item.id)
    session.add(quiz)
    session.flush()
    built = []
    for index in range(questions):
        question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_text=f"Question {index}?", points=10,
                                order_index=index, competency_id=competency.id if competency else None)
        session.add(question)
        session.flush()
        options = [QuizOption(id=uuid.uuid4(), question_id=question.id, option_text=label,
                              is_correct=(label == "A"), order_index=i) for i, label in enumerate("AB")]
        session.add_all(options)
        built.append((question, options))
    session.flush()
    return quiz, built


def make_written_question(session, quiz, *, competency: Optional[Competency] = None, text: str = "What does an inner join return?",
                          expected: Optional[str] = "Only the rows that have a matching value in both tables.", points: int = 10,
                          question_type: str = "short_answer", rubric=None, difficulty: Optional[float] = None, order_index: int = 50):
    """A written question on a quiz. It has no options: it is graded by the grading agent (or a person)."""
    from app.models import QuizQuestion

    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_text=text, question_type=question_type, points=points, order_index=order_index,
                            competency_id=competency.id if competency else None, expected_answer=expected, difficulty=difficulty,
                            rubric=rubric if rubric is not None else [{"criterion": "Matching rows", "weight": 1.0, "description": "Says only matching rows are kept"}])
    session.add(question)
    session.flush()
    return question


def make_assignment(session, org: Organization, course: Course, module: Module, item: ContentItem):
    from app.models import Assignment

    assignment = Assignment(id=uuid.uuid4(), org_id=org.id, course_id=course.id, module_id=module.id,
                            title=item.title, instructions="Build the thing.", content_item_id=item.id,
                            rubric={"correctness": {"weight": 1.0}})
    session.add(assignment)
    session.flush()
    return assignment


def enroll(session, org: Organization, user: User, course: Course):
    from app.models import Enrollment

    enrollment = Enrollment(id=uuid.uuid4(), org_id=org.id, user_id=user.id, course_id=course.id, status="active")
    session.add(enrollment)
    session.flush()
    return enrollment


def set_mastery(session, org: Organization, user: User, competency: Competency, mastery: float,
                confidence: float = 0.8, evidence: int = 6):
    from app.models import LearnerCompetency

    row = LearnerCompetency(id=uuid.uuid4(), org_id=org.id, user_id=user.id, competency_id=competency.id,
                            mastery_score=mastery, confidence_score=confidence, data_points_count=evidence,
                            status="developing")
    session.add(row)
    session.flush()
    return row


def only_module(session, course: Course) -> Module:
    return session.query(Module).filter_by(course_id=course.id).one()


def token_for(user: User) -> str:
    return create_access_token(subject=str(user.id), claims={"org_id": str(user.org_id), "role": user.role})


def auth(user: User) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}"}


# ---------------------------------------------------------------------------
# A fixed two-tenant world used by the isolation tests
# ---------------------------------------------------------------------------
@dataclass
class Tenant:
    org: Organization
    learner: User
    manager: User
    ld_admin: User
    org_admin: User
    course: Course
    module: Module
    content: ContentItem
    competencies: List[Competency] = field(default_factory=list)


@dataclass
class World:
    a: Tenant
    b: Tenant
    super_admin: User  # lives in tenant A


def _build_tenant(session, label: str) -> Tenant:
    org = make_org(session, f"{label}-{_uid()}")
    learner = make_user(session, org, ["learner"])
    manager = make_user(session, org, ["manager"])
    ld_admin = make_user(session, org, ["ld_admin"])
    org_admin = make_user(session, org, ["org_admin"])
    course = make_course(session, org, ld_admin)
    module = session.query(Module).filter_by(course_id=course.id).one()
    content = session.query(ContentItem).filter_by(course_id=course.id).first()
    comps = [make_competency(session, org, f"{label}.basics"), make_competency(session, org, f"{label}.advanced")]
    return Tenant(org, learner, manager, ld_admin, org_admin, course, module, content, comps)


@pytest.fixture(scope="session")
def world(test_database) -> World:
    session = SessionLocal(expire_on_commit=False)  # keep loaded attributes readable after detaching
    try:
        a = _build_tenant(session, "alpha")
        b = _build_tenant(session, "beta")
        super_admin = make_user(session, a.org, ["super_admin"])
        session.commit()
        session.expunge_all()
        return World(a, b, super_admin)
    finally:
        session.close()


@pytest.fixture
def db_session(test_database):
    """A synchronous session for arranging or asserting database state directly."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# HTTP client (in-process ASGI, no server needed)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(test_database):
    from app.main import app

    engine = create_async_engine(TEST_ASYNC_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest_asyncio.fixture
async def ingestion_env(test_database, monkeypatch):
    """
    Everything the ingestion pipeline touches, replaced for the duration of a test:
    in-memory storage, an AI provider that is DOWN by default (so nothing can reach a real
    one), no embedder, no transcription engine, and jobs that run inline in the request.
    """
    from app.core.config import settings
    from app.core.storage import storage_client
    from app.ingestion import ai as ingestion_ai
    from app.ingestion import embeddings, pipeline, transcription
    from tests.foundation.fakes import MemoryStorage, outage

    engine = create_async_engine(TEST_ASYNC_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    store = MemoryStorage()
    for name in ("upload_file", "download_file", "delete_file"):
        monkeypatch.setattr(storage_client, name, getattr(store, name))
    monkeypatch.setattr(settings, "ingestion_run_inline", True)
    monkeypatch.setattr(settings, "allowed_file_types", "pdf,docx,pptx,txt,md,mp4,webm,mov,mp3,wav,m4a")   # independent of the developer's .env
    monkeypatch.setattr(settings, "ai_embedding_model", "")

    pipeline.set_session_factory(session_factory)
    ingestion_ai.set_provider_override(lambda task: outage())
    embeddings.set_embedder_override(None)
    transcription.set_transcriber_override(None)
    pipeline.set_youtube_override(None)

    class Env:
        storage = store

        @staticmethod
        def use_ai(provider):
            ingestion_ai.set_provider_override(lambda task: provider)

        @staticmethod
        def use_youtube(transport):
            from app.ingestion.youtube import YouTubeClient
            pipeline.set_youtube_override(YouTubeClient(transport=transport))

        session = staticmethod(session_factory)

    yield Env
    pipeline.set_session_factory(None)
    ingestion_ai.set_provider_override(None)
    pipeline.set_youtube_override(None)
    await engine.dispose()


@pytest_asyncio.fixture
async def grading_env(test_database):
    """The grading agent's model, replaced: DOWN by default, so a test must choose what it answers (`use(ScriptedAI(...))`)."""
    from app.ingestion import ai as ingestion_ai
    from tests.foundation.fakes import outage

    ingestion_ai.set_provider_override(lambda task: outage())

    class Env:
        @staticmethod
        def use(provider):
            ingestion_ai.set_provider_override(lambda task: provider)
            return provider

    yield Env
    ingestion_ai.set_provider_override(None)


API = "/api/v1"
