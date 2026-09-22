# Adaptive LMS — API Reference

All requests must include the JWT bearer token in the `Authorization` header:
```
Authorization: Bearer <access_token>
```
The API automatically scopes every query to the caller's verified `org_id` (multi-tenancy) and validates permissions against 5 supported roles: `learner`, `instructor`, `manager`, `org_admin`, and `super_admin`.

Interactive OpenAPI Swagger UI is available locally at: **[http://localhost:8000/docs](http://localhost:8000/docs)**.

---

## 1. Authentication & RBAC

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Public | Authenticates credentials, generates JWT access token, and logs audit record. |
| `GET` | `/api/v1/auth/me` | Any Authenticated | Returns profile, active tenant ID, and permissions for current caller. |
| `POST` | `/api/v1/auth/refresh` | Any Authenticated | Refreshes expired access tokens. |
| `POST` | `/api/v1/auth/logout` | Any Authenticated | Invalidate session tokens. |

---

## 2. LMS Core Curriculum & Enrollments

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/courses` | Any Authenticated | Lists published courses for caller's organization. |
| `POST` | `/api/v1/courses` | Instructor, Admin | Creates a new curriculum course. |
| `GET` | `/api/v1/courses/{id}` | Any Authenticated | Retrieves course details and sequenced modules. |
| `POST` | `/api/v1/courses/{id}/modules` | Instructor, Admin | Adds a sequenced module to a course. |
| `POST` | `/api/v1/courses/{id}/chat` | Any Authenticated | In-course AI Chatbot: course summarization, personalized learning paths, and interactive tutoring. |
| `POST` | `/api/v1/modules/{id}/content` | Instructor, Admin | Adds a content asset to a module (text, slide, video, quiz). |

| `GET` | `/api/v1/enrollments` | Any Authenticated | Lists learner course enrollments and milestone progress. |
| `POST` | `/api/v1/enrollments` | Any Authenticated | Enrolls a learner in a curriculum course. |

---

## 3. Content Ingestion Pipeline

Full reference: [CONTENT_INGESTION.md](CONTENT_INGESTION.md). All endpoints are under `/api/v1/admin/content`, need `ld_admin` (legacy `instructor`) or `org_admin`, and are tenant-scoped (a foreign id is `404`). The earlier `/api/v1/ingestion/*` and `/api/v1/ai/*` endpoints were removed in Phase 3.

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/capabilities` | File types, size limit, whether AI / transcription / embeddings are available |
| `POST` | `/ingest/file` | multipart `file`, `module_id`, `title?`, `allow_duplicate?`. Validates, stores, starts a background job. `202 {content_id, job_id}`; `409 duplicate_content`; `413/415/422` with `{code, message}` |
| `POST` | `/ingest/youtube` | `{url, module_id, title?, allow_duplicate?}`. Only YouTube links; `422 invalid_url` otherwise |
| `GET` | `/` | Library: `q`, `status`, `type`, `source`, `course_id`, `module_id`, `limit`, `offset` |
| `GET` | `/{id}` | Detail: analysis, job and stages, question candidates, readiness (blockers, warnings) |
| `GET` | `/jobs/{id}` | Job progress (status, stage list, error code and message) |
| `POST` | `/{id}/process` | Retry; `{"force": true}` re-analyses even if unchanged |
| `PUT` | `/{id}` | Title, description, module |
| `PUT` | `/{id}/transcript` | Manual transcript for video/audio; optionally re-analyses |
| `PUT` | `/{id}/analysis` | Edit summary, level, objectives, competency decisions (`link` / `create` / `skip`) |
| `POST` | `/{id}/candidates` | Write a question (starts `approved`) |
| `PUT` / `DELETE` | `/candidates/{cid}` | Edit / delete a candidate (`409` once published) |
| `POST` | `/candidates/{cid}/status` | `pending` / `approved` / `rejected` |
| `POST` | `/{id}/candidates/status` | The same for many candidates |
| `POST` | `/{id}/publish` | Apply competency decisions, create the quiz from approved questions, publish. `409 not_publishable` lists blockers |
| `POST` | `/{id}/unpublish` | Hide from learners (progress kept) |
| `DELETE` | `/{id}` | Delete unpublished content and its stored file |

---

## 4. Learning Events and Sessions

Full reference: [EVENT_MODEL.md](EVENT_MODEL.md).

| Method | Path | Role | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/learning/sessions/start` | Any authenticated | `{course_id, context?}`. Starts the learner's session for a course, or resumes the open one (`status: created \| resumed`) |
| `GET` | `/api/v1/learning/sessions/active` | Any authenticated | The caller's open session, optionally for `course_id`; a quiet one is closed at its last activity |
| `POST` | `/api/v1/learning/sessions/{id}/heartbeat` | Owner | Record activity; `409 session_ended` if it ended |
| `POST` | `/api/v1/learning/sessions/{id}/end` | Owner | End it (idempotent) |
| `GET` | `/api/v1/learning/sessions` | Any authenticated | List (`user_id`, `course_id`, `active`, `limit`, `offset`); own / team / organisation by role |
| `GET` | `/api/v1/learning/sessions/{id}` | Visible to caller | Details and a summary counted from its events |
| `GET` | `/api/v1/learning/sessions/{id}/events` | Visible to caller | The session timeline, oldest first |
| `POST` | `/api/v1/events` | Any authenticated | Report **one interaction event** (`lesson_opened`, `video_*`, `article_opened`, `question_shown`, `hint_requested`, `assignment_opened`). Server-only types are `403 server_only_event`. Body: `event_type`, `content_id` or `question_id`, `session_id?`, `idempotency_key?`, `payload`, `timestamp?` |
| `POST` | `/api/v1/events/batch` | Any authenticated | Up to 50, all or nothing; an error names the failing `index` |
| `GET` | `/api/v1/events` | Any authenticated | Query with filters (`user_id`, `session_id`, `course_id`, `module_id`, `content_id`, `assessment_id`, `question_id`, `competency_id`, repeatable `event_type`, `since`, `until`, `order`, `limit`, `cursor`) → `{items, next_cursor}`; learners see their own, managers their team's, admins the tenant's |
| `GET` | `/api/v1/events/{id}` | Visible to caller | One event |
| `GET` | `/api/v1/events/stats` | L&D, org admin, manager | Counts by type and day, learners, sessions, for what the caller may see |

---

## 4b. Interactive Video Learning & Anti-Skipping Checkpoints

| Method | Path | Role | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/learning/video/{content_item_id}/checkpoints` | Any authenticated | Retrieves video checkpoints with learner's completion status; generates on-demand from transcript if none exist. |
| `POST` | `/api/v1/learning/video/{content_item_id}/checkpoints/generate` | Any authenticated | Force AI regeneration of comprehension checkpoints from the video transcript. |
| `POST` | `/api/v1/learning/video/{content_item_id}/checkpoints/{checkpoint_id}/status` | Any authenticated | Updates checkpoint status (e.g. `displayed` when flash card pops up). |
| `POST` | `/api/v1/learning/video/{content_item_id}/checkpoints/{checkpoint_id}/answer` | Any authenticated | Submits learner's answer choice (`selected_option_id`); returns correctness, correct option, and transcript explanation. |
| `POST` | `/api/v1/learning/video/{content_item_id}/validate-seek` | Any authenticated | Audits and validates a proposed playback seek (`current_time` -> `target_time`); blocks forward skip if intermediate checkpoints are uncompleted. |

---

## 5. Real-Time Adaptive Sequencing Engine

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/adaptive/next` | Any Authenticated (for yourself) | `{course_id?, competency_id?, session_id?}`: the next step from stored evidence, with `why` (Phase 6; docs/ADAPTIVE_ENGINE.md). Actions: CONTINUE, REMEDIATE, EASIER, HARDER, CHANGE_MODALITY, REVISIT, SKIP, ASSESS. |
| `GET` | `/api/v1/adaptive/decisions/{learner_id}` | Self, manager (team), admin | Stored decisions with the facts and evidence ids each used. |
| `GET` | `/api/v1/adaptive/competencies/{learner_id}` | Self, manager (team), admin | Served by the competency engine since Phase 5 (same data as `/mastery`): mastery, confidence, trend from history, evidence counts. |
| `GET` | `/api/v1/adaptive/skill-gaps/{learner_id}` | Self, manager (team), admin | Served by the competency engine: gaps with reasons, and competencies without enough evidence. |
| `GET` | `/api/v1/adaptive/cohort-gaps/{team_id}` | Manager (team), L&D, admin | Served by the competency engine: per competency, how many assessed learners are below the target (counts, not an average). |

---

## 6. Risk Engine (Early Warning & Interventions)

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/risks` | Manager, Admin | Lists at-risk learners across the organization with risk scores ($0.0–1.0$) and anomaly triggers. |
| `GET` | `/api/v1/risks/{learner_id}` | Any Authenticated | Risk history and anomaly breakdown for a specific learner. |
| `POST` | `/api/v1/risks/scan` | Manager, Admin | On-demand organization-wide risk scanner trigger. |
| `PUT` | `/api/v1/risks/{risk_id}/resolve` | Manager, Admin | Marks an at-risk alert as resolved post-coaching intervention. |

---

## 7. Grounded AI Insights & Evidence Engine

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/insights/generate` | Any Authenticated | Synthesizes an evidence-grounded AI narrative report with explicit `[E-#]` citation keys. |
| `GET` | `/api/v1/insights/{id}` | Any Authenticated | Retrieves generated insight, claims list, and grounding confidence score. |
| `GET` | `/api/v1/insights/{id}/evidence` | Any Authenticated | Returns backing telemetry fact package for "Why?" evidence inspection. |

---

## 8. Deterministic Analytics Gateway

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/learner/{user_id}` | Any Authenticated | Progress, velocity, and mastery analytics for a learner. |
| `GET` | `/api/v1/analytics/team/{team_id}` | Manager, Admin | Cohort velocity, active rate, and average team mastery index. |
| `GET` | `/api/v1/analytics/organization` | Admin | Executive high-level KPIs across all courses and cohorts. |

---

## 9. Scheduled Digests & Proactive Reporting

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/reports/digest/generate` | Manager, Admin | Triggers on-demand execution of the proactive scheduled leadership digest. |
| `GET` | `/api/v1/reports/digest/latest` | Manager, Admin | Retrieves the latest scheduled leadership digest and dispatch metadata. |

---

## 10. BI Export & Data Warehouse Streaming

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/export/events` | Admin | Streams learning events in CSV or JSON format for data warehouses. |
| `GET` | `/api/v1/export/competencies` | Admin | Streams competency mastery ledger in CSV or JSON format. |
| `GET` | `/api/v1/export/risks` | Admin | Streams risk signals and resolution histories in CSV or JSON format. |

---

## 11. Embeddable Reporting Widget

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/embed/report` | Public / Token | Returns responsive HTML card widget or JSON summary for enterprise intranet embeds. |

## Competency engine and grading (Phase 5)

Reference: `docs/COMPETENCY_ENGINE.md`, `docs/GRADING_AGENT.md`.

| Method | Path | Role | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/mastery/parameters` | Any | Method and parameters of the deterministic update |
| `GET` | `/api/v1/mastery/me`, `/me/gaps` | Any | Own competency states (evidence-based only) and skill gaps (`?course_id=`) |
| `GET` | `/api/v1/mastery/learners/{id}`, `/learners/{id}/gaps` | Self, manager (team), admin | Another learner's; anyone outside the remit gets `404` |
| `GET` | `/api/v1/mastery/learners/{id}/competencies/{cid}/explain` | as above | The evidence chain behind the mastery, with previous and new values, sentences, quotes; `404` when there is no evidence |
| `GET` | `/api/v1/mastery/learners/{id}/competencies/{cid}/verify` | as above | Recompute the chain from stored evidence and compare |
| `GET` | `/api/v1/mastery/cohort-gaps` | Manager, L&D, org admin | Per competency: assessed learners, learners below target, declining, lowest, median (`?team_id=&course_id=`) |
| `GET` | `/api/v1/mastery/evidence/{id}` | Self, manager (team), admin | One piece of evidence and its source; what reports will cite |
| `GET` | `/api/v1/grading/queue` | L&D, org admin | Written answers waiting for a person (`?course_id=`) |
| `GET` | `/api/v1/grading/responses/{id}` | L&D, org admin | One answer with question, rubric, expected answer and the AI's suggestion |
| `POST` | `/api/v1/grading/responses/{id}/review` | L&D, org admin | `{signal 0..1, error_type?, feedback?}`. Finalises the attempt when it was the last waiting answer; `409` if not waiting |
| `POST` | `/api/v1/admin/content/{id}/candidates` | L&D, org admin | Now accepts `question_type` (`multiple_choice`, `short_answer`, `open_ended`), `expected_answer`, `rubric` |

Quiz submit (`POST /quizzes/{id}/attempts/{attempt}/submit`) accepts `text_response` for written questions and returns `grading_status` per answer and per attempt (`needs_review`: provisional score, not passed). Learners see the rubric of a written question, never its expected answer. `GET /risks` and the risk endpoints return `risk_details` and are scoped: managers see their team.

## Reporting (Phases 7-8)

Reference: `docs/REPORTING_AI.md`. The earlier `/insights/*` and `/reports/digest/*` proxies to a separate reporting service, and the unauthenticated `GET /embed/report`, are gone.

| Method | Path | Role | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/reports/generate` | per audience | `{audience: learner|team|ld|organization, scope_id?, days?, use_ai?, force?}`: evidence package, deterministic findings, optional AI interpretation, citation validation, stored report |
| `GET` | `/api/v1/reports`, `/reports/{id}` | requester or remit | Your reports; one report with accepted and refused claims |
| `GET` | `/api/v1/reports/{id}/evidence/{evidence_id}` | as above | The evidence drawer |
| `GET` | `/api/v1/reports/learner|team|ld|organization` | per audience | The evidence package as JSON (no model) |
| `GET` | `/api/v1/reports/skill-gaps`, `/risks`, `/evidence?ids=` | manager, L&D, admin (evidence: remit) | Structured JSON for BI |
| `GET` | `/api/v1/analytics/learner/{id}`, `/team/{id}`, `/organization`, `/events`, `/competencies` | scoped | Deterministic figures (null when there is nothing behind them) |
| `POST` `GET` | `/api/v1/reports/schedules`, `/schedules/{id}/run`, `/schedules/run-due`, `/digests`, `/digest/generate`, `/digest/latest` | owner; run-due: admins | Scheduled digests |
| `POST` `GET` | `/api/v1/embed/tokens`, `/embed/data?token=`, `/embed/adaptive-reporting.js` | manager or admin mints; the token reads one scope | Embeddable widget |

## Login check-in (Phase 11)

Reference: `docs/CHECKIN.md`. For the signed-in learner about themselves; nobody else, whatever their role, can read a check-in.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/checkins/start` | `{fresh?, course_id?}` -> `202`; a model writes an AI quiz from the learner's course material and a self-report in the background (`generating` -> `ready`, or `failed` with a reason) |
| `GET` | `/api/v1/checkins/{id}` | Status; the quiz and statements without answers while `ready`; the scored report when `completed` |
| `POST` | `/api/v1/checkins/{id}/submit` | `{quiz: {question_id: option_id}, self_report: {statement_id: 1-5}}`: scores both, returns the report with the review and source passages |
| `POST` | `/api/v1/checkins/{id}/skip` | |
| `GET` | `/api/v1/checkins` | Your check-ins with scores |
