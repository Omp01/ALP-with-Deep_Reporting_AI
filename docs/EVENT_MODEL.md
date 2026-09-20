# Learning events and sessions

Events are evidence. Every meaningful thing a learner does, and every decision the platform makes about them, is recorded as an event that is **added and never changed**. Sessions group a learner's events into a period of learning. Everything later in the pipeline (competency state, adaptation, reports) is derived from this store, so what it records, and what it refuses to record, decides how far the rest can be trusted.

Code: `services/api/app/events/` (vocabulary, store, sessions, queries, dispatcher, evidence), `services/api/app/api/v1/events.py` and `learning_sessions.py` (API), `frontend/lib/event-reporter.ts` and `frontend/hooks/use-learning-events.tsx` (browser). Migration `006_learning_events_sessions`.

---

## 1. Principles

1. **Append-only, enforced by the database.** A trigger rejects `UPDATE` and `DELETE` on `learning_events`. Foreign keys that could erase or rewrite evidence (`ON DELETE CASCADE`, `SET NULL`) were replaced by plain restrictions: a user, course, module or content item that events refer to cannot be deleted. (Content with recorded activity gets `409 has_learner_activity`: unpublish it instead.)
2. **The server decides what counts as a fact.** Two sources of events, and the difference is the point:
   - **Server events**: a graded answer, a completed lesson, an assessment result, a submission, a grade, a decision. Recorded by server code at the place the fact is established. The browser endpoint refuses them (`403 server_only_event`), so a learner cannot write evidence about themselves, and neither can an administrator through that door.
   - **Learner events**: interaction the server cannot observe (a lesson opened, a video paused, a question displayed). The browser reports them; the server checks every reference against the caller's tenant and derives course, module and competency from the referenced item, never from the request.
3. **Tenant and learner come from the token**, never the body. Another tenant's ids are `404`.
4. **Unknown stays unknown.** A question with no difficulty rating records `difficulty: null`, not "medium". A response time nobody measured is `null`. An error type that cannot be known is `"unknown"`, never a guess.
5. **Nothing is lost silently.** Delivery to the stream goes through an outbox with retry; the browser keeps unsent events and retries; rejected events are counted, not swallowed.

---

## 2. The vocabulary

Defined in `shared/events/types.py` (names) and `services/api/app/events/vocabulary.py` (who may create each, required references, payload schema).

| Group | Event | Source | Needs | Notes |
|---|---|---|---|---|
| Session | `session_started`, `session_completed` | server | | `session_completed` carries `reason` and `duration_seconds` |
| Content | `lesson_opened` | learner | `content_id` | payload `source`: outline, resume, next, recommendation, direct |
| | `content_started`, `content_completed` | server | `content_id` | The facts progress logic and (later) competency logic count. `content_completed` covers every kind of item |
| | `video_started`, `video_paused`, `video_resumed`, `video_progress` | learner | `content_id` | `position_seconds` (and `duration_seconds`); progress also has `percent`, sent after each 30 s of real playback |
| | `video_completed`, `article_completed` | server | `content_id` | The typed view of the same fact as `content_completed`; `derived_from` names that event. **Count `content_completed`, not both.** |
| | `article_opened` | learner | `content_id` | |
| | `content_skipped`, `content_recommended` | server | `content_id` | Reserved (Phase 6) |
| Assessment | `assessment_started` | server | `assessment_id` | Every attempt |
| | `retry_started` | server | `assessment_id` | Additionally, for attempt 2 and later; names `previous_attempt_id` |
| | `question_shown`, `hint_requested` | learner | `question_id` | Payload `attempt_id` must be the caller's open attempt |
| | `question_answered` | server | `assessment_id`, `question_id` | **The primary evidence event.** See section 4 |
| | `assessment_completed` | server | `assessment_id` | `score`, `passed`, points, `duration_seconds` |
| | `answer_submitted`, `answer_graded` | server | `question_id` | Written answers (Phase 5): `answer_submitted` when the answer is handed in, `answer_graded` when a grade is accepted (payload: `graded_by`, `signal`, `confidence`, `quote_verified`, `model`). Objective questions are graded on submission and are recorded as `question_answered` only. An answer waiting for a person has `answer_submitted` and no `answer_graded` yet |
| Assignment | `assignment_opened` | learner | (derived) | payload `assignment_id` |
| | `assignment_submitted`, `assignment_graded` | server | | The grade is evidence about the **learner** (`user_id` is theirs, `graded_by` is the grader) and belongs to no session |
| Decisions | `adaptive_decision_made`, `competency_updated`, `recommendation_generated` | server | | `competency_updated` is emitted by the competency engine for every mastery update (`update_id`, `evidence_id`, previous and new mastery, signal, weight, trend, method). `adaptive_decision_made` is emitted for every adaptive decision (Phase 6: `decision_id`, `action`, `rule`, `mastery`; it names the content and competency chosen). `checkin_completed` (server; course, correct, total, quiz percent; never the self-report) is emitted when a login check-in is scored (`docs/CHECKIN.md`). `recommendation_generated` is still reserved |

Legacy names still found in old rows (`question_viewed`, `answer_retried`, `video_played`, `article_read`) are accepted on ingest where they have a current equivalent (`question_shown`, `retry_started`, `video_resumed`) and stored under the current name; `article_read` is retired.

Payloads are validated per type. Learner payloads reject unknown fields; server payloads require what evidence needs and may carry more. Payloads are limited to 8 KB.

---

## 3. Schema

`learning_events` (see migration 006 and `app/models/events.py`):

| Column | Meaning |
|---|---|
| `id` | Server-generated primary key |
| `org_id`, `user_id` | Tenant and learner (restricted foreign keys) |
| `session_id` | The learning session; the composite key `(session_id, org_id, user_id)` guarantees it is **this learner's session in this tenant** |
| `course_id`, `module_id`, `content_id`, `assessment_id`, `question_id`, `competency_id` | References, derived server-side |
| `event_type`, `payload` (JSONB) | |
| `timestamp` | When it happened. For browser-reported events, the browser's clock **if plausible** (not more than 2 minutes ahead, not more than 24 h old), else the server's |
| `received_at` | When the server recorded it (always the server's clock) |
| `idempotency_key` | Unique per tenant among non-null; see section 5 |
| `processed` | Deprecated, never updated (the table is append-only). Delivery state is in `event_outbox` |

`learning_sessions`: `id`, `org_id`, `user_id`, `course_id`, `started_at`, `last_activity_at`, `ended_at`, `end_reason` (`explicit` / `idle` / `superseded`), `context` (JSON, for example `{"source": "player"}`). Constraints: `ended_at >= started_at`; `ended_at` and `end_reason` are set together; **one open session per learner per course** (a partial unique index, so concurrent starts cannot create two).

`event_outbox`: which events still have to be published to the stream, with attempts, the next attempt time and the last error.

Per-answer evidence also lives on the answer rows: `quiz_questions.difficulty` (0-1, nullable; copied from the reviewed candidate at publish) and `question_responses.response_time_ms`, `response_time_source`, `error_type`.

---

## 4. Per-answer evidence (`question_answered`)

Spec section 17 asks what is captured for every answer. Each field, and where it comes from:

| Field | Source |
|---|---|
| learner, session, assessment, question, competency | Token; the open session; the question's quiz; the question's competency (a column, not only payload) |
| `attempt_id`, `attempt_number` | The attempt row |
| `selected_option_id`, `answered` | The submission (`answered: false` for a blank) |
| `is_correct`, `points_awarded` | Deterministic grading by the server |
| `difficulty` | The question's rating, or `null` |
| `response_time_ms`, `response_time_source` | Measured by the player as time on that question; **held to the attempt's real elapsed time by the server** (`client`, or `client_clamped` when it was capped). `null` when not reported |
| `error_type` | `null` when correct; **`"unknown"` when wrong.** See below |
| `timestamp` | Server time of grading (microsecond offsets keep the order of the questions) |

**Error types.** The spec lists `conceptual_misunderstanding`, `procedural_error`, `calculation_error`, `misreading`, `careless_error`, `knowledge_gap`, `unknown`, and says not to assign them randomly. For a multiple-choice question the platform has no information about *why* an option was chosen: options carry no error tags. Inferring a cause from timing or from which distractor was picked would be a guess presented as evidence, so a wrong answer is `"unknown"`. A richer classification needs evidence the platform does not have yet: tagged distractors, or the grading agent's reading of a written answer (Phase 5: a written answer carries the error type the grader or reviewer assigned; a multiple-choice answer is still `unknown`). `app/events/evidence.py` is where that logic will grow, and it is unit-tested to *not* vary with speed or option position.

---

## 5. Idempotency and concurrency

A browser retry after a timeout must not double-count. Each browser event carries an `idempotency_key`; the server stores it as `"<user_id>:<key>"` and the database allows one row per `(org_id, idempotency_key)`. `INSERT ... ON CONFLICT DO NOTHING` makes this safe under concurrent retries (tested with eight simultaneous requests).

This replaced the old scheme in which the **client chose the event's primary key** and the server checked for a duplicate without filtering by tenant (audit R7): another tenant using the same id got its event silently dropped, and the check was a read-then-write race. Keys are now per learner and per tenant, and the legacy `event_id` field is accepted only as an alias for the key.

## 6. Sessions

- **Explicit start.** The player calls `POST /learning/sessions/start` for the course. If the learner already has an open session for it, that one is resumed (`status: "resumed"`).
- **Implicit start.** Any server event that belongs to a course and finds no open session starts one (`context.source: "implicit"`), so nothing a learner does in a course is outside a session. It begins one microsecond before its first event, so `session_started` always sorts first.
- **Idle.** A session with no activity for `SESSION_IDLE_MINUTES` (30) is closed **at its last activity**, not when someone notices, so a forgotten tab never counts as hours of learning. It is closed lazily, the next time it is looked at (start, active, heartbeat, an event naming it).
- **End.** The player ends the session when the page is closed (`pagehide`, with `keepalive`). Moving between lessons inside the app is client-side and stays in the same session; a full reload ends it and starts another.
- **Late events.** Browsers report in batches, and on close the last batch and the end request race. An event that *happened* before the session (or attempt) ended is still accepted; one that claims to be later is refused (`session_ended`, `attempt_finished`).
- `learning_sessions` replaced `adaptive_sessions` as the target of events. Existing adaptive sessions were copied with the same ids; `adaptive_sessions` remains as the adaptive engine's working state and is unified in Phase 6.

## 7. Delivery to the stream

The Redis stream (`learning_events`) still feeds the event worker and adaptive engine. Events are no longer published inside the request:

1. `store.record()` inserts the event and, for streamed types, an `event_outbox` row **in the same transaction**;
2. a background dispatcher (`app/events/dispatcher.py`, started with the API; `EVENT_DISPATCHER_ENABLED`, every `EVENT_DISPATCH_INTERVAL_SECONDS`) publishes due rows with `SKIP LOCKED` (several API processes are safe);
3. a failure records the error and schedules a retry with exponential backoff (2, 4, 8 ... capped at 5 minutes). A Redis outage delays delivery; it cannot fail a learner's request or lose an event (the old code swallowed the error and the mastery update was lost, audit A5).

`question_answered` and `assignment_submitted` are **stored but not streamed** to the legacy mastery handler. That handler reads a `correct` key these events do not carry (every answer counted as correct, audit C1) and files competency-less evidence under the organisation's first competency (C2). They stay in the store as evidence. Since Phase 5 the competency engine is called directly where the answer is graded (it does not consume the stream), and the legacy handler that read them is retired: `/adaptive/events` acknowledges and ignores. (`content_completed` and `assessment_completed`, which the old path already received, are unchanged.)

## 8. Queries

| Endpoint | Purpose |
|---|---|
| `GET /events` | Filters: `user_id`, `session_id`, `course_id`, `module_id`, `content_id`, `assessment_id`, `question_id`, `competency_id`, `event_type` (repeatable), `since`, `until`, `order`, `limit` (max 200). Keyset pagination on `(timestamp, id)` with `next_cursor`: a page never repeats or skips an event when new ones arrive |
| `GET /events/{id}` | One event |
| `GET /events/stats` | Counts by type and by day, learners and sessions (L&D, org admins, managers) |
| `GET /learning/sessions` | List; filters `user_id`, `course_id`, `active`; a quiet open session is shown as `idle` |
| `GET /learning/sessions/{id}` | Details and a summary counted from its events (by type, items touched, questions answered and correct) |
| `GET /learning/sessions/{id}/events` | The timeline, oldest first |

**Who sees what** (`app/events/queries.py`): a learner, their own events and sessions. A manager, their own plus those of members of the teams they manage (this is the team scoping of audit R4, applied to events; other manager endpoints still lack it). L&D and org admins, everyone in the tenant. A `user_id` outside what the viewer may see returns an empty list, indistinguishable from "no events". A foreign or invisible id is `404`.

## 9. What the browser does

`frontend/lib/event-reporter.ts` queues events, sends them in batches every two seconds, gives each an idempotency key, keeps them (with backoff) when the server is unreachable, flushes with `keepalive` when the page is hidden or closed, and re-joins a fresh session if the server says the old one ended. `frontend/hooks/use-learning-events.tsx` starts the session for the course player and keeps it alive with a heartbeat every minute. The player reports `lesson_opened`, `video_started/paused/resumed/progress` (from real player events), `article_opened`, `question_shown` (with per-question time), and `assignment_opened`. Authors previewing a course generate no events.

## 10. Limits and honest gaps

- **Video events were not exercised in a real browser.** The seeded videos are YouTube embeds and the build environment has no internet; the events are covered by the API tests and by the tracker code path shared with progress, not by a played video.
- **Response time is time on a question**, not "time to first answer": the quiz shows one question at a time and lets the learner change an answer, so it is measured from first display to submission, summed over visits.
- **`error_type` is `unknown` for every wrong objective answer** (section 4).
- **No `hint_requested` source yet**: the quiz has no hints, so the event is accepted but nothing sends it.
- **Manager scoping is applied to events and sessions only.** Other manager-facing endpoints (audit R4) are unchanged.
- **A browser event can precede its session's `session_started`.** An event carries the browser's time for when it happened; the session is created by a request that finishes later, so in a timeline `lesson_opened` for the first lesson can sort a few hundred milliseconds ahead of `session_started`. Both times are true; the session record is not backdated to hide it.
- **Retention.** Nothing archives or aggregates old events; the table grows with use. Partitioning by time is the obvious next step at scale.
- **`TRUNCATE` is still possible** for an administrator with database access (row triggers do not fire on it). The guarantee is against application and ordinary SQL writes, not against the database owner.
