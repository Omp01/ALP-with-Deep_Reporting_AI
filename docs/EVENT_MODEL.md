# Learning Event Model & Architecture

## Overview

The Adaptive Learning Platform utilizes an **immutable, append-only Learning Event Store**. Every action a learner takes—from starting a module to answering an assessment question—produces a strictly validated telemetry event. 

These events are decoupled from synchronous business logic:
1. **API Ingestion Service**: Receives events at `POST /api/v1/events` and `POST /api/v1/events/batch`.
2. **PostgreSQL Relational Store**: Persists events immutably to the `learning_events` table for permanent auditing and analytics.
3. **Redis Streams (`learning_events`)**: Dispatches events in real time using `XADD`.
4. **Event Worker (`workers/event-worker`)**: Consumes via Redis Consumer Group `event_workers` (`XREADGROUP`), filtering for `ADAPTIVE_TRIGGER_EVENTS` and updating learner competency models in the Adaptive Engine.
5. **Reporting Engine**: Queries the immutable event log directly to derive deterministic metrics, trends, and grounded AI citations.

---

## Canonical Event Types

Defined in `shared/events/types.py`:

| Category | Event Type | Description | Competency Driver? |
| :--- | :--- | :--- | :--- |
| **Session Lifecycle** | `session_started` | Learner initiates learning session | No |
| | `session_completed` | Learner terminates session | No |
| **Content Interaction**| `content_started` | Content resource opened | No |
| | `content_completed` | Content resource viewed/read/watched | Yes |
| | `content_skipped` | Content skipped | No |
| | `content_recommended` | System advised learner to review content | No |
| **Question & Assessment**| `question_viewed` | Assessment item rendered | No |
| | `question_answered` | Item submitted with accuracy & latency | **Yes (Primary)** |
| | `answer_retried` | Subsequent attempt on same item | **Yes** |
| | `hint_requested` | Scaffolded guidance revealed | Yes (Confidence factor) |
| | `assessment_started` | Diagnostic / module test initiated | No |
| | `assessment_completed` | Diagnostic / module test finalized | **Yes** |

---

## Event Schema

### Relational Schema (`learning_events`)
```sql
CREATE TABLE learning_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID,
    course_id UUID REFERENCES courses(id) ON DELETE SET NULL,
    module_id UUID REFERENCES modules(id) ON DELETE SET NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_learning_events_org_user_time ON learning_events(org_id, user_id, timestamp DESC);
CREATE INDEX ix_learning_events_course_type ON learning_events(org_id, course_id, event_type);
```

### Ingestion Payload Example (`POST /api/v1/events`)
```json
{
  "event_type": "question_answered",
  "course_id": "42253dfc-f370-4e31-ba04-daee2d4e7f34",
  "module_id": "7acfa957-69bb-4309-a78b-d72b21c4b182",
  "payload": {
    "question_id": "q-react-hooks-01",
    "competency_id": "c-react-state-management",
    "correct": true,
    "duration_ms": 4200,
    "attempt_number": 1,
    "difficulty": "intermediate"
  }
}
```

---

## Redis Streams Topology

```
+------------------+         XADD          +-------------------------------+
| alms-api         | --------------------> | Redis Stream: learning_events |
+------------------+                       +-------------------------------+
                                                           |
                                                      XREADGROUP
                                                   (event_workers)
                                                           v
                                            +-------------------------------+
                                            | alms-event-worker             |
                                            +-------------------------------+
                                                           |
                                               POST /api/v1/adaptive/events
                                                           v
                                            +-------------------------------+
                                            | alms-adaptive-engine          |
                                            | - Update Competency Mastery   |
                                            | - Log Mastery Delta           |
                                            +-------------------------------+
```
