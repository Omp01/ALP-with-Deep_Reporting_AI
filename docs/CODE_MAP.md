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
| **Events & Risks** | [events.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/events.py), [risk.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/risk.py) | `learning_events`, `learner_risks` | Telemetry stream persistence, early dropout risk |
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

## Phase 5: Content Ingestion Pipeline

| Component | Path | Endpoint / Symbol | Purpose |
| :--- | :--- | :--- | :--- |
| **Document Parsers** | [text_extractor.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/parsers/text_extractor.py) | `TextExtractor.extract_from_bytes` | Multi-format parser (PDF, DOCX, PPTX, media, text) |
| **Semantic Chunker** | [chunker.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/parsers/chunker.py) | `SemanticChunker.chunk_text` | Boundary-preserving chunking (350 tokens, 50 overlap) |
| **Storage Client** | [storage.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/core/storage.py) | `StorageClient.upload_file`, `download_file` | Async S3 storage interactions |
| **Ingestion Router** | [ingestion.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/ingestion.py) | `POST /upload`, `POST /jobs/{id}/process`, `GET /jobs` | Ingestion job lifecycle & automated ContentItem creation |
| **Ingestion Tests** | [test_ingestion.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/tests/test_ingestion.py) | 2 automated tests (17 total API tests) | File upload, S3 persistence, text extraction, chunking, RBAC |

---

## Phase 6: AI Competency Derivation & Assessment Generation

| Component | Path | Endpoint / Symbol | Purpose |
| :--- | :--- | :--- | :--- |
| **AI Generation Service** | [ai_service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/ai_service.py) | `AIGenerationService.derive_competencies_from_text`, `generate_assessment_items` | Bloom taxonomy extraction & IRT question synthesis |
| **AI Derivation Router** | [ai.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/ai.py) | `POST /api/v1/ai/derive-competencies`, `/generate-assessments` | Competency discovery & question bank generation |
| **Review Lifecycle** | [ai.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/ai.py) | `PUT /api/v1/ai/assessments/{id}/review`, `GET /assessments` | Human-in-the-loop review (approved/flagged/rejected) |
| **AI Generation Tests** | [test_ai_generation.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/tests/test_ai_generation.py) | 2 automated tests (19 total API tests) | Competency derivation, question synthesis, review lifecycle |
