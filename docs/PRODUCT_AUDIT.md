# Product Audit — Adaptive LMS with Deep Reporting AI

**Audit date:** 2026-09-19
**Scope:** Full inspection of `adaptive-lms/` against the *Professional Adaptive LMS + Live Competency Model + Deep Reporting AI* master specification.
**Status:** Phase 0 audit. Written before any changes; **Phase 1 has since been delivered** — see the "Phase 1 update" section at the end for which findings it closed.
**Supersedes:** `docs/CURRENT_IMPLEMENTATION_AUDIT.md` and `docs/PRODUCT_TRANSFORMATION_AUDIT.md` (both written against earlier prompts; several of their claims are now stale — see §17).

**Method.** Every finding below comes from reading the code in the working tree, plus three live checks: `tsc --noEmit` on the frontend (clean), the running Postgres container (schema and row counts), and `GET /health` on the running API. **I did not run the backend test suite** — it is live-HTTP against a seeded database and would write events into your demo data. Findings cite files so you can verify them.

---

## 0. Verdict in one paragraph

The project has a solid *shell* — multi-tenant JWT auth, a well-structured async API, a Redis-Streams event pipeline, a real BKT function, an evidence builder, digest/export/embed endpoints, and a new component library with Explore, Course Detail, My Learning and Assessments pages. But the **core loop the spec cares about is not actually closed**. Quiz answers reach the mastery model as *"always correct"* (key-name mismatch), the live mastery update is a fixed-alpha moving average rather than the BKT function that is written but bypassed, adaptive sequencing ignores competencies and difficulty when picking content, ingestion falls back to hardcoded fake questions and a fake transcript, there is no prerequisite graph, no YouTube path, no realtime, and the reporting AI's "claims" are just echoed evidence sentences with a validator that never checks tenant or scope. There is also one unauthenticated data endpoint and one RBAC hole in the reporting gateway. Most of the good code is reusable; most of the *intelligence* needs to be rebuilt on top of it.

---

## 1. Current architecture

```text
Next.js 16 (App Router, React 19)           :3000
      │  fetch → API  (32 hardcoded http://localhost:8000 URLs remain; api-client used by 7 files)
      ▼
FastAPI "api" gateway                        :8000   JWT + role checks + TenantContext; 82 endpoints
      │  httpx (no service-to-service auth; org_id passed as a query param)
      ├──► adaptive-engine   :8001   BKT/EMA mastery, policy, sequencing, skill gaps
      ├──► reporting-engine  :8002   evidence → LLM → citation check; analytics; digest
      ├──► ingestion         :8003   health endpoints only — no business routes (see §10)
      └──► s3-storage (MinIO wrapper)
Postgres 16 :5433→5432 · Redis 7 Streams :6379 · MinIO :9000
Workers: event-worker (stream → adaptive-engine), risk-worker, digest-worker
```

- **Style:** microservices-lite. Three Python services + 3 workers + gateway, all sharing one Postgres.
- **Spec §60 says "prefer a modular monolith."** The split is not paying for itself here — see §15, problem A1.
- **Nesting quirk:** `D:\ALP-Deep_Report_AI` is a git repo with no commits; `adaptive-lms/` is a *second*, nested repo with 13 commits. `git status` in the outer repo just shows `?? adaptive-lms/`.

## 2. Current technology stack

| Layer | Technology | Note |
|---|---|---|
| Frontend | Next.js 16.3.5, React 19.2.8, TS 5, Tailwind 4, lucide-react, CVA | `recharts`, `react-query`, `next-themes` installed, unused |
| API | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2 async | |
| DB | PostgreSQL 16 (pgvector extension enabled, **not used**), Alembic | |
| Queue | Redis 7 Streams | |
| Storage | MinIO (S3) | |
| AI | `shared/schemas/ai_provider.py` (Gemini/Groq/OpenAI-compatible) **and** a separate if-ladder in `reporting-engine/app/ai/llm_provider.py` | two unreconciled paths |
| Tests | pytest + httpx, live-HTTP | |

**Stack decision:** the spec's example paths use `.ts`/Prisma phrasing, but it also says *"use the existing database architecture if it is sound"* and *"do NOT blindly replace working functionality."* I will **keep Python/FastAPI/SQLAlchemy/Alembic** and translate file paths accordingly. A TypeScript rewrite would burn the schedule for zero assignment value.

## 3. Existing features (what is real)

Verified present and working in code: JWT login/refresh/me; org-scoped queries; 5-role RBAC via `require_roles`; course/module/content CRUD; competency CRUD and course/module mapping; enrollments; assignments with submit/grade; quizzes with attempts and auto-grading; content progress; learning sessions; event ingest with `event_id` idempotency; risk scan (6 signals); insights; digest; CSV/JSON export; iframe embed; audit log; a design system (`components/ui`, `components/shell`) with 20+ primitives and a role-aware shell.

Live DB right now (`alembic_version = 002_lms_entities`, 36 tables): **2 orgs, 13 users, 5 courses, 18 content items, 6 quizzes, 15 learning events, 7 learner-competency rows, 1 adaptive decision, 0 AI insights.** The data is thin: nothing has ever generated an insight, and 15 events cannot demonstrate adaptation.

## 4. Existing database schema

35 application tables, `org_id` + index on every tenant-owned row (this part is done well).

```text
organizations, audit_logs, users, teams, user_teams
courses, modules, content_items, content_chunks
competencies, course_competencies, module_competencies, content_competencies
learner_competencies, competency_history, skill_gaps
assessment_items, quizzes, quiz_questions, quiz_options, quiz_attempts, question_responses
assignments, assignment_submissions, content_progress
enrollments, adaptive_sessions, session_sequence_steps, adaptive_decisions
learning_events, ingestion_jobs
ai_insights, scheduled_reports, report_digests, learner_risks
```

**Schema gaps vs spec §40** (verified by reading `models/*.py`):

| Spec entity | State |
|---|---|
| `competency_prerequisites` | **Missing.** `competencies.parent_id` is a hierarchy, not a prerequisite DAG. `grep prerequisite` finds one string in `risk_service.py`. |
| `roles` / `user_roles` | **Missing.** Single `users.role` string column. |
| `learning_sessions` | **Conflated.** Events FK to `adaptive_sessions`; there is no `ended_at`/`context` session concept independent of adaptive state. An API `learning_sessions.py` exists but writes to `adaptive_sessions`. |
| `competency_state_updates` | **Missing.** `competency_history` stores only `mastery_score` + a non-FK `event_id`. No `previous_mastery`, no `signal`, no FK to evidence. §20 "why did mastery go 0.41→0.68" is **unanswerable today.** |
| `evidence_records` | **Missing.** Evidence is built in memory and stored as a JSON blob in `ai_insights.structured_data`. |
| `report_claims`, `report_citations` | **Missing.** Claims live in `ai_insights.citations` JSON. |
| `assessment_attempts/responses` | Present as `quiz_attempts`/`question_responses`, but `QuestionResponse` has no `response_time`, `difficulty`, `error_type`, `confidence`, `evidence_quote`, `session_id`, or `org_id`. |
| Event fields | `learning_events` lacks `competency_id`, `assessment_id`, `question_id` columns (they hide in JSONB). |
| Event immutability | FKs to `users`/`organizations` are `ON DELETE CASCADE`; course/module/session are `SET NULL`. Deleting a user deletes their evidence; deleting a course orphans it. Nothing enforces append-only (no trigger/revoked UPDATE). |
| Content model | `content_type` values disagree: seed uses `VIDEO/ARTICLE/QUIZ/ASSIGNMENT`; ingestion writes `document/audio/video/slide`. No `source_type` (youtube/upload) or `analysis` fields; `status` existed but with no lifecycle values or constraint. |
| Embeddings | `content_chunks.embedding` is a JSONB column. pgvector is enabled but unused; **no code computes an embedding.** |
| Course fields | `rating` defaults to a fixed **4.8** and `duration_minutes` to **120** via `server_default` (migration 002) — every course shows a fabricated rating. |

**Migration debt:** revision `001` is `Base.metadata.create_all()`, not DDL. Revision `002` is real. The chain works going forward but `001` can never be autogenerated against or downgraded meaningfully. Acceptable to leave; new revisions should be genuine DDL.

## 5. Existing authentication & authorization

**Good:** bcrypt + JWT, refresh, active-user and active-org checks, `TenantContext` derived from the token (not the client), `X-Tenant-ID` honored only for `system_admin`, `require_roles()`, audit log.

**Problems found:**

| # | Issue | Severity |
|---|---|---|
| R1 | **`GET /api/v1/embed/report` has no authentication.** It takes `learner_id` and `org_id` from the query string and returns that learner's name and mastery. Anyone who knows two UUIDs reads learner data. (`embed.py:20`) | **Critical** |
| R2 | **Learner can request org/team-level insights.** `insights.py` only blocks `scope_type == "learner"` on someone else's ID. A learner sending `scope_type: "organization"` or `"cohort"` is not stopped. Also `GET /insights/{id}` and `/evidence` have no ownership check — any user in the tenant can read any insight. | High |
| R3 | **Adaptive, reporting and ingestion services trust `org_id` from the query string with no auth**, and their ports (8001/8002/8003) are published to the host in `docker-compose.yml`. Anyone who can reach those ports can read any tenant. Spec §34: "never trust tenant_id sent arbitrarily." | High |
| R4 | **Managers are not scoped to their teams.** `teams.manager_id` exists but is never used in an authorization check; a manager can request analytics for any team in the org. Spec §36. | High |
| R5 | Role vocabulary differs from spec. Code has `learner / instructor / manager / org_admin / system_admin`; several guards list `"super_admin"`, which no user can hold. Spec wants `LEARNER / MANAGER / L&D_ADMIN / ORG_ADMIN / SUPER_ADMIN`. `instructor` ≈ L&D admin. | Medium |
| R6 | `GET /users/{id}` lets any authenticated user read any same-org profile (learner can read the CEO's record). | Medium |
| R7 | Event ingest checks duplicate `event_id` **without an org filter** — a cross-tenant ID probe, and a collision drops a legitimate event. Not race-safe (select-then-insert). `/events/batch` has no idempotency at all. | Medium |
| R8 | Upload has no size/type validation. `max_upload_size_mb` and `ALLOWED_FILE_TYPES` are defined in config/.env and **never referenced**. | Medium |
| R9 | No rate limiting anywhere; no prompt-injection handling for uploaded content. | Medium |

## 6. Existing LMS functionality

| Feature | State |
|---|---|
| Learner shell + navigation | Present (role-aware sidebar/topbar, `lib/navigation.ts`). The nav lists Learning Paths, Progress, Competencies and Profile as `planned` items, but **no route exists for any of them** (`app/` has only dashboard, insights, learning, my-learning, assessments, explore, courses/[id]). Learning History is not in the nav at all. |
| Explore | Present (`app/explore`, 415 lines). |
| Course detail | Present (`app/courses/[id]`). Modules/objectives depend on seed data quality. |
| My Learning / Assessments | Present, new, uncommitted. |
| Course player | Present (`learner/learning/page.tsx`, 459 lines — rewritten, uncommitted) with renderers in `components/content/`. **Video is an HTML player pointed at fake URLs** (`https://storage.adaptivelms.io/...mp4` — a domain that does not serve these files). No YouTube embed. No `video_progress/paused/resumed/completed` — enum only has `video_played`, `video_paused`. |
| Quizzes | MCQ only. Submitted as a whole quiz; grading happens once at the end, so **there is no per-question adaptive delivery**. `text_response` is stored but never graded; open-ended answers are recorded as incorrect. |
| Learner home | Dashboard exists; not the spec's Continue / Recommended / Competencies / Recent Activity / AI Insight layout. |
| Admin | **No content library, no ingestion UI, no course authoring UI, no review/publish flow.** `admin/dashboard` is analytics + a file uploader. |
| Learning paths | Missing entirely. |

## 7. Existing AI functionality

- **Provider abstraction (`shared/schemas/ai_provider.py`):** decent `AIProvider` ABC, OpenAI-compatible + Groq + Gemini classes, retryable error type. Used only by `ai_service.py`. No Ollama class, no `LocalAIProvider`; no Ollama service in `docker-compose.yml`.
- **Reporting AI does not use it.** `llm_provider.py` is a separate if-ladder (Gemini → Groq → OpenAI → Anthropic → Ollama → offline) with its own env vars and a module-level `SYSTEM_PROMPT`. No prompt versioning, no task→model routing, no caching.
- **Provenance is falsified:** `main.py` writes `model_used="gpt-4o-mini"` and `prompt_version="v1.0.0-grounded"` on *every* insight regardless of which provider (or the offline fallback) actually produced it.
- **Silent failure:** `ai_service.py` wraps calls in `except Exception: pass` and returns heuristics. The caller cannot tell the LLM failed. Spec §52: "Never silently fail."
- **No grading agent.** Nothing takes (question, rubric, learner answer) → structured signal. Spec §18 is unimplemented.
- **Local keys exist:** `.env` (gitignored, not tracked) contains populated Gemini and Groq keys. Fine as-is; just do not copy this folder into a shared repo without checking, and rotate if it ever leaves your machine.

## 8. Existing reporting

Six surfaces exist (learner insights page, manager dashboard/reports, admin dashboard, digest worker, embed, export) and all share the reporting-engine, which is the right shape. But against spec §25–§33:

- **One generic generator.** There are not four audience-specific agents; `scope_type` selects which evidence rows are fetched and the *same* prompt runs. Spec §30 wants distinct agents answering distinct questions.
- **Evidence package is thin** (`evidence/builder.py`): learner scope = competency rows + 10 most recent events + 1 risk row. Team scope = **a single average** ("cohort average mastery is 0.52 across N competencies"). Org scope = one sentence about average enrollment progress, and it multiplies a stored `progress_pct` by 100 (unit ambiguity). No question responses, no sessions, no mastery updates, no content effectiveness, no time range, no patterns.
- **Citation keys are positional** (`E-1`…`E-n`), reassigned per package. Same fact cites `E-3` today and `E-7` tomorrow. Spec §26 wants stable IDs such as `event_1842`, `response_291`.
- **No claim structure.** The LLM returns free-text markdown. "Claims" are then synthesized from matched `[E-#]` tokens by copying the *evidence sentence itself* into `claim` (`main.py:151`). That is not a claim; it is the evidence echoed back — the validator can never fail it.
- **Validator (`grounding/validator.py`) checks one thing:** that a cited `E-#` string exists in the package it was generated from. It does **not** check tenant, scope, cited numbers vs. stored values, unsupported uncited claims, or claim type. It also returns `is_valid=True, score=0.70` when the evidence package is empty, and invalid citations lower a score but **do not reject the report.** Magic constants `0.70/0.25/0.30/0.20`.
- **No causality guardrail.** No observation/correlation/causal typing anywhere.
- **No content-effectiveness analysis, no L&D report, no organization coverage analysis.**
- **Digest exists** but only as ad-hoc generation; no `scheduled_reports` audit of what was cited.
- **BI/API:** three export endpoints. Spec §33 wants `/reports/{learner,team,ld,organization,skill-gaps,risks,evidence}` and `/analytics/{events,competencies}`.
- **Embed** works but is unauthenticated (R1) and is a raw iframe, not the `<adaptive-report>` custom element in §32.
- **Realtime:** none. No WebSocket/SSE code exists in any service or page; every number updates on reload.

## 9. Existing multi-tenancy

`org_id` on all tables, gateway derives tenant from the token, most queries filter by it (checked in quizzes, events, adaptive, insights, users). There is one cross-tenant test (`test_cross_tenant_isolation`) that touches user listing only. Spec §35 requires isolation tests over **users, courses, events, competency states, reports, evidence, assessments** — six of seven are untested. Problems R1, R3, R6, R7 above are tenant-isolation gaps in practice. The internal services (R3) are the largest structural weakness.

## 10. Existing content ingestion

| Spec §10 stage | State |
|---|---|
| Upload / URL | Upload only. **No URL, no YouTube.** |
| Validation | **None** (R8). Legacy `.doc`/`.ppt` are accepted by name but python-docx/python-pptx cannot parse them. |
| Storage | MinIO — works. |
| Extraction | PDF (PyMuPDF), DOCX, PPTX, TXT — real. **Audio/video: returns a hardcoded transcript about "distributed architecture and message stream partitioning" for every file** (`shared/parsers/text_extractor.py:104`). The README calls this "stubbed"; in practice it is ingested as real content and then fed to competency/question generation. |
| Chunking | `SemanticChunker` exists and is wired. |
| Content analysis / objectives | **Missing.** |
| Competency mapping | `derive_competencies_from_text` → LLM, else a keyword heuristic that only knows "distributed systems" and "streams", else "Core Conceptual Foundations". Hardcoded to one domain. |
| Question generation | LLM, else **two hardcoded questions about "decoupled asynchronous message streams" regardless of the content or competency, stamped `quality_flag: "approved"`.** This directly violates "no fake intelligence" and "real content first" (§72, §74). |
| Embeddings | **None computed.** |
| Admin review/publish | **Missing.** Generated items are not held for review. |
| `services/ingestion` container | Only `/health`, `/ready` and a global exception handler. The parsing runs inside the API process; the container and its `sentence-transformers` dependency (large image) do nothing. |
| Processing runs inline in the HTTP request | No background job, no status polling, no realtime processing status. |

## 11. Existing competency logic

The most important section. There are **three** mastery computations in the repo and the live one is the weakest.

1. `competency/mastery.py::calculate_mastery` — multi-factor formula blended 60/40 with a real Corbett-Anderson BKT. Reasonable, but…
2. **…it is only called for a learner's *first* observation.** For every later event, `adaptive-engine/app/main.py:211-215` does `mastery = 0.75·old + 0.25·(1 if correct else 0)`. That is a fixed-alpha exponential moving average, not BKT. `calculate_mastery`, `determine_trend` and the BKT function are imported and effectively unused on the live path.
3. `competency/skill_gap.py` and the risk service compute their own thresholds.

Specific defects:

| # | Defect | Effect |
|---|---|---|
| C1 | `raw_payload.get("correct", True)` — **default is `True`**. `quizzes.py` emits `QUESTION_ANSWERED` with key `is_correct`, not `correct`. The worker forwards it, the engine finds no `correct`, and records **a correct answer for every quiz question**, right or wrong. | **Critical.** Mastery rises on wrong answers. |
| C2 | Same handler: if the event carries no `competency_id`, it **assigns the evidence to the org's first competency** (`select … limit(1)`). | Evidence attributed to the wrong skill. |
| C3 | `duration_ms` defaults to `3000`, `difficulty` to `"intermediate"`, `attempt_number` to `1` — fabricated inputs. | Silent fake evidence. |
| C4 | `trend="stable"` is hard-coded in `/adaptive/next`; `consecutive_correct = 3 if mastery > 0.85 else 1` is *invented from mastery*. | The policy's trend/streak rules can never fire honestly. |
| C5 | `GET /adaptive/competencies` derives `trend` from mastery **thresholds** (≥0.75 "improving", <0.45 "declining"), not from history. | UI shows a fake trend. |
| C6 | No prior state → mastery **defaults to 0.50** and confidence 0.20 in `/adaptive/next`. | Untested learners look average. |
| C7 | `CompetencyHistory` has no previous value, no signal, no FK to the evidence row (§20 audit trail absent). | Cannot explain a mastery change. |
| C8 | No LLM grading signal exists, so nothing feeds the "signal → deterministic update" contract in §18. | Core spec item absent. |
| C9 | `confidence` = `min(1, n / required_evidence_count)` — evidence *volume*, not uncertainty. | Acceptable as a first cut; document it. |
| C10 | `DIFFICULTY_WEIGHTS` and all thresholds are `settings` values that are undocumented. | Documentation debt. |

**The good news:** the BKT function itself is correct and the multi-factor formula is a fine starting point. The fix is to make *one* deterministic update function (BKT with per-question difficulty/guess/slip, taking a graded signal) the only writer, and to log every update.

## 12. Existing adaptive logic

- `sequencing/policy.py` — a clean, readable rule set: `change_modality`, `skip`, `remediate`, `advance`, `revisit`, `continue`. **Keep the shape**, but it lacks `EASIER`, `HARDER`, `ASSESS`, prerequisite handling, and error-type-specific rules, and its inputs are partly fabricated (C4).
- `sequencing/recommender.py` — **selects `content_items[0]` of a module.** It ignores `recommended_difficulty` (the parameter is accepted and never read), ignores `content_competencies`, ignores the learner's history, and cannot pick a remediation item at all. `remediate` and `revisit` return the same first item the learner is already on. This is the piece that makes "adaptive" true or false, and today it is false.
- `adaptive_decisions` table exists and is written (good), but stores only `mastery` and `confidence` in metadata. No previous/new mastery, no evidence IDs, no alternatives considered. `GET /decisions` reads `session_sequence_steps` instead of `adaptive_decisions`.
- **"Why this?"** — no evidence-backed explanation is assembled from stored records; `reason` is a formatted string from the rule that fired.
- README says *"in-memory adaptive decisions… restart resets in-flight session state."* That is **stale/incorrect** — sessions persist to Postgres.
- No prerequisite awareness (no graph). No quiz-level adaptation (a quiz is all-or-nothing). No realtime push of the decision to the UI.

## 13. Existing evidence / citation logic

See §8. Summary: evidence is ephemeral, positional, and unstructured; claims are not first-class; validation is existence-only; nothing persists `evidence_records`, `report_claims` or `report_citations`; there is no evidence drawer that can show previous→new mastery, session and attempt (the learner insights page has a citation drawer, but it renders the echoed evidence sentence).

## 14. Missing assignment requirements (checklist)

Legend: ✅ done · 🟡 partial · ❌ missing.

| Spec § | Requirement | State |
|---|---|---|
| 5–6 | Learner nav + home with real dynamic content | 🟡 |
| 7–8 | Explore, Course Detail from real data | 🟡 (fake default rating/duration) |
| 9 | Player: YouTube, video, PDF, docs, quizzes, short-answer, open-ended, coding | 🟡 (MCQ + article + video-tag only) |
| 10–12 | Ingestion pipeline + admin UI + YouTube + review/publish | ❌ (extraction only) |
| 13 | Skill graph with prerequisites | ❌ |
| 14 | Append-only event store, full event vocabulary | 🟡 (19 types; missing video_started/progress/resumed/completed, opened events, answer_graded, adaptive_decision_made, competency_updated, recommendation_generated…) |
| 15 | Learning sessions with `ended_at`/`context`, all events reference one | 🟡 (conflated with adaptive session; quiz events omit `session_id`) |
| 16–17 | MCQ / short / open-ended / coding; per-answer evidence incl. response time, difficulty, error type | ❌/🟡 |
| 18 | LLM grading agent returning structured signal | ❌ |
| 19–20 | Competency store + deterministic BKT update with audit | 🟡 (writes state; bypasses BKT; no audit) |
| 21–22 | Adaptive sequencing with 8 actions + "Why this?" | 🟡 |
| 23, 49 | Skill-gap + explainable risk engine | 🟡 (6-signal risk is real; no prerequisite/time-on-task signals; reasons not evidence-linked) |
| 24 | Learner AI insights | 🟡 |
| 25–29 | Evidence package, grounded claims, citation validator, causality guardrail | ❌/🟡 |
| 30, 47 | Four distinct reporting agents/experiences | ❌ |
| 31 | Scheduled digests (learner, manager, L&D, org) | 🟡 (one digest type) |
| 32 | `<adaptive-report>` embeddable widget | 🟡 (iframe, unauthenticated) |
| 33 | BI/API touchpoints | 🟡 |
| 34–36 | Multi-tenancy, isolation tests, RBAC w/ 5 roles | 🟡 |
| 37–38 | AIProvider abstraction; zero-cost local mode (Ollama) | 🟡 (abstraction exists but bypassed; no Ollama provider) |
| 39–40 | Normalized schema incl. state updates, evidence, claims | 🟡 |
| 42–44 | Demo data through real services; scripted SQL-JOIN scenario | ❌ (seed writes mastery values directly; different domain) |
| 45–46 | Claim data model + Evidence drawer | ❌ |
| 48 | Content-effectiveness report | ❌ |
| 50 | Realtime (SSE/WebSocket/polling) | ❌ |
| 52–55 | Errors, observability, cost control, security | 🟡 |
| 56 | Tests: competency, adaptive, grounding, isolation, ingestion | ❌ (0 unit tests on core math; 45 live-HTTP tests) |
| 57–59 | 22 docs, traceability matrix, `architecture.svg` | 🟡 (10 of the 22 named docs exist, `ARCHITECTURE.md` being a stub; diagrams are `.mmd`, not `.svg`) |

## 15. Architecture problems

- **A1. Three services, three copies of the schema.** `adaptive-engine/models/tables.py`, `reporting-engine/models/tables.py` and `api/models/*` each redefine the tables. Schema drift is one migration away, and they already differ. The services have no auth (R3), add three network hops per request, and force every write to be re-proxied. For a single-team assignment the operational cost exceeds the benefit.
- **A2. The core loop is broken in the middle** (C1, C2, C3): events → mastery is unreliable, so everything downstream (adaptation, risk, reports) reasons on corrupted state.
- **A3. LLM output is unconstrained text** rather than a validated structure, so grounding can only be checked by regex.
- **A4. Business logic lives in route handlers** (quiz grading, progress, event handling) while the project declares a service layer used by 2 of 19 routers. `quizzes.py` even guesses which content item a quiz belongs to by title substring or "first quiz in course."
- **A5. Fire-and-forget event publishing.** `except Exception: pass` around Redis publishes; if Redis is down, the DB row is written with `processed=False` and **nothing ever retries** — the mastery update is silently lost.
- **A6. No realtime channel** to carry competency/decision updates to the learner.
- **A7. Fake-intelligence fallbacks** (§10, §7): the system degrades to plausible-looking hardcoded output instead of failing visibly.

## 16. UI/UX problems

1. Product surface is improving (Explore, Course Detail exist) but the **admin side has no LMS feel at all** — no content library, no ingestion wizard, no review screen.
2. Learner home is a metrics dashboard, not the "Continue Learning / Recommended / Competencies / Recent / AI Insight" layout.
3. Course thumbnails are absent; a fixed 4.8★ rating is shown for every course (fabricated).
4. Video player points at non-existent files, so the headline modality cannot demonstrate anything.
5. No "Why this?" panel, no evidence drawer wired to real records, no live competency change toast in the player.
6. Manager/L&D/org surfaces are three variants of one dashboard.
7. 32 hardcoded `http://localhost:8000` URLs remain; the app cannot be deployed off localhost.
8. Page titles/nav describe architecture ("Adaptive Learning", "Grounded Digests") in the older pages; the newer pages are better — finish the migration for consistency.
9. Responsive behaviour of the player (collapsible curriculum) is unverified.

## 17. Technical debt & stale documentation

- **Uncommitted work:** `git status` shows 63 changed paths in `adaptive-lms` — migration `002`, quizzes/progress models and routers, Explore, Course Detail, Assessments, My Learning, content components, seed rewrite, and staged deletions of the recursive `adaptive-engine/app/app/` and `app/app/app/` duplicate trees. **Commit this baseline before Phase 1** so the transformation is diffable.
- Tracked/untracked build junk on disk: nested `venv/` in root and `services/api/`, `__pycache__/`, `.pytest_cache/`, `tsconfig.tsbuildinfo`. Currently ignored, not tracked — fine.
- **Stale claims in existing docs** (all verified against code):
  - README "80/80 tests passing" → **45 test functions** across 10 files; not run in this audit.
  - README "Next.js 14" → **16.3.5**.
  - README "12 canonical event types" → **19**.
  - README "Whisper transcription is stubbed" → it is a hardcoded fake transcript that flows into the pipeline.
  - README "in-memory adaptive decisions" → persisted.
  - README "pgvector / embeddings via sentence-transformers" → no embeddings are computed; column is JSONB.
  - README/ARCHITECTURE "BKT mastery model" → BKT is bypassed after the first observation (C-section).
  - `PRODUCT_TRANSFORMATION_AUDIT.md` says the app has "no component library / 37 hardcoded URLs / `tsc`-unverified" → a component library now exists; 32 URLs remain.
- `docs/ARCHITECTURE.md` is a 5-line stub pointing at the root file.
- Tests: no `conftest.py`, no fixtures, no CI-runnable path; the adaptive-engine, reporting-engine and ingestion test dirs contain only `__init__.py`; zero unit tests for `mastery.py`, `policy.py`, `validator.py`, `builder.py`. The one cross-tenant test (`test_auth_rbac.py:103`) only asserts that `GET /users` returns no other-tenant emails.
- `frontend/AGENTS.md` (written by `next dev`) warns that this Next.js version has breaking changes vs. training data — I will read `node_modules/next/dist/docs/` before writing frontend code in Phase 2.

## 18. What can be reused

Keep and build on — do not rewrite:

- `core/security.py`, `api/deps.py` (JWT, `TenantContext`, `require_roles`, audit log) — extend, don't replace.
- `org_id`-everywhere schema convention, async SQLAlchemy layer, Alembic (add real revisions from `003`).
- `competency/mastery.py::calculate_bkt_mastery` — the BKT core. Wrap it into the single audited update.
- `sequencing/policy.py` — rule structure, extended.
- Redis-Streams pipeline and `event_id` idempotency idea (fix R7, A5).
- Quiz/attempt/response tables and the quiz router (add fields, per-question flow).
- `shared/schemas/ai_provider.py` — becomes the one `AIProvider`; add `LocalAIProvider` (Ollama).
- `evidence/builder.py` SQL patterns and `analytics/calculator.py` deterministic metrics.
- Risk service six signals; digest worker; export streaming; embed HTML card (behind auth).
- `components/ui/*`, `components/shell/*`, `lib/api-client.ts`, `use-api`/`use-auth` hooks, the new Explore/Course/My-Learning/Assessments pages.
- Docker Compose topology and healthchecks.
- `SemanticChunker`, PDF/DOCX/PPTX extractors.

## 19. What must change

| Area | Change |
|---|---|
| Security | Authenticate/sign embed (R1); scope insight endpoints by role + ownership (R2); internal service auth or fold services in (R3); team-scope managers (R4); file/URL validation (R8). |
| Mastery | One deterministic BKT update; strict event schema (no silent defaults); audit table `competency_state_updates`. |
| Events | Add `competency_id`, `question_id`, `assessment_id`; real `learning_sessions`; full vocabulary; DB-level append-only; drop `CASCADE` on evidence; outbox-style retry instead of `except: pass`. |
| Skill graph | New `competency_prerequisites` (DAG, cycle check), used by adaptive engine and risk engine. |
| Adaptive | Content selection by competency + difficulty + modality + prerequisites; persist decision with previous/new mastery and evidence; per-question adaptive quiz; `/adaptive/next` reads real trend/streak. |
| Ingestion | YouTube; validation; real analysis → objectives → competencies → question candidates in **`review`** status; remove fake transcript and fake question fallbacks (fail visibly instead); optional local Whisper/Ollama; admin UI. |
| Grading | New grading service (LLM → structured JSON signal) for short/open-ended; deterministic grading for MCQ. |
| Reporting | Persisted `evidence_records`; stable IDs; four agents with different question sets; structured `{claim, claim_type, evidence_ids}` output; validator that checks existence, tenant, scope and numeric equality and **rejects**; causality typing; content-effectiveness; scheduled digests ×4. |
| AI | Consolidate to one provider layer; record true provider/model/prompt version; add Ollama; task→model routing; caching. |
| Frontend | Finish `api-client` migration; learner home; player with YouTube + live competency + Why-this; evidence drawer; admin content library/wizard; distinct report UIs; SSE hook. |
| Data | Re-seed **through the services**, using the SQL-JOIN scenario, instead of inserting mastery rows. Remove `server_default` rating `4.8`. |
| Tests/Docs | Unit tests for core math; conftest with real fixtures and a second tenant; tenant-isolation suite; the 22 docs + `architecture.svg` + traceability matrix. |

## 20. Recommended implementation order

The spec's order is right; one adjustment: fix the *broken middle* of the loop before building more UI on top of it.

- **Phase 0.5 (small, before Phase 1):** commit the current baseline; stop the bleeding on R1/R2 and C1 (three one-line-class fixes) so nothing downstream is built on corrupt state. *This touches code, so I will only do it if you say so.*
- **Phase 1** Foundation: `competency_prerequisites`, `roles/user_roles` (or a role enum extension to L&D_ADMIN), `learning_sessions` split, event column additions + append-only, `evidence_records`/`report_claims`/`report_citations`/`competency_state_updates` tables, real Alembic revisions, tenant-isolation test harness.
- **Phase 2** Professional LMS: finish learner home, nav, player, remove remaining hardcoded URLs.
- **Phase 3** Ingestion: YouTube first (highest demo value, no file plumbing), then PDF/DOCX/PPTX/TXT; review/publish UI.
- **Phase 4–5** Events + competency: strict schema, grading service, single BKT update with audit, skill-gap and risk on real signals, unit tests.
- **Phase 6** Adaptive: content selection, prerequisites, per-question adaptive quiz, Why-this, SSE, scripted in-session demo.
- **Phase 7–8** Reporting AI + touchpoints: evidence package → four agents → validator; digests; widget; BI API.
- **Phase 9–10** Hardening and end-to-end acceptance run.

## 21. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Rebuilding the mastery path changes numbers seen in current demo data | High | Low | Expected; demo data is re-seeded through services anyway |
| Folding adaptive/reporting into the API (if you approve) breaks running containers | Medium | Medium | Do it behind the same HTTP contracts first; delete services last |
| LLM quality with small local models (grading, claim generation) | High | High | Strict JSON schema + validator + deterministic fallbacks that **fail visibly**; never fake output |
| Structured-claim validator too strict → most reports rejected | Medium | High | Log rejection reasons; constrain prompt to cite ID + value; retry once |
| Citation-number matching (numeric equality) is brittle | Medium | Medium | Claims carry machine-readable `metric` fields; validate those, not prose |
| Next.js 16 API differences vs. my training data | Medium | Medium | Read bundled docs before frontend work (per `AGENTS.md`) |
| Local Ollama unavailable on your machine | Medium | Medium | Provider abstraction; Groq/Gemini keys already present as optional providers |
| YouTube transcript retrieval blocked/absent for some videos | Medium | Medium | Fall back to title/description + admin-pasted transcript; surface "no transcript" state explicitly |
| Schedule: this is a large scope | High | High | Phases 3–7 carry the value; Phase 10 acceptance run is the scope guard |

## 22. Estimated complexity by phase

Relative sizing (S ≈ hours, M ≈ a day, L ≈ 2–3 days, XL ≈ a week of focused work):

| Phase | Deliverable | Size | Main driver |
|---|---|---|---|
| 0.5 | Baseline commit + critical fixes | **S** | 3–4 small fixes |
| 1 | Foundation (schema, roles, graph, isolation harness) | **L** | Migrations + test harness |
| 2 | Professional LMS UI | **L** | Player + home; components exist |
| 3 | Content ingestion (YouTube + files + review UI) | **XL** | Analysis pipeline + admin UI |
| 4 | Learning events & sessions | **M** | Mostly wiring + new event types |
| 5 | Competency engine + grading + risk | **L** | Grading service; unit tests |
| 6 | Adaptive engine + Why-this + SSE | **L** | Selection logic; realtime |
| 7 | Deep reporting AI (evidence, agents, validator) | **XL** | Highest rubric weight; most new design |
| 8 | Reporting touchpoints | **M** | Reuse of Phase 7 backend |
| 9 | Hardening | **M** | Tests, RBAC, error states |
| 10 | Final polish + acceptance | **M** | End-to-end run and fixes |

---

## Decisions I need from you at "START PHASE 1"

These change what I build, so I would rather ask than guess:

1. **Modular monolith?** I recommend folding `adaptive-engine` and `reporting-engine` into the API as internal packages (keeping workers, Redis and MinIO), which also removes R3 and A1. Alternative: keep the services and add service-to-service auth plus a shared model package. *Recommendation: monolith.*
2. **Role model.** Extend the existing `role` column (`instructor` → `ld_admin`, `system_admin` → `super_admin`) or add real `roles`/`user_roles` tables? *Recommendation: tables, with a migration that maps existing roles.*
3. **Local AI.** Do you have Ollama installed and a model pulled (e.g. `llama3.1:8b` or `qwen2.5`)? If not, I'll default to your existing Groq/Gemini keys as "external" providers and still ship the `LocalAIProvider`.
4. **Phase 0.5 approval.** May I commit the current working tree as a baseline and apply the three critical fixes (embed auth, insight scoping, the `is_correct` mismatch) before Phase 1?

**Stopping here per your instruction. Waiting for `START PHASE 1`.**

---

## Phase 1 update (2026-09-19)

Findings closed or changed by Phase 1 (foundation). Everything not listed here is unchanged and still scheduled as described above.

| Finding | Result |
|---|---|
| Missing `competency_prerequisites` (skill graph) | **Done** — table, API, cycle protection, UI, tests. `docs/SKILL_GRAPH.md` |
| Missing `roles` / `user_roles`; role vocabulary mismatch (R5) | **Done** — five canonical roles, legacy spellings kept as aliases. `docs/RBAC.md` |
| R6: any user could read any same-org profile | **Fixed** — learners may read only their own profile and roles |
| Fabricated course rating 4.8 and duration 120 (schema, §16) | **Fixed** — both nullable; rating NULL until real data exists; duration computed from content; "popular" sort now uses real enrolment counts |
| Content model lacked source/analysis/lifecycle | **Done** — `source_type`, `source_url`, `analysis`, DB-checked `status`. `docs/CONTENT_MODEL.md` |
| Content creation dropped most fields and never set `course_id` | **Fixed** |
| Migration 002 could not run on a fresh database | **Fixed** — 002 and 003 detect objects `create_all()` already made |
| Tenant isolation tests covered `GET /users` only | **Extended** — 18 resource kinds plus listings, spoofed headers, forged claims, quizzes, events (mutation-checked) |
| No test harness usable without a live stack | **Done** — `tests/foundation` builds its own database from the real migrations |
| Demo seed wrote no roles, graph or domains | **Fixed** — seed assigns roles and inserts a skill graph through the normal tables |

**Not changed in Phase 1 (deliberately):** R1 (unauthenticated embed), R2 (insight scoping), R3 (unauthenticated internal services), R4 (manager team scoping), R7 (cross-tenant event id check — captured as a strict `xfail` test), C1–C10 (mastery/adaptive defects), and everything in §7–§13 (AI, reporting, ingestion). Those belong to Phases 3–9 or were not approved for early action.

---

## Phase 2 update (2026-09-20)

| Finding | Result |
|---|---|
| The "video player" was a timer simulating playback, generating fake watch progress | **Replaced** with a real YouTube IFrame player and an HTML5 player; progress advances only by time actually played |
| Seeded video URLs pointed at a domain that serves nothing | **Fixed**: six real YouTube videos, each verified via oEmbed |
| Progress was a stored float the client could set (`PUT /enrollments/{id}/progress`); completion was client-asserted for everything; time was invented (a default of 120 s, the quiz time limit) | **Fixed**: derived from lesson records; quizzes and assignments complete server-side; time clamped to real elapsed time; the endpoint no longer accepts a number |
| Quiz linked to its lesson by title guess ("first quiz wins") | **Fixed**: explicit unique `content_item_id` |
| Assignment "submit" was a `setTimeout`; assignments were not lesson items | **Fixed**: real submission form and API; assignments appear in the outline |
| No learner home matching the spec; no Course Detail from real data | **Built** (`/learner/dashboard`, `/courses/{id}`) |
| Learners could see draft courses and items | **Fixed**: published-only for learners, authored preview for L&D and org admins |
| Fabricated instructor names ("Adaptive LMS Faculty", "Staff Instructor", "Faculty Lead") | **Removed** |
| Ingestion attached content to a module without checking the tenant, and created items without `course_id` | **Fixed** |
| Stored enrollment "completed" values unsupported by lesson records | **Corrected** by migration 004 |
| Article "reading progress" started at a fake 25 %; raw Markdown shown as text | **Fixed**: scroll-depth tracking and a safe Markdown renderer |

**Still open after Phase 2** (deliberately): R1-R4, R7, the mastery/adaptive defects C1-C10 (so the mastery figures on Home and Course Detail come from the old update path), all ingestion work (section 10), the reporting and AI work (sections 7-8), learning paths, competencies / history / profile pages, and short-answer / open-ended / coding questions. YouTube playback itself was not verified end-to-end because the build environment had no outbound internet; see `docs/LEARNING_EXPERIENCE.md`.


## Phase 3 update (2026-09-20)

| Finding | Result |
|---|---|
| **R8**: upload had no size/type validation | **Fixed**: extension allow-list, magic-byte match, size cap, zip-bomb limits, sanitised names; legacy `.doc`/`.ppt` refused; `ALLOWED_FILE_TYPES` and `MAX_UPLOAD_SIZE_MB` are now honoured |
| **R9** (prompt-injection half): no handling of hostile content | **Addressed**: fenced prompts with per-call nonce, delimiter defanging, schema-validated output, every generated question checked against the source text, human approval before publish. Rate limiting is **still open** |
| **New finding, fixed**: the S3 storage service accepted unauthenticated requests and path traversal (`..` in an object key) | **Fixed**: bearer token required, strict bucket/key validation, resolved-path containment, size cap; 21 tests. **A container built before this still has the hole: rebuild it.** Compose now binds its ports to `127.0.0.1` |
| Audio/video ingestion returned a hardcoded transcript about "distributed architecture" for every file, which then drove competency and question generation | **Removed**: real transcription only when `faster-whisper` is installed; otherwise the job says "transcription unavailable" and the admin can paste a transcript |
| Question generation fell back to two hardcoded questions "stamped approved" when AI failed; competency derivation fell back to a keyword heuristic for one domain | **Removed**: an AI failure is recorded on the job with its reason and can be retried; nothing is invented. Generated questions start `pending`, are verified against the source, and need approval |
| Text extraction fell back to decoding raw bytes as latin-1 | **Removed**: named `ExtractionError`s (`corrupt_file`, `encrypted`, `invalid_encoding`, `missing_dependency`); scanned PDFs are reported, not turned into garbage |
| No URL/YouTube ingestion | **Built** (YouTube only, SSRF-safe): metadata, captions, manual transcript fallback |
| No content analysis / objectives; no competency mapping to the tenant's own skills | **Built**: objectives, concepts, competency decisions matched against existing competencies, editable |
| No admin review or publish step; generated items were live immediately | **Built**: candidates, approve/reject/edit/write, publish creates competencies/mappings and a real quiz; unpublish; audit entries |
| Processing ran inline in the HTTP request; no status; failures left jobs stuck | **Replaced**: background jobs with per-stage status, polling, retry, restart recovery |
| Embeddings never computed | **Optional stage** (stored with model name); nothing consumes them yet |
| Admin dashboard "Ingestion Studio" called removed endpoints on a hardcoded `localhost:8000`, and the KPI cards showed invented fallbacks (13, 68 %, 76 %, 1) when the API returned nothing | **Replaced** by the Content Library (`/admin/content`); KPI cards now show "—" without data; URLs use `NEXT_PUBLIC_API_URL` |
| The old `/ingestion/*` and `/ai/*` endpoints, `ai_service.py` and their tests | **Deleted** (they contained the fake fallbacks) |

**Still open after Phase 3** (deliberately): R1-R4, R7, rate limiting, the mastery/adaptive defects C1-C10, event/session capture (Phase 4), the competency engine and grading agent (Phase 5), adaptive sequencing (Phase 6), the reporting AI and its citations (Phase 7), and the rest of the admin surface (course/assessment/competency/user management). The internal `services/ingestion` container is an unused stub (parsing runs in the API process) and can be removed from compose. **Not verified live:** a real LLM, real YouTube, real transcription and real embeddings (no outbound internet or local model in the build environment), and PPTX extraction (`python-pptx` not installed there). See `docs/CONTENT_INGESTION.md` and `docs/TESTING.md`.


## Phase 4 update (2026-09-21)

| Finding | Result |
|---|---|
| **R7**: event ingest checked for a duplicate `event_id` without an org filter (cross-tenant id probe; a collision dropped a legitimate event), was not race-safe, and `/events/batch` had no idempotency at all | **Fixed**: the client no longer chooses the primary key; per-tenant idempotency keys (prefixed per learner) with `ON CONFLICT DO NOTHING`; batches are idempotent; the strict `xfail` test now passes and was rewritten |
| **A5**: event publishing to Redis was fire-and-forget (`except: pass`); a Redis outage silently lost the mastery update | **Fixed**: outbox written in the event's transaction, background dispatcher with retry and backoff, failures recorded. Verified against a real Redis (54 of 54 delivered) |
| Events were not append-only (nothing enforced it); `ON DELETE CASCADE` on users and organisations erased evidence, `SET NULL` on course/module/content rewrote it | **Fixed**: database trigger rejects UPDATE/DELETE; foreign keys now restrict; content with activity cannot be deleted (`409`) |
| Events lacked `competency_id`, `assessment_id`, `question_id`; quiz question events omitted the session | **Fixed**: real columns (existing rows filled from payloads where the row exists in the same tenant); every course event carries a session |
| "Learning sessions" were the adaptive engine's state; events pointed at `adaptive_sessions` and it had no `context` | **Fixed**: `learning_sessions` (started, last activity, ended, reason, context), idle closing at last activity, one open per learner per course; adaptive sessions copied across with their ids |
| Any client could post any event type, including `question_answered` with `correct: true` | **Fixed**: browsers may report only interaction; evidence is recorded by the server and refused from the browser (also from admins) |
| Vocabulary missing video/article/lesson/assignment/answer events; three names differed from the spec | **Fixed**: 20 spec events present; legacy names accepted as aliases |
| The course player produced almost no events (only progress start/complete and quiz start/finish) | **Fixed**: lesson opened, video started/paused/resumed/progress (from real playback), article opened, question shown with time on each question, assignment opened; server-side answers, completions, submissions and grades |
| Event listing returned a bare list with offset paging, learners filtered by legacy role string, managers saw the whole organisation | **Fixed** for events and sessions: filters on every reference, keyset pagination, stats by day, visibility by role (managers: their team, the team scoping of **R4** for this data only) |
| Question difficulty was not recorded; response time and error type did not exist | **Added** (`quiz_questions.difficulty` from the reviewed candidate, response time held to real elapsed time, `error_type` deterministic: `unknown` for a wrong answer, never guessed) |

**Deliberately not done**: `question_answered` is stored but not streamed to the legacy mastery handler, because that handler reads a `correct` key these events do not carry (audit **C1**: every answer counted as correct) and files competency-less evidence under the first competency (**C2**). The Phase 5 competency engine reads from the store. **Still open after Phase 4**: R1-R4 (R4 partly), C1-C10 and the mastery numbers they produce, rate limiting, the adaptive engine still using `adaptive_sessions`, short-answer and open-ended questions with the grading agent (Phase 5), adaptation inside a session (Phase 6), reporting on events (Phase 7). **Not verified**: video playback events in a real browser (no internet in the build environment: the seeded videos are YouTube embeds). See [EVENT_MODEL.md](EVENT_MODEL.md).


## Phase 5 update (2026-09-22)

| Finding | Result |
|---|---|
| **C1**: every quiz answer counted as correct (`raw_payload.get("correct", True)`, key `is_correct` was never read) | **Fixed**: the legacy mastery handler is retired (`/adaptive/events` acknowledges and ignores). Mastery is written only by the competency engine from graded answers; a wrong answer lowers it |
| **C2**: evidence with no competency was filed under the organisation's first competency | **Fixed**: evidence always names its competency (from the question); an answer to a question with no competency is graded but is not evidence. The engine rejects a competency from another tenant |
| **C3**: `duration_ms=3000`, `difficulty="intermediate"`, `attempt_number=1` invented when absent | **Fixed**: unknown stays unknown (`difficulty: null` is treated as 0.5 with no adjustment and says so in the stored parameters; response time is measured or null) |
| **C5**: `trend` derived from mastery thresholds | **Fixed**: trend is computed from the stored update history; fewer than three updates gives `insufficient_data` |
| **C7**: history had no previous value, signal or evidence link | **Fixed**: `competency_state_updates` (previous, new, signal, weight, parameters, evidence id) and `evidence_records`, both append-only; `explain` and `verify` endpoints |
| **C8**: no grading signal existed | **Built**: the grading agent (`docs/GRADING_AGENT.md`): rubric-based signal with confidence, quote and error type, checked before use, with a human review queue; written questions can be authored and published |
| **C9**: "confidence" was evidence volume presented as certainty | **Defined and documented**: `n_eff / (n_eff + K)`, how much evidence stands behind the estimate, not how high it is |
| **C10**: undocumented thresholds | **Documented and configurable** (`docs/COMPETENCY_ENGINE.md`, `.env.example`), stored with every update. They are standard starting values, not fitted to this platform's data |
| Three competing mastery computations (BKT, an EMA, a multi-factor formula) | **One**: `app/competency/bkt.py` (soft-evidence BKT). The others are no longer called |
| Skill gaps were "100 minus completion" style scores; the risk service read event keys that did not exist and wrote "nominal engagement" | **Rebuilt** as documented rules over stored evidence, each reason carrying the real figures, with a refusal to call a gap on fewer than two answers; cohort gaps report counts ("3 of 12 below 70%"), not averages |
| Managers saw every learner's risk in the organisation | **Fixed** for risk (list, history, resolve), cohort gaps and mastery: managers see their team. This is the team scoping of **R4** for events, sessions, risk and mastery |
| Demo data wrote mastery, risk scores and skill gaps straight into tables | **Replaced**: `scripts/generate_demo_data.py` writes synthetic answers (`source_type = seed_history`) and the engine derives the rest; risk comes from the production rules |
| Numbers written by the old engine on the user's data | **Quarantined** by migration 007: kept, marked `legacy_unverified`, never shown, replaced by the first real evidence |

**Still open after Phase 5**: **C4** (the adaptive engine's `/next` still hard-codes `trend="stable"`, invents a streak from mastery and defaults an untested learner to 0.50) and **C6** are Phase 6, together with the recommender that returns the first content item of a module and the adaptation policy; R1-R3 and rate limiting; the reporting AI and its citations (Phase 7); retention and deletion of learner data. **Limits stated in `docs/COMPETENCY_ENGINE.md` and `docs/GRADING_AGENT.md`**: model parameters are not fitted; grading quality on a real model is unmeasured here; accepted grades are not regraded; objective wrong answers have error type `unknown`. **Not verified live**: a real LLM grading real answers, and video events (no outbound internet in the build environment).

## Phase 6-10 update (2026-09-23)

| Finding | Result |
|---|---|
| **C4**: `/adaptive/next` hard-coded `trend="stable"` and invented a streak from mastery; **C6**: an untested learner defaulted to mastery 0.50 | **Fixed**: the adaptive engine is rebuilt in the API (`app/adaptive`) and reads only stored evidence; an untested learner has no mastery and is sent to material or an assessment |
| The recommender returned the first content item of a module and ignored difficulty, competency mapping and history; `remediate` and `revisit` returned the item the learner was already on | **Replaced**: content is chosen by competency mapping, completion, modality, difficulty (where known) and the prerequisite graph; eight actions with stored rules |
| No "Why this?" | **Built** from the stored facts of each decision; shown in the player |
| Reporting was a separate service whose narratives and citations were not tied to stored evidence; insight endpoints proxied to it | **Rebuilt in the API**: evidence packages with ids, deterministic findings, an optional model for interpretation, citation validation (ids, tenant, scope, period, numbers, causation), a stored report with its package, four distinct audiences |
| **Security**: `GET /embed/report` returned any learner's competencies to an unauthenticated caller who supplied a learner id and an organization id | **Removed**; the widget uses scoped, expiring embed tokens that are refused as logins and refresh tokens |
| Analytics endpoints proxied to the separate service and invented figures when data was absent | **Replaced** by deterministic local figures, null when nothing stands behind them |
| A run of wrong retried answers raised mastery (the learning step ignored the evidence weight) | **Fixed** in the formula (found by the reporting tests) |

### Phase 10 review: the questions

| Question | Answer |
|---|---|
| Does it feel like an LMS? Professional? | Yes: role-aware shell, real course player, outline, progress, quizzes with written answers, admin content library and review; consistent design system and states (loading, empty, error) on every new page. Not everything in the target IA exists (courses, users and settings administration, learner paths and profile are still `planned` and hidden from navigation) |
| Can an admin ingest real content? | Yes (documents, YouTube captions), reviewed and published by a person. Real transcription and embeddings need optional components |
| Can a learner learn from it? | Yes for the content that exists; video playback needs internet |
| Does behavior generate real events? | Yes, append-only, server-established facts and browser-reported interaction |
| Does competency change from evidence? | Yes: one deterministic function of graded evidence, with a recomputable chain |
| Does the next activity adapt, and can the learner see why? | Yes, inside one session, with the reason built from the stored facts |
| Can reporting explain what happened, and can every claim be traced? | Yes: every claim cites records that open in a drawer; unsupported statements are refused and listed |
| Are the four reports genuinely different? | Yes: different questions, evidence and findings; managers get no raw activity |
| Does tenant isolation work? | Tested for every new endpoint: reports, evidence, decisions, embed, schedules, grading, mastery |
| Can the loop be demonstrated in 5-10 minutes? | Yes: `docs/DEMO_SCRIPT.md` |

**Still open, stated plainly**: no real language model has been run in this environment, so grading and report wording are verified against a stand-in that reads the same prompts; mastery and adaptation thresholds are documented defaults, not tuned on data; content effectiveness is an association, not a causal estimate; digests are not emailed; no rate limiting on submit or report generation; retention and deletion of learner data; R1-R3; the legacy live-HTTP test files were not re-run; several `planned` administration screens do not exist; the separate `adaptive-engine`, `reporting-engine`, `event-worker` and `digest-worker` services are no longer called by the API for these features and can be retired.
