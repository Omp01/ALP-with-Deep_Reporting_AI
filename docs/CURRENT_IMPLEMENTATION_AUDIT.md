# Comprehensive LMS Implementation Audit (Stage 2 Transition)

**Audit Date:** September 17, 2026  
**Auditor:** Lead Systems Architect & Senior Full-Stack AI Engineer  
**Document Purpose:** Baseline audit of existing frontend, backend services, data models, APIs, and AI integrations to guide the transformation into a dynamic, content-driven, event-driven Adaptive LMS with Deep Reporting AI.

---

## 1. Executive Summary & Audit Matrix

| Existing Feature | Current Implementation | Hardcoded? | Dynamic? | Keep/Modify/Replace | Notes & Migration Action |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Authentication & RBAC** | JWT Bearer tokens with 5 roles (`system_admin`, `org_admin`, `instructor`, `manager`, `learner`) | No | Yes | **Keep** | Fully dynamic, secure, and production-ready. |
| **Multi-Tenancy** | Organization-scoped middleware and foreign keys (`org_id` on all tables) | No | Yes | **Keep** | Robust tenant isolation pattern across all queries. |
| **Database Schema (Core)** | 25 SQLAlchemy models across Courses, Modules, Competencies, Events, Risks, Insights | Partially | Yes | **Modify** | Add `assignments`, `assignment_submissions`, content types (`VIDEO`, `ARTICLE`, `QUIZ`, `ASSIGNMENT`), error categories. |
| **Course Catalog Data** | Single seeded course (`PY-DIST-101`) in `scripts/seed.py` | Partially | Yes | **Modify** | Replace demo seed with 5 real courses with full curriculum: Python, SQL, Data Engineering, ML, GenAI. |
| **Frontend Content Rendering** | `frontend/app/learner/learning/page.tsx` contains 2 inline React question objects | **Yes** | No | **Replace** | Build generic `ContentRenderer`, `VideoPlayer`, `ArticleViewer`, `QuizRenderer`, `AssignmentRenderer`. |
| **Learning Event Ingestion** | `POST /api/v1/events` pushes to Redis Streams and persists to PostgreSQL | No | Yes | **Modify** | Expand supported event types (video, article, quiz, assignment, session), enforce idempotency with `event_id`. |
| **Learning Sessions** | `AdaptiveSession` model exists; dummy session UUID used in some frontend requests | Partially | Yes | **Modify** | Implement explicit `POST /api/v1/learning/sessions` and `POST /api/v1/learning/sessions/{id}/end` lifecycle. |
| **Adaptive Engine Service** | Microservice on port 8001 with Bayesian mastery updates & pedagogical sequencing rules | No | Yes | **Modify** | Extend item selection to query real content items/quizzes mapped to weak competencies; add error-type weighting. |
| **Risk Detection Engine** | 6-signal anomaly detection scanner and background worker in `alms-api` | No | Yes | **Keep** | Dynamic risk calculation based on real learner telemetry. |
| **Evidence Package Builder** | `EvidenceBuilder` extracts structured facts with citation keys (`[E-#]`) | No | Yes | **Modify** | Enrich facts with question difficulty, error classification, assignment rubric feedback, and cross-course trends. |
| **Citation & Grounding Validator** | Regex-based validator enforcing zero hallucinations and grounding scores | No | Yes | **Keep** | Production-ready deterministic verification. |
| **AI Provider Abstraction** | Generic LLM call wrapper with mock fallback in `services/reporting-engine` | Partially | Yes | **Replace** | Implement formal `AIProvider` factory (`GroqProvider`, `OpenAIProvider`, `SelfHostedProvider`), prompt versioning. |
| **Proactive Scheduled Reporting** | Digest background worker generating periodic reports for managers & admins | No | Yes | **Keep** | Persists audit records to `scheduled_reports` table. |
| **BI Data Streaming Export** | `GET /api/v1/export/*` streaming CSV & JSON with pagination and tenant isolation | No | Yes | **Keep** | Production-grade streaming export. |
| **Embeddable Reporting Widget** | `GET /api/v1/embed/report` iframe endpoint with postMessage event handling | No | Yes | **Keep** | Embeddable cross-origin widget. |
| **Automated Test Suite** | 80 tests passing in `services/api/tests/` covering API, auth, adaptive, and reporting | No | Yes | **Modify** | Add Stage 2 tests for dynamic content rendering, assignment grading, real-time WebSocket, and AI failure modes. |

---

## 2. Deep-Dive Inspection by Layer

### 2.1. Frontend Architecture
- **Framework:** Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Lucide Icons.
- **Routes Audited:**
  - `frontend/app/page.tsx` — Landing page with dynamic persona routing. *(Keep)*
  - `frontend/app/login/page.tsx` — Persona switcher with live JWT authentication. *(Keep)*
  - `frontend/app/learner/dashboard/page.tsx` — Dynamic KPI cards, live mastery curves, and active course banner. *(Keep)*
  - `frontend/app/learner/learning/page.tsx` — **GAPS IDENTIFIED:** Assessment questions (`q-1`, `q-2`) are hardcoded directly in React state. Needs replacement with dynamic `ContentRenderer` supporting Video, Article, Quiz, and Assignment.
  - `frontend/app/learner/insights/page.tsx` — Dynamic grounded AI insights with clickable citation badges and slide-over evidence drawer. *(Keep)*
  - `frontend/app/manager/dashboard/page.tsx` — Live cohort mastery matrix, systemic skill gaps, and at-risk learner alert cards. *(Keep)*
  - `frontend/app/manager/reports/page.tsx` — Team-level grounded AI reporting studio and proactive digest generator. *(Keep)*
  - `frontend/app/admin/dashboard/page.tsx` — Organization analytics, content ingestion studio, BI export center, and widget sandbox. *(Keep)*

### 2.2. Backend Services & Containers
- **`alms-api` (Port 8000):** FastAPI REST Gateway. Exposes 18 router modules.
- **`alms-adaptive-engine` (Port 8001):** FastAPI service for Bayesian knowledge tracing, IRT difficulty calculations, and sequencing decisions (`advance`, `remediate`, `skip`, `change_modality`, `revisit`).
- **`alms-reporting-engine` (Port 8002):** FastAPI service with deterministic SQL evidence extraction, prompt orchestration, and citation validation.
- **`alms-postgres` (Port 5432):** PostgreSQL 16 with pgvector extension enabled.
- **`alms-redis` (Port 6379):** Redis 7 for real-time telemetry streaming (`XADD`, `XREADGROUP`, `XACK`).
- **`alms-minio` (Port 9000/9001):** S3-compatible object storage for course media, transcripts, and document ingestion.

### 2.3. Database Schema Gaps
The existing schema is robust (25 tables) but requires targeted additions for Stage 2:
1. **Assignments & Submissions:**
   - Need `assignments` table: `id`, `tenant_id`, `course_id`, `module_id`, `title`, `instructions`, `competency_id`, `difficulty`, `due_date`, `rubric`, `max_score`.
   - Need `assignment_submissions` table: `id`, `tenant_id`, `assignment_id`, `learner_id`, `submission_text`, `submission_url`, `submitted_at`, `score`, `feedback`, `status` (`ASSIGNED`, `IN_PROGRESS`, `SUBMITTED`, `GRADED`), `is_ai_graded`.
2. **Error Taxonomy & Psychometrics:**
   - Enhance `assessment_items` and `learning_events` payload with explicit error category classification: `CONCEPTUAL`, `PROCEDURAL`, `APPLICATION`, `CALCULATION`, `CARELESS`, `UNKNOWN`.
3. **Content Item Extensions:**
   - Add explicit support for `content_type` values: `VIDEO`, `ARTICLE`, `QUIZ`, `ASSIGNMENT`.
   - Add fields: `order_index`, `duration_seconds`, `text_content`, `status`.

### 2.4. Real-Time Architecture Gaps
- Telemetry ingestion is currently REST-based (`POST /api/v1/events`) pushing to Redis Streams.
- Need a lightweight WebSocket / SSE route (`/ws/learning/{session_id}`) on `alms-api` to broadcast real-time competency updates, next item recommendations, and risk state changes to the learner UI without page reloads.

### 2.5. AI Provider Integration Status
- Currently, AI reporting uses a direct call wrapper with mock fallback when API keys are absent.
- Stage 2 requires:
  1. Clean `AIProvider` interface under `services/reporting-engine/app/ai/` supporting Groq, OpenAI, and local OpenAI-compatible endpoints.
  2. Strict configuration validation script (`scripts/check_ai_config.py`).
  3. Interactive API key explanation (Phase K requirement).
  4. Prompt versioning under `services/reporting-engine/app/prompts/`.

---

## 3. Migration Plan (Phases A through T Roadmap)

The transition will follow the strict 20-phase roadmap requested:

```
[Phase A] Audit & Baseline (Current)
    ↓
[Phase B] Dynamic Course & Content Schema (courses, modules, content_items, assignments)
    ↓
[Phase C] Real Multi-Modality Content (5 Real Courses with Video, Article, Quiz, Assignment)
    ↓
[Phase D] Learning Sessions & Granular Immutable Learning Events Pipeline
    ↓
[Phase E] Dynamic Content-Driven Competency Mapping
    ↓
[Phase F] Real Bayesian Competency Mastery Model
    ↓
[Phase G] Real-Time Adaptive Sequencing Policy & WebSocket Updates
    ↓
[Phase H] Multi-Signal Risk Engine
    ↓
[Phase I] Deterministic Reporting Analytics Engine
    ↓
[Phase J] Structured Evidence Package Builder
    ↓
[Phase K] AI Provider Configuration & Interactive Key Setup Guide
    ↓
[Phase L] Grounded Reporting AI & Zero-Hallucination Citation Verification
    ↓
[Phase M] Dynamic Learner Reporting & "Why?" Evidence Drawer
    ↓
[Phase N] Manager & Team Cohort Intelligence Hub
    ↓
[Phase O] Admin & Organization-Level Reporting & Content Effectiveness
    ↓
[Phase P] Scheduled Proactive Learning Intelligence Digests
    ↓
[Phase Q] Embeddable Reporting Widget Sandbox
    ↓
[Phase R] High-Throughput BI Export APIs (CSV / JSON)
    ↓
[Phase S] Comprehensive Test Suite & Failure / Resilience Scenarios
    ↓
[Phase T] Final Documentation, Architecture Diagrams & End-to-End Demo Script
```

---

## 4. Conclusion & Next Step
All existing working features (Authentication, Multi-Tenancy, Redis Streams, PostgreSQL pgvector, Docker Compose topology) are preserved. We are ready to begin execution starting from **Phase A** upon confirmation.
