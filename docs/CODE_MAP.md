# Code Map & System Inventory

> Detailed mapping: Assignment Requirement → Feature → Service → Folder → File → Class/Function → API Endpoint → Database Table → Test.

---

## Phase 1: Repository, Infrastructure & Shared Contracts

| Component | Path | Key Symbols / Exports | Purpose |
| :--- | :--- | :--- | :--- |
| **Docker Compose** | [docker-compose.yml](file:///d:/ALP-Deep_Report_AI/adaptive-lms/docker-compose.yml) | `postgres`, `redis`, `minio`, `api`, `adaptive-engine`, `reporting-engine`, `ingestion`, `workers`, `frontend` | Multi-container local production environment |
| **Shared Schemas** | [common.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/schemas/common.py) | `UserRole`, `CourseStatus`, `MasteryStatus`, `RiskLevel`, `TaxonomyLevel`, `PaginatedResponse` | Unified enum and contract definitions |
| **AI Abstraction** | [ai_provider.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/schemas/ai_provider.py) | `AIProvider`, `OpenAICompatibleProvider`, `get_ai_provider` | Vendor-agnostic LLM interface |
| **Event Schemas** | [schemas.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/events/schemas.py) | `BaseLearningEvent`, `AssessmentAttemptPayload`, `SkillGapDetectedPayload` | Event streaming payload contracts |
| **Event Types** | [types.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/events/types.py) | `EventType` (12 distinct events) | Canonical event registry |
| **Service Contracts** | [contracts.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/contracts/contracts.py) | `AdaptiveNextStepRequest`, `GenerateReportRequest`, `IngestionTaskRequest` | Inter-service HTTP/RPC contracts |

---

## Phase 2: Database Models, Migrations & Telemetry

| Domain Entity | Model File | Database Table | Associated Schema / Enums |
| :--- | :--- | :--- | :--- |
| **Organization & Audit** | [organization.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/organization.py) | `organizations`, `audit_logs` | Multi-tenancy root and compliance logs |
| **User & Teams** | [user.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/user.py) | `users`, `teams`, `user_teams` | `UserRole` (5 roles), team cohorts |
| **Curriculum** | [course.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/course.py) | `courses`, `modules`, `content_items`, `content_chunks` | Course hierarchy, multi-modal content, embeddings |
| **Competencies** | [competency.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/competency.py) | `competencies`, `course_competencies`, `module_competencies`, `learner_competencies`, `competency_history`, `skill_gaps` | Knowledge graph, mastery estimation, progression tracking |
| **Assessments** | [assessment.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/assessment.py) | `assessment_items` | IRT psychometric question bank, options, answers |
| **Enrollment & Adaptive** | [enrollment.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/enrollment.py) | `enrollments`, `adaptive_sessions`, `session_sequence_steps` | Dynamic sequencing, session states |
| **Events, sessions & risks** | [events.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/events.py), [risk.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/risk.py) | `learning_events`, `learning_sessions`, `event_outbox`, `learner_risks` | Append-only evidence, sessions, delivery outbox, early dropout risk |
| **Reporting & Ingestion** | [reporting.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/reporting.py), [ingestion.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/ingestion.py) | `ai_insights`, `scheduled_reports`, `report_digests`, `ingestion_jobs` | Grounded AI reports, scheduled digests, document jobs |
| **Migrations** | [alembic.ini](file:///d:/ALP-Deep_Report_AI/adaptive-lms/database/alembic.ini), [env.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/database/migrations/env.py) | `alembic_version` | Head: `001_initial_schema` |
| **Database Seed** | [seed.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/scripts/seed.py) | 25 tables | 2 Orgs, 13 Users, 3 Teams, Courses, Competencies |
| **Demo Telemetry** | [generate_demo_data.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/scripts/generate_demo_data.py) | Telemetry & History | 4 Archetypes: High mastery, Shallow completion, Declining, Disengaged |

---

## Phase 3: Authentication, RBAC & Multi-Tenancy

| Component | Path | Endpoint / Symbol | Purpose |
| :--- | :--- | :--- | :--- |
| **Security Core** | [security.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/core/security.py) | `hash_password`, `verify_password`, `create_access_token`, `decode_access_token` | Password hashing & JWT generation |
| **Auth Schemas** | [auth.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/schemas/auth.py) | `LoginRequest`, `TokenResponse`, `UserProfileResponse`, `TenantInfo` | Auth contracts & profiles |
| **Auth Dependencies** | [deps.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/deps.py) | `get_current_user`, `get_current_tenant`, `require_roles`, `log_audit_action` | JWT validation, tenant resolution, RBAC guards |
| **Auth Router** | [auth.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/auth.py) | `POST /api/v1/auth/login`, `/refresh`, `GET /me`, `POST /logout` | Authentication lifecycle & audit logging |
| **Organization Router** | [organizations.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/organizations.py) | `GET /api/v1/organizations/me`, `/audit-logs` | Tenant inspection & compliance audit log access |
| **User Directory Router** | [users.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/users.py) | `GET /api/v1/users`, `GET /users/{user_id}` | Scoped directory & cross-tenant barrier |
| **Regression Tests** | [test_auth_rbac.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/tests/test_auth_rbac.py) | 9 automated test cases | Verifies login, RBAC 403, cross-tenant isolation, audit |

---

## Phase 4: LMS Core (Courses, Modules, Content, Competencies, Enrollments)

| Component | Path | Endpoint / Symbol | Purpose |
| :--- | :--- | :--- | :--- |
| **Course Schemas** | [course.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/schemas/course.py) | `CourseCreate`, `CourseResponse`, `ModuleCreate`, `ContentItemCreate` | Curriculum serialization & input validation |
| **Competency Schemas** | [competency.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/schemas/competency.py) | `CompetencyCreate`, `CourseCompetencyMapRequest`, `ModuleCompetencyMapRequest` | Bloom taxonomy & curriculum mapping contracts |
| **Enrollment Schemas** | [enrollment.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/schemas/enrollment.py) | `EnrollmentCreate`, `EnrollmentProgressUpdate`, `EnrollmentResponse` | Enrollment contracts & completion tracking |
| **Courses Router** | [courses.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/courses.py) | `GET/POST /courses`, `POST /publish`, `GET/POST /modules`, `POST /content` | Curriculum hierarchy authoring & publishing |
| **Competencies Router** | [competencies.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/competencies.py) | `GET/POST /competencies`, `POST /courses/{id}/competencies`, `POST /modules/{id}/competencies` | Knowledge graph management & benchmark weighting |
| **Enrollments Router** | [enrollments.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/enrollments.py) | `GET/POST /enrollments`, `PUT /enrollments/{id}/progress` | Learner course registration & telemetry progress updates |
| **Core Regression Tests** | [test_lms_core.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/tests/test_lms_core.py) | 6 automated test cases (15 total API tests) | CRUD validation, course publishing, module sequencing, progress |

---

## Content ingestion (rebuilt in Phase 3)

| Component | Path | Endpoint / Symbol | Purpose |
| :--- | :--- | :--- | :--- |
| **Admin API** | [content_admin.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/content_admin.py) | `/api/v1/admin/content/*` | Ingest, library, review, publish |
| **Request / response models** | [content_admin.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/schemas/content_admin.py) | `CandidateCreate`, `AnalysisUpdate`, `ContentDetail`... | Validation of review edits (3-5 options, exactly one correct) |
| **Pipeline** | [pipeline.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/pipeline.py) | `run_job`, `submit`, `recover_stale_jobs` | Staged, resumable background processing |
| **Validation** | [validation.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/validation.py) | `validate_upload`, `sanitize_filename` | Extension, magic bytes, zip limits |
| **YouTube** | [youtube.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/youtube.py) | `validate_youtube_url`, `YouTubeClient` | URL validation, oEmbed, captions (SSRF-safe) |
| **Analysis** | [analysis.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/analysis.py) | `analyze_content`, `generate_questions`, `validate_questions` | Objectives, competency matching, grounded questions |
| **AI access** | [ai.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/ai.py) | `provider_for`, `complete_structured` | Provider selection, JSON validation, one repair retry |
| **Prompts** | [prompts.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/prompts.py) | `PROMPT_VERSION`, `fence` | Versioned prompts, injection fencing |
| **Publish** | [publish.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/publish.py) | `readiness`, `publish_content` | Competencies, mappings, quiz creation |
| **Transcription / embeddings** | [transcription.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/transcription.py), [embeddings.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/embeddings.py) | `Transcriber`, `get_embedder` | Optional; report "unavailable" instead of faking |
| **Document parsers** | [text_extractor.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/parsers/text_extractor.py) | `TextExtractor.extract_from_bytes`, `ExtractionError` | PDF, DOCX, PPTX, text; named errors, no fallbacks |
| **Semantic chunker** | [chunker.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/parsers/chunker.py) | `SemanticChunker.chunk_text` | Boundary-preserving chunking |
| **Storage client / service** | [storage.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/core/storage.py), [main.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/s3-storage/app/main.py) | `StorageClient`, token-authenticated S3-style API | Files under `{org_id}/{job_id}/` |
| **Models** | [ingestion.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/ingestion.py) | `IngestionJob`, `QuestionCandidate` | Job stages, reviewable questions |
| **Admin UI** | `frontend/app/admin/content/` | Library, Add Content wizard, review page | See [CONTENT_INGESTION.md](CONTENT_INGESTION.md) |
| **Tests** | `services/api/tests/foundation/` | `test_ingestion_*`, `test_text_extraction.py` | See [TESTING.md](TESTING.md) |


---

## AI competency derivation & assessment generation (superseded in Phase 3)

`ai_service.py`, `api/v1/ai.py` and `tests/test_ai_generation.py` were **deleted**: they fell back to hard-coded questions and a keyword heuristic when AI failed, and stamped fabricated questions "approved". The replacement is the ingestion pipeline above (grounded, reviewable candidates). The older `assessment_items` table remains in the schema; nothing writes to it any more.

---

## Learning events and sessions (Phase 4)

| Component | Path | Symbol | Purpose |
| :--- | :--- | :--- | :--- |
| **Vocabulary & policy** | [vocabulary.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/vocabulary.py) | `SPECS`, `validate_payload`, `HELD_FROM_LEGACY_ENGINE` | Who may create which event, required references, payload schemas |
| **Store** | [store.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/store.py) | `record`, `dispatch_pending` | The only place an event is validated and appended; idempotent insert; outbox delivery with retry |
| **Sessions** | [sessions.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/sessions.py) | `start`, `for_activity`, `end`, `close_if_idle`, `require_open` | Lifecycle, implicit sessions, idle closing at last activity |
| **Queries** | [queries.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/queries.py) | `visible_user_ids`, `list_events`, `stats`, `session_summary` | Scoped reads, keyset pagination |
| **Evidence rules** | [evidence.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/evidence.py) | `error_type_for`, `response_time` | Deterministic per-answer evidence |
| **Dispatcher** | [dispatcher.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/dispatcher.py) | `run_dispatcher` | Background delivery to the stream |
| **Events API** | [events.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/events.py) | `/api/v1/events*` | Browser ingestion with server-side reference checks; queries |
| **Sessions API** | [learning_sessions.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/learning_sessions.py) | `/api/v1/learning/sessions*` | Start, end, heartbeat, list, details, timeline |
| **Emitters** | [progress.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/progress.py), [quizzes.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/quizzes.py), [assignments.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/assignments.py) | `event_store.record(...)` | The facts the server records as a learner works |
| **Browser** | `frontend/lib/event-reporter.ts`, `frontend/hooks/use-learning-events.tsx`, `frontend/hooks/use-playback-tracker.ts` | `EventReporter`, `LearningEventsProvider` | Batching, retry, idempotency, session; video and quiz events |
| **Activity UI** | `frontend/app/admin/activity/page.tsx` | | Events, sessions and a session timeline for admins and managers |
| **Migration** | [006_learning_events_sessions.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/database/migrations/versions/006_learning_events_sessions.py) | | Sessions, columns, trigger, outbox, per-answer columns |

## Competency engine and grading (Phase 5)

| Component | File | Key symbols | Purpose |
| :--- | :--- | :--- | :--- |
| **The formula** | [bkt.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/bkt.py) | `update`, `fold`, `trend_of`, `confidence_of` | The only place mastery is calculated; pure, deterministic |
| **The writer** | [service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/service.py) | `apply`, `explain`, `verify`, `list_states` | Stores evidence and the update, refreshes the state, emits `competency_updated`; locks per learner and competency |
| **Skill gaps** | [gaps.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/gaps.py) | `assess`, `cohort_summary` | Rules and reasons; "not enough evidence" |
| **Risk** | [risk.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/risk.py), [risk_service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/risk_service.py) | `assess`, `evaluate_learner_risk` | Explained risk from evidence and activity |
| **Data for both** | [insight.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/insight.py) | `learner_gaps`, `cohort_gaps`, `risk_input` | Gathers stored data (evidence-based rows only) |
| **Grading agent** | [grader.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/grading/grader.py) | `grade_answer`, `interpret`, `GradeOut` | Prompt, fencing, output checks, `needs_review` |
| **Answers to evidence** | [assessment.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/assessment.py) | `submit`, `finalize_attempt`, `review` | Grades a submitted attempt, emits events, applies evidence, holds answers for review |
| **APIs** | [mastery.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/mastery.py), [grading.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/grading.py) | `/api/v1/mastery*`, `/api/v1/grading*` | Read models and the review queue |
| **Models** | [competency.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/competency.py), [grading.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/grading.py) | `LearnerCompetency`, `EvidenceRecord`, `CompetencyStateUpdate`, `GradingResult` | State and immutable audit tables |
| **Migration** | [007_competency_engine.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/database/migrations/versions/007_competency_engine.py) | | Idempotent; quarantines legacy numbers |
| **Frontend** | `frontend/app/learner/competencies`, `app/admin/grading`, `app/admin/skill-gaps`, `components/content/quiz-renderer.tsx`, `components/admin-content/questions-panel.tsx`, `services/mastery.ts` | | Competencies with "Why?", review queue, gaps and risk, written questions |
| **Demo data** | [generate_demo_data.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/scripts/generate_demo_data.py) | | Synthetic answers through the engine |

## Adaptive engine and reporting (Phases 6-8)

| Component | File | Key symbols | Purpose |
| :--- | :--- | :--- | :--- |
| **Decision function** | [engine.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/adaptive/engine.py) | `decide`, `explain` | Pure: one rule per situation, and the explanation from its facts |
| **Gathering and storing** | [service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/adaptive/service.py) | `next_step`, `history`, `situation_for` | Reads stored data, stores the decision and its event |
| **Evidence package** | [package.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/package.py) | `Package` | Records, metrics and findings with ids; hashing; the compact form for the model |
| **Builders** | [builders.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/builders.py) | `build_learner`, `build_team`, `build_ld`, `build_organization` | The four audiences' evidence and findings |
| **Reporting agent** | [agent.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/agent.py) | `run`, `SYSTEM` | Interpretation only; never raises for a model failure |
| **Citation validator** | [validator.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/validator.py) | `validate_claim`, `validate_all`, `validate_narrative` | Ids, tenant, scope, period, numbers, causation |
| **Orchestration** | [service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/service.py) | `generate`, `load`, `evidence_detail` | Authorise, build, interpret, validate, store, cache |
| **APIs** | [reports.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/reports.py), [embed.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/embed.py), [analytics.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/analytics.py), [adaptive.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/adaptive.py) | | Reports, widget, analytics, next step |
| **Frontend** | `components/reports/report-view.tsx`, `components/player/next-step-card.tsx`, `app/learner/insights`, `app/manager/insights`, `app/manager/reports`, `app/admin/intelligence`, `app/admin/capability` | | Report pages with the evidence drawer; "Why am I seeing this?" |

## Login check-in (Phase 11)

| Layer | File | Purpose |
|---|---|---|
| Model / migration | `app/models/checkin.py`, `database/migrations/versions/009_checkins.py` | `checkins` |
| Quiz | `app/checkin/quiz.py` | Passages from the course's published lessons, sampling that favours unused ones, model call, verification through `ingestion/analysis` |
| Self-report | `app/checkin/psychometric.py` | Constructs, model prompt, statement validation, scoring and bands |
| Report | `app/checkin/report.py` | Quiz scoring, observations, the checked coaching note |
| Service / API | `app/checkin/service.py`, `app/api/v1/checkins.py` | Start (background generation), read, submit, skip, history |
| Frontend | `frontend/app/learner/checkin/page.tsx`, `frontend/services/checkins.ts` | The check-in page; the login page opens it for learners |
