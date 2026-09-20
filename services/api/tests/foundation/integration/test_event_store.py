"""
The event store against a real PostgreSQL schema: what the database itself guarantees
(append-only, no erasing evidence, sessions that belong to their learner), what the store
guarantees under concurrency (one event per idempotency key, one open session per course),
and how delivery to the stream is retried.
"""

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.events import sessions, store
from app.models import EventOutbox, LearningEvent, LearningSession
from tests.foundation.conftest import (
    TEST_ASYNC_URL, enroll, make_competency, make_course, make_item, make_org, make_quiz, make_user, only_module,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def scene(db_session):
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    other = make_user(db_session, org, ["learner"])
    course = make_course(db_session, org, ld, content_seconds=[])
    module = only_module(db_session, course)
    item = make_item(db_session, org, course, module, content_type="VIDEO")
    db_session.commit()
    return org, learner, other, course, module, item


@pytest.fixture
async def factory(test_database):
    engine = create_async_engine(TEST_ASYNC_URL, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


async def record_in_new_session(factory, **kwargs):
    async with factory() as db:
        result = await store.record(db, **kwargs)
        await db.commit()
        return result


def add_event(db_session, org, user, item, **extra):
    event = LearningEvent(id=uuid.uuid4(), org_id=org.id, user_id=user.id, course_id=item.course_id, content_id=item.id,
                          event_type="content_started", payload={"content_type": "VIDEO"}, timestamp=datetime.utcnow(), **extra)
    db_session.add(event)
    db_session.commit()
    return event


# ============================================================ what the database guarantees
def test_events_cannot_be_updated(db_session, scene):
    org, learner, _, _, _, item = scene
    event = add_event(db_session, org, learner, item)
    with pytest.raises(DBAPIError) as info:
        db_session.execute(text("UPDATE learning_events SET event_type = 'question_answered' WHERE id = :i"), {"i": event.id})
    assert "append-only" in str(info.value)
    db_session.rollback()


def test_events_cannot_be_deleted(db_session, scene):
    org, learner, _, _, _, item = scene
    event = add_event(db_session, org, learner, item)
    with pytest.raises(DBAPIError) as info:
        db_session.execute(text("DELETE FROM learning_events WHERE id = :i"), {"i": event.id})
    assert "append-only" in str(info.value)
    db_session.rollback()


def test_the_orm_cannot_quietly_rewrite_an_event_either(db_session, scene):
    org, learner, _, _, _, item = scene
    event = add_event(db_session, org, learner, item)
    event.payload = {"tampered": True}
    with pytest.raises(DBAPIError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("table, column", [("users", "user_id"), ("courses", "course_id"), ("content_items", "content_id"),
                                           ("modules", "module_id"), ("organizations", "org_id")])
def test_removing_something_an_event_refers_to_is_refused_not_cascaded(db_session, scene, table, column):
    """Evidence must not vanish (CASCADE) or be rewritten (SET NULL, which is an UPDATE) when its subject is removed."""
    org, learner, _, course, module, item = scene
    event = LearningEvent(id=uuid.uuid4(), org_id=org.id, user_id=learner.id, course_id=course.id, module_id=module.id,
                          content_id=item.id, event_type="content_started", payload={}, timestamp=datetime.utcnow())
    db_session.add(event)
    db_session.commit()
    target = {"user_id": learner.id, "course_id": course.id, "content_id": item.id, "module_id": module.id, "org_id": org.id}[column]
    with pytest.raises((IntegrityError, DBAPIError)):
        db_session.execute(text(f"DELETE FROM {table} WHERE id = :i"), {"i": target})
    db_session.rollback()
    assert db_session.get(LearningEvent, event.id) is not None


def test_an_event_cannot_point_at_another_learners_session(db_session, scene):
    org, learner, other, course, _, item = scene
    session = LearningSession(id=uuid.uuid4(), org_id=org.id, user_id=other.id, course_id=course.id)
    db_session.add(session)
    db_session.commit()
    db_session.add(LearningEvent(id=uuid.uuid4(), org_id=org.id, user_id=learner.id, session_id=session.id, course_id=course.id,
                                 content_id=item.id, event_type="content_started", payload={}, timestamp=datetime.utcnow()))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_an_event_cannot_point_at_another_tenants_session(db_session, scene):
    org, learner, _, course, _, item = scene
    foreign_org = make_org(db_session)
    foreign_owner = make_user(db_session, foreign_org, ["ld_admin"])
    foreign_course = make_course(db_session, foreign_org, foreign_owner, content_seconds=[])
    foreign_session = LearningSession(id=uuid.uuid4(), org_id=foreign_org.id, user_id=foreign_owner.id, course_id=foreign_course.id)
    db_session.add(foreign_session)
    db_session.commit()
    db_session.add(LearningEvent(id=uuid.uuid4(), org_id=org.id, user_id=learner.id, session_id=foreign_session.id,
                                 event_type="content_started", payload={}, timestamp=datetime.utcnow()))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_session_cannot_end_before_it_started_or_have_half_an_ending(db_session, scene):
    org, learner, _, course, _, _ = scene
    now = datetime.utcnow()
    for kwargs in (dict(ended_at=now - timedelta(hours=1), end_reason="explicit", started_at=now),
                   dict(ended_at=now + timedelta(hours=1), end_reason=None, started_at=now),
                   dict(ended_at=None, end_reason="explicit", started_at=now),
                   dict(ended_at=now + timedelta(hours=1), end_reason="because", started_at=now)):
        db_session.add(LearningSession(id=uuid.uuid4(), org_id=org.id, user_id=learner.id, course_id=course.id, **kwargs))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_the_database_allows_one_open_session_per_learner_per_course(db_session, scene):
    org, learner, _, course, _, _ = scene
    db_session.add(LearningSession(id=uuid.uuid4(), org_id=org.id, user_id=learner.id, course_id=course.id))
    db_session.commit()
    db_session.add(LearningSession(id=uuid.uuid4(), org_id=org.id, user_id=learner.id, course_id=course.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_per_answer_columns_reject_impossible_values(db_session, scene):
    org, _, _, course, module, item = scene
    quiz_item = make_item(db_session, org, course, module, content_type="QUIZ")
    quiz, built = make_quiz(db_session, org, course, module, quiz_item, questions=1)
    db_session.commit()
    question = built[0][0]
    for bad in (2.0, -0.1):
        db_session.execute(text("UPDATE quiz_questions SET difficulty = NULL WHERE id = :i"), {"i": question.id})
        with pytest.raises(DBAPIError):
            db_session.execute(text("UPDATE quiz_questions SET difficulty = :d WHERE id = :i"), {"d": bad, "i": question.id})
        db_session.rollback()


# ====================================================================== idempotency and races
async def test_the_same_key_is_recorded_once(factory, scene):
    org, learner, _, course, _, item = scene
    kw = dict(org_id=org.id, user_id=learner.id, event_type="lesson_opened", course_id=course.id, content_id=item.id, idempotency_key="retry-1")
    first = await record_in_new_session(factory, **kw)
    second = await record_in_new_session(factory, **kw)
    assert first.created and not second.created and first.event.id == second.event.id


async def test_simultaneous_retries_record_one_event(factory, scene, db_session):
    """Race safety: select-then-insert let two requests both insert; the unique key plus ON CONFLICT does not."""
    org, learner, _, course, _, item = scene
    kw = dict(org_id=org.id, user_id=learner.id, event_type="lesson_opened", course_id=course.id, content_id=item.id, idempotency_key="race-1")
    results = await asyncio.gather(*[record_in_new_session(factory, **kw) for _ in range(8)])
    assert sum(1 for r in results if r.created) == 1
    assert len({r.event.id for r in results}) == 1
    assert db_session.query(LearningEvent).filter_by(org_id=org.id, idempotency_key="race-1").count() == 1


async def test_the_same_key_in_different_tenants_are_different_events(factory, scene, db_session):
    org, learner, _, course, _, item = scene
    other_org = make_org(db_session)
    other_owner = make_user(db_session, other_org, ["ld_admin"])
    other_learner = make_user(db_session, other_org, ["learner"])
    other_course = make_course(db_session, other_org, other_owner, content_seconds=[])
    other_item = make_item(db_session, other_org, other_course, only_module(db_session, other_course))
    db_session.commit()

    a = await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="lesson_opened", course_id=course.id, content_id=item.id, idempotency_key="same")
    b = await record_in_new_session(factory, org_id=other_org.id, user_id=other_learner.id, event_type="lesson_opened",
                                    course_id=other_course.id, content_id=other_item.id, idempotency_key="same")
    assert a.created and b.created and a.event.id != b.event.id


async def test_simultaneous_starts_open_one_session(factory, scene, db_session):
    org, learner, _, course, _, _ = scene

    async def start():
        async with factory() as db:
            session, created = await sessions.start(db, org_id=org.id, user_id=learner.id, course_id=course.id)
            await db.commit()
            return session.id, created

    results = await asyncio.gather(*[start() for _ in range(6)])
    assert len({sid for sid, _ in results}) == 1
    assert sum(1 for _, created in results if created) == 1
    assert db_session.query(LearningSession).filter_by(user_id=learner.id, course_id=course.id, ended_at=None).count() == 1
    starts = db_session.query(LearningEvent).filter_by(user_id=learner.id, event_type="session_started").count()
    assert starts == 1


# ================================================================================== the store
async def test_course_events_get_a_session_and_the_session_records_it(factory, scene, db_session):
    org, learner, _, course, _, item = scene
    result = await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="lesson_opened", course_id=course.id, content_id=item.id)
    assert result.event.session_id is not None
    session = db_session.get(LearningSession, result.event.session_id)
    assert session.context == {"source": "implicit"} and session.ended_at is None
    types = [e.event_type for e in db_session.query(LearningEvent).filter_by(session_id=session.id).order_by(LearningEvent.timestamp)]
    assert types == ["session_started", "lesson_opened"]


async def test_events_outside_any_course_have_no_session(factory, scene):
    org, learner, *_ = scene
    result = await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="recommendation_generated", payload={"n": 1})
    assert result.event.session_id is None


async def test_the_store_refuses_what_the_vocabulary_refuses(factory, scene):
    from app.events.vocabulary import VocabularyError

    org, learner, _, course, _, item = scene
    with pytest.raises(VocabularyError):
        await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="made_up")
    with pytest.raises(VocabularyError):
        await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="lesson_opened", course_id=course.id)  # no content
    with pytest.raises(VocabularyError):
        await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="lesson_opened", course_id=course.id,
                                    content_id=item.id, payload={"source": "elsewhere"})


async def test_received_at_is_the_servers_clock_even_when_the_event_is_older(factory, scene):
    org, learner, _, course, _, item = scene
    earlier = datetime.utcnow() - timedelta(minutes=10)
    event = (await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="lesson_opened", course_id=course.id,
                                         content_id=item.id, timestamp=earlier)).event
    assert event.timestamp == earlier and event.received_at > earlier + timedelta(minutes=9)


# =================================================================================== outbox
class FakeStream:
    def __init__(self, fail=False):
        self.fail, self.messages = fail, []

    async def publish_event(self, data):
        if self.fail:
            raise ConnectionError("redis is down")
        self.messages.append(data)
        return f"{len(self.messages)}-0"


async def drain(factory):
    """The database is shared by every test, so earlier tests leave undelivered events behind: deliver them first."""
    while (await store.dispatch_pending(factory, FakeStream())).published:
        pass


async def outbox_for(db_session, event_id):
    db_session.expire_all()
    return db_session.get(EventOutbox, event_id)


async def test_streamed_events_get_an_outbox_row_and_held_back_ones_do_not(factory, scene, db_session):
    org, learner, _, course, module, item = scene
    quiz_item = make_item(db_session, org, course, module, content_type="QUIZ")
    quiz, built = make_quiz(db_session, org, course, module, quiz_item, questions=1)
    db_session.commit()
    streamed = await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="content_completed", course_id=course.id,
                                           content_id=item.id, payload={"content_type": "VIDEO"})
    held = await record_in_new_session(
        factory, org_id=org.id, user_id=learner.id, event_type="question_answered", course_id=course.id, assessment_id=quiz.id,
        question_id=built[0][0].id, payload={"attempt_id": str(uuid.uuid4()), "attempt_number": 1, "is_correct": True,
                                              "points_awarded": 10.0, "answered": True, "question_type": "multiple_choice"})
    assert await outbox_for(db_session, streamed.event.id) is not None
    assert await outbox_for(db_session, held.event.id) is None


async def test_dispatch_publishes_committed_events_once(factory, scene, db_session):
    await drain(factory)
    org, learner, _, course, _, item = scene
    recorded = await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="content_completed", course_id=course.id,
                                           content_id=item.id, payload={"content_type": "VIDEO"})
    stream = FakeStream()
    first = await store.dispatch_pending(factory, stream)
    second = await store.dispatch_pending(factory, stream)
    assert first.published >= 1 and second.published == 0
    mine = [m for m in stream.messages if m["event_id"] == str(recorded.event.id)]
    assert len(mine) == 1
    message = mine[0]
    assert message["org_id"] == str(org.id) and message["user_id"] == str(learner.id)
    assert message["session_id"] == str(recorded.event.session_id) and message["content_id"] == str(item.id)
    assert message["payload"]["content_type"] == "VIDEO"
    row = await outbox_for(db_session, recorded.event.id)
    assert row.published_at is not None and row.stream_message_id and row.last_error is None


async def test_a_stream_outage_delays_delivery_and_is_recorded_then_retried(factory, scene, db_session):
    await drain(factory)
    org, learner, _, course, _, item = scene
    recorded = await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="content_completed", course_id=course.id,
                                           content_id=item.id, payload={"content_type": "VIDEO"})
    down = FakeStream(fail=True)
    now = datetime.utcnow()
    result = await store.dispatch_pending(factory, down, now=now)
    assert result.failed >= 1 and not down.messages
    row = await outbox_for(db_session, recorded.event.id)
    assert row.published_at is None and row.attempts == 1 and "redis is down" in row.last_error and row.next_attempt_at > now

    # not due yet: nothing is attempted
    still_waiting = FakeStream()
    assert (await store.dispatch_pending(factory, still_waiting, now=now)).published == 0 and not still_waiting.messages

    # the stream is back and the retry is due: the event is delivered, not lost
    back = FakeStream()
    await store.dispatch_pending(factory, back, now=now + timedelta(minutes=10))
    assert any(m["event_id"] == str(recorded.event.id) for m in back.messages)
    assert (await outbox_for(db_session, recorded.event.id)).published_at is not None


async def test_retry_backoff_grows_and_is_capped(factory, scene, db_session):
    org, learner, _, course, _, item = scene
    recorded = await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="content_completed", course_id=course.id,
                                           content_id=item.id, payload={"content_type": "VIDEO"})
    now, gaps = datetime.utcnow(), []
    for _ in range(12):
        await store.dispatch_pending(factory, FakeStream(fail=True), now=now)
        row = await outbox_for(db_session, recorded.event.id)
        gaps.append((row.next_attempt_at - now).total_seconds())
        now = row.next_attempt_at
    assert gaps[:4] == sorted(gaps[:4]) and gaps[0] < gaps[3]
    assert max(gaps) <= store.RETRY_BACKOFF_CAP_SECONDS


async def test_a_batch_limit_is_respected(factory, scene, db_session):
    await drain(factory)
    org, learner, _, course, _, item = scene
    for _ in range(5):
        await record_in_new_session(factory, org_id=org.id, user_id=learner.id, event_type="content_completed", course_id=course.id,
                                    content_id=item.id, payload={"content_type": "VIDEO"})
    stream = FakeStream()
    assert (await store.dispatch_pending(factory, stream, batch=2)).published == 2
