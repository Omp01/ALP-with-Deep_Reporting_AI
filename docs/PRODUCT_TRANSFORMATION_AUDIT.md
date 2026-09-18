# Product Transformation Audit — Phase 0

**Repository:** `ALP-with-Deep_Reporting_AI`
**Audit date:** 2026-09-17
**Scope:** Full-repository inspection prior to the LMS product transformation.
**Status:** Phase 0 complete. No source files were modified during this audit.

> **Note on the prior audit document.** `docs/CURRENT_IMPLEMENTATION_AUDIT.md` contains several claims
> that no longer match the tree — it reports Next.js 14 / React 18 (actually Next 16.3.5 / React 19.2.8),
> "80 tests passing" (actually 42 test functions), and hardcoded quiz objects in
> `learner/learning/page.tsx` (since replaced with API-driven rendering). This document supersedes it and
> is based on a fresh read of the working tree.

---

## 1. Current Architecture

```text
Next.js 16 App Router (frontend, :3000)
        │   raw fetch() to hardcoded http://localhost:8000
        ▼
FastAPI Gateway  "alms-api"  (:8000)  — 19 routers, 72 endpoints, JWT + RBAC + tenant middleware
        │
        ├── httpx ──► alms-adaptive-engine  (:8001)  BKT mastery, sequencing policy, skill gaps
        ├── httpx ──► alms-reporting-engine (:8002)  analytics → evidence → LLM → citation validation
        ├── httpx ──► alms-ingestion        (:8003)  document/AV text extraction + chunking
        └── httpx ──► alms-s3-storage                MinIO wrapper
        │
        ├── PostgreSQL 16 + pgvector (:5432)  — 25 tables, single Alembic revision
        └── Redis 7 Streams (:6379)           — XADD from API, XREADGROUP by workers

Workers (long-running containers, no scheduler framework):
  event-worker   — consumes learning_events stream, forwards to adaptive engine
  risk-worker    — periodic risk scan (RISK_SCAN_INTERVAL_SECONDS)
  digest-worker  — periodic proactive digest generation (DIGEST_CRON_EXPRESSION)
```

Twelve containers total in `docker-compose.yml`. The three-layer separation the assignment asks for
(adaptive engine / event store / reporting layer) genuinely exists — the reporting engine reads the
event store and never imports adaptive-engine code.

---

## 2. Current Frontend Structure

| Path | LOC | Assessment |
| :--- | ---: | :--- |
| `app/page.tsx` | 156 | Landing + persona routing |
| `app/login/page.tsx` | 224 | Persona switcher, live JWT login |
| `app/learner/dashboard/page.tsx` | ~440 | KPI cards, mastery display |
| `app/learner/learning/page.tsx` | ~900 | Course player — video/article/quiz/lab, API-driven |
| `app/learner/insights/page.tsx` | ~400 | Grounded insights + citation drawer |
| `app/manager/dashboard/page.tsx` | ~400 | Cohort matrix, skill gaps, at-risk cards |
| `app/manager/reports/page.tsx` | ~350 | Digest generation |
| `app/admin/dashboard/page.tsx` | ~500 | Org analytics, ingestion, export, embed sandbox |
| `components/Navbar.tsx` / `Sidebar.tsx` | 102 / 153 | Role-aware but only 6 nav links total |
| `lib/api-client.ts` | 124 | **Written but imported by zero files** |
| `components/ui/`, `features/`, `hooks/`, `services/` | 5 each | **Empty `export {}` placeholders** |

Total application TypeScript: ~4,100 LOC across **8 pages and 2 components**.

### Critical frontend findings

1. **No component library exists.** `components/ui/index.ts`, `features/index.ts`, `hooks/index.ts`, and
   `services/index.ts` are all five-line placeholder files exporting nothing. Every button, card, badge,
   and table is hand-rolled inline in each page. There is no `Button`, `Card`, `Skeleton`, `Toast`,
   `Dialog`, `Tabs`, `Breadcrumb`, or `EmptyState` component anywhere in the tree.
2. **`lib/api-client.ts` is dead code.** All eight pages call `fetch("http://localhost:8000/...")`
   directly — **37 hardcoded absolute URLs**. `NEXT_PUBLIC_API_URL` is defined in `.env.example` and
   never read. The app cannot be deployed anywhere except a machine where the API is on localhost:8000.
3. **Installed-but-unused dependencies:** `@tanstack/react-query` (0 usages), `recharts` (0 usages),
   `next-themes` (0 usages), `class-variance-authority` (0 usages). Every chart in the dashboards is
   hand-drawn with divs, and there is no query cache, no request deduplication, no retry policy.
4. **The design system is defined but not applied.** `app/globals.css` declares a complete 179-line
   token set (`--primary`, `--surface`, `--border`, `--text-secondary`, semantic colors, sidebar
   palette). The pages ignore it and use raw Tailwind utilities (`bg-slate-50`, `text-indigo-700`)
   directly, so the tokens cannot actually retheme the product.
5. **Auth state lives in `localStorage` read ad-hoc in every page** via `useEffect` + `JSON.parse`.
   There is no `useAuth` hook, no auth context, no route guard component — each page reimplements the
   redirect-to-login check.
6. **No loading skeletons, no empty states, no error boundaries, no toasts.**

---

## 3. Current Backend Structure

`services/api` — 19 routers, **72 endpoints**:

| Router | Endpoints | Notes |
| :--- | ---: | :--- |
| auth | 4 | login / refresh / me / logout — solid |
| organizations, users, teams | 3 / 2 / 2 | tenant + directory |
| courses | 9 | course/module/content CRUD (no DELETE) |
| competencies | 5 | competency CRUD + course/module mapping |
| enrollments | 4 | list / create / get / update progress |
| assignments | 6 | create / list / get / submit / submissions / grade |
| events | 4 | single / batch ingest, query, stats |
| learning_sessions | 4 | start / active / end / get |
| adaptive | 5 | next / decisions / competencies / skill-gaps / cohort-gaps |
| ai | 4 | derive-competencies, generate-assessments, review, list |
| ingestion | 4 | upload / process / jobs |
| insights | 3 | generate / get / **evidence** |
| analytics | 3 | learner / team / organization |
| reports | 2 | digest generate / latest |
| export | 3 | events / competencies / risks (streaming CSV+JSON) |
| embed | 1 | iframe report widget |
| risks | 4 | list / by-learner / scan / resolve |

**Quality:** the API layer is genuinely good. Async SQLAlchemy 2.0, Pydantic v2 schemas, `TenantContext`
dependency injected everywhere, `require_roles()` guard, `log_audit_action()`, structured logging,
`/health` + `/ready` on every service. This is production-posture code and should be preserved.

**Architectural inconsistency:** only two files exist under `app/services/` (`ai_service.py`,
`risk_service.py`). All other business logic — progress calculation, enrollment rules, event handling,
analytics aggregation — lives directly inside route handlers. The project declares a service-layer
convention it follows in 2 of 19 routers.

---

## 4. Current Database Structure

**25 tables**, all carrying `org_id` with an index — tenant isolation is modeled correctly.

```text
organizations, audit_logs
users, teams, user_teams
courses, modules, content_items, content_chunks
assessment_items
assignments, assignment_submissions
competencies, course_competencies, module_competencies,
  learner_competencies, competency_history, skill_gaps
enrollments, adaptive_sessions, session_sequence_steps
learning_events
ingestion_jobs
ai_insights, scheduled_reports, report_digests
learner_risks
```

### Schema gaps against the target LMS

| Missing concept | Consequence |
| :--- | :--- |
| `Quiz` / `QuizQuestion` / `QuizOption` grouping | `assessment_items` are loose per-module questions. There is no quiz entity, so `QUIZ_STARTED` / `QUIZ_COMPLETED` / `QUIZ_RETRY` have no subject and no score rollup. |
| `content_progress` (per learner × content item) | Completion is inferred from event scanning; there is no authoritative per-item completion record. |
| `content_id` FK on `learning_events` | Events reference `course_id` and `module_id` only. Content identity is buried in the JSONB payload, so content-level analytics ("where do learners drop off?") cannot be queried relationally. |
| `ContentCompetency` mapping | Competencies map to courses and modules, **not to individual content items or questions**. §23 of the transformation brief requires item- and question-level mapping. |
| `adaptive_decisions` audit table | §26 requires storing decision + reason + previous/new mastery + selected content. Decisions are currently returned in the response and written into `session_sequence_steps.reason` as a free-text string only. |
| Course presentation fields | `courses` has no `thumbnail_url`, `instructor_id`, `category`, `difficulty`, `rating`, `duration`. §9/§10/§48 need all of them. A discovery page cannot be built on this table. |
| `quiz_attempts` / `question_responses` | Per-question responses live only as JSONB event payloads. Retry counts, response times, and attempt numbers cannot be indexed or aggregated. |
| `AssignmentGrade` as a distinct record | Grade is denormalized onto `assignment_submissions`; no grade history on retry. |

### Migration debt — significant

`database/migrations/versions/001_initial_schema.py` is 28 lines and its `upgrade()` body is:

```python
Base.metadata.create_all(bind=op.get_bind())
```

This is **not a migration**. It is `create_all` wearing an Alembic revision id. There is exactly one
revision, it has no table DDL, and it cannot express any incremental change. Phases 2 and 6 will add
~8 tables and alter ~4; that work needs a real autogenerate-based migration chain first.

---

## 5. Current AI Implementation

Two independent, unreconciled AI paths:

**Path A — `shared/schemas/ai_provider.py` (214 LOC).** A proper abstraction: `AIProvider` ABC with
`complete()`, `health_check()`, `provider_name`; `OpenAICompatibleProvider` implementation; `AIMessage` /
`AICompletionRequest` / `AICompletionResponse` Pydantic models; `AIProviderError` with a `retryable` flag;
`get_ai_provider()` factory. Consumed by exactly one file: `services/api/app/services/ai_service.py`
(competency derivation and assessment generation).

**Path B — `services/reporting-engine/app/ai/llm_provider.py` (220 LOC).** The Reporting AI — the
highest-weighted feature in the rubric — **does not use Path A at all.** It is a single
`generate_grounded_narrative()` function containing an inline if-ladder that tries Gemini → Groq →
OpenAI → Anthropic → Ollama → offline fallback, with the HTTP request for each provider written out
longhand in the function body.

### AI findings

1. **Environment variable mismatch.** `.env.example` documents `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`,
   `AI_BASE_URL`. `llm_provider.py` reads `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`,
   `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL` — **none of which appear in `.env.example`**. A developer who
   follows the documented setup gets silent offline fallback for every report and no error explaining why.
2. **The LLM returns free-text prose, not structured output.** §37/§38 require
   `{"insights":[{"claim": "...", "evidence_ids":[...]}]}` validated against a Pydantic schema. The
   current contract is a markdown narrative sprinkled with `[E-1]` markers, parsed back out by
   `CITATION_REGEX`. There is no per-claim evidence binding.
3. **Citation keys are ephemeral.** `[E-1]`…`[E-n]` are assigned by position at package-build time. The
   same claim cites `E-3` in one report and `E-7` in the next. The underlying `source_id` (a real DB UUID)
   *is* carried in the evidence item, so the data is recoverable — but the report's own citation
   vocabulary is not stable or externally meaningful.
4. **Invalid citations are penalized, not rejected.** `validate_grounded_citations()` returns
   `is_valid=False` and subtracts 0.30 from the grounding score, but nothing regenerates or blocks the
   report. §37 requires rejection. The rubric treats unverifiable insights as a *critical failure*.
5. **Scope ownership is never verified.** The validator checks that a cited key exists in the package.
   It does not check that the evidence belongs to the report's scope — the third of the three checks
   §37 requires.
6. **No prompt versioning.** `SYSTEM_PROMPT` is a module-level string constant in the provider file.
   §57 requires `services/reporting-engine/app/prompts/` with explicit `reporting_v1` / `reporting_v2`
   versions; that directory does not exist.
7. **No `docs/AI_PROVIDER_SETUP.md` and no `scripts/check_ai_config.py`** (§40).

**What is genuinely strong:** `evidence/builder.py` builds packages from real SQL against
`learner_competencies`, `learning_events`, `learner_risks`, and `enrollments`, and each item carries a
real `source_id`. `analytics/calculator.py` computes metrics deterministically in Python/SQL before the
LLM is ever called. The "never let the LLM calculate" principle of §44 is already honored.

---

## 6. Current Realtime Implementation

**There is none.**

A repository-wide search for `websocket`, `WebSocket`, `EventSource`, `SSE`, and `Server-Sent` across
all Python and TSX sources returns **zero matches**. Redis Streams carry events server-side to the
workers, but nothing reaches the browser. Every dashboard number updates only on full page reload.

§28 (realtime competency/recommendation updates) and the `docs/REAL_TIME_ARCHITECTURE.md` deliverable
are entirely unimplemented.

---

## 7. Existing LMS Features

| Feature | State |
| :--- | :--- |
| Course / module / content data model | Present, relational, tenant-scoped |
| Content types VIDEO / ARTICLE / QUIZ / ASSIGNMENT | Enumerated on `content_items.content_type` |
| Course player | Partial — one 900-line page; API-driven but monolithic, no reusable renderers |
| Enrollment | Partial — API exists; no UI flow (no Explore → View → Enroll journey) |
| Course discovery / `/explore` | **Absent** |
| Course detail page `/courses/[id]` | **Absent** |
| `/progress`, `/competencies` learner pages | **Absent** |
| Video player with position tracking | **Absent** — no real player, no VIDEO_PROGRESS events |
| Article reader with scroll progress | **Absent** |
| Quiz as a first-class entity | **Absent** — loose assessment items only |
| Assignment submit / status / grade UI | Partial — backend complete, no dedicated UI |
| Admin content management CRUD UI | **Absent** (§33 — the largest single gap) |
| Course thumbnails | **Absent** — no column, no assets |
| Progress calculation from completion records | Partial — `enrollments.progress_pct` is a stored float updated by a PUT, not derived |

---

## 8. Existing Adaptive Features

**This is the strongest part of the codebase.**

- `competency/mastery.py` (185 LOC) — a real Corbett-Anderson **Bayesian Knowledge Tracing**
  implementation with `p_transit` / `p_guess` / `p_slip`, combined with a multi-factor weighted formula
  and an exponential **recency decay** (7-day half-life). This is not a veneer.
- `sequencing/policy.py` + `recommender.py` — decision policy producing `advance`, `remediate`, `skip`,
  `change_modality`, `revisit`.
- `competency/skill_gap.py` (172 LOC) — individual and cohort gap detection.
- `main.py` (448 LOC) — `POST /adaptive/events` updates the learner model and writes `competency_history`;
  `POST /adaptive/next` returns the sequencing decision.

**Gaps:** decisions are not persisted to a dedicated audit table with previous/new mastery (§26); the
"Why this?" explanation is assembled ad-hoc rather than read from a decision record (§27); item selection
does not yet weight by question-level error type; and there are **zero tests** for any of this math.

### Duplicate-directory defect

`services/adaptive-engine/app/` contains `app/app/` **and** `app/app/app/` — two complete recursive copies
of `competency/`, `core/`, `models/`, `sequencing/`, and `main.py`, 114 KB in total. Commit `5929c29`
("Phase T: Remove recursive app/app duplicate folders") did not remove them: `git ls-files` confirms all
of these files are still tracked. Editing `mastery.py` today leaves two stale copies behind that an
import path change could silently resurrect.

---

## 9. Existing Reporting Features

All six required touchpoints have a backing surface:

| Touchpoint | Implementation | State |
| :--- | :--- | :--- |
| Learner insight view | `app/learner/insights/page.tsx` + `/insights/*` | Present, with clickable citation drawer |
| Manager/team view | `app/manager/dashboard` + `reports` | Present |
| L&D admin/program view | `app/admin/dashboard` | Present |
| Scheduled proactive digest | `digest-worker` + `/reports/digest/*` | Present, persists to `report_digests` |
| Embeddable widget | `GET /api/v1/embed/report` | Present, iframe + postMessage |
| Raw export / BI API | `GET /api/v1/export/{events,competencies,risks}` | Present, streaming CSV + JSON, paginated |

They correctly share one engine (`reporting-engine`), satisfying §43 — this is not six hand-written
generators.

**Gaps:** no natural-language query interface (the assignment's first bonus); no forecasting; no
proactive alerting distinct from the scheduled digest; the structured-output and citation-rejection
problems from §5 above; and the report audit record (§56) stores provider/model but not `prompt_version`.

---

## 10. Hardcoded / Demo Behavior

The good news: the classic failure mode is largely **absent**. There are no `const courses = [...]`,
`const mastery = 84`, or fake `chartData` arrays in the React pages. Phases C/E/G of the prior work
genuinely replaced them. The four array literals that remain are legitimate UI configuration:
`personas` (login switcher) and `learnerLinks` / `managerLinks` / `adminLinks` (nav definitions).

What *is* hardcoded:

| Location | Hardcoded value | Impact |
| :--- | :--- | :--- |
| 8 page files, 37 occurrences | `http://localhost:8000` | **High** — undeployable; must route through `lib/api-client.ts` + `NEXT_PUBLIC_API_URL` |
| `enrollments.progress_pct` | Stored float set by `PUT /progress` | **High** — §18 requires derivation from completion records |
| `adaptive_sessions.current_difficulty` | Defaults to `0.5` | Medium — should initialize from the learner's prior mastery |
| `validator.py` | Magic constants `0.70`, `0.25`, `0.30`, `0.20` | Medium — grounding score weights are undocumented literals |
| `llm_provider.py` | `SYSTEM_PROMPT` module constant | Medium — blocks prompt versioning (§57) |
| Evidence builder | `.limit(10)` recent events | Medium — evidence breadth is a hidden constant |
| Course presentation | No thumbnail/instructor/rating columns at all | High for §9/§10 |

---

## 11. Reusable Code — Preserve These

Per §3 of the brief, the following are good and must **not** be rebuilt:

- **Auth & RBAC** — `core/security.py`, `api/deps.py`. JWT, refresh, `TenantContext`, `require_roles()`,
  system_admin escalation, audit logging. Production quality.
- **Multi-tenancy** — `org_id` + index on all 25 tables, tenant dependency on every route.
- **Async DB layer** — `core/database.py`, SQLAlchemy 2.0 async sessions, both async and sync engines.
- **Adaptive math** — `mastery.py` BKT, `skill_gap.py`, `policy.py`. Extend; do not replace.
- **Evidence builder** — real SQL, real `source_id`s. Enrich; do not replace.
- **Deterministic analytics** — `analytics/calculator.py`. The LLM-free metric layer is correct.
- **Event pipeline** — `POST /events` → Postgres → Redis XADD → `event-worker` XREADGROUP.
  Idempotency via client-supplied `event_id` already works.
- **Export / embed / digest surfaces** — all three are real and working.
- **`shared/schemas/ai_provider.py`** — the abstraction §39 asks for already exists; the Reporting AI
  simply needs to be moved onto it.
- **Docker Compose topology** — 12 services, healthchecks, internal network. Keep as is.
- **Design tokens** in `globals.css` — the palette is well chosen; it just needs to be actually used.

---

## 12. Broken / Incomplete Functionality

| # | Issue | Severity |
| :-- | :--- | :--- |
| 1 | `services/adaptive-engine/app/app/` and `app/app/app/` recursive duplicates still tracked in git | High |
| 2 | Alembic revision 001 is `create_all`, not DDL; no incremental migration path | High |
| 3 | `.env` absent — `docker compose config` fails; `docker compose up` cannot start | High |
| 4 | Reporting AI reads env vars that `.env.example` never documents | High |
| 5 | `lib/api-client.ts` unused; 37 hardcoded API URLs | High |
| 6 | Zero unit tests for `mastery.py`, `validator.py`, `builder.py`, `policy.py` — the four highest-rubric-weight modules | High |
| 7 | All 42 tests are live-HTTP integration tests against `localhost:8000` with a seeded DB; no `conftest.py`, no fixtures, no CI-runnable path | High |
| 8 | `services/{adaptive-engine,reporting-engine,ingestion}/tests/` contain only `__init__.py` | High |
| 9 | No realtime transport of any kind | High |
| 10 | Invalid citations lower a score but never reject a report | High |
| 11 | Business logic in route handlers despite a declared service-layer convention | Medium |
| 12 | Three separate SQLAlchemy model definitions (`api/app/models/`, `adaptive-engine/.../tables.py`, `reporting-engine/.../tables.py`) — schema drift risk | Medium |
| 13 | No DELETE endpoints for course/module/content — admin CRUD is create/read/update only | Medium |
| 14 | `GET /courses` has pagination but no search, category, difficulty, or sort | Medium |
| 15 | `recharts`, `react-query`, `next-themes`, `cva` installed and unused | Low |
| 16 | `docs/CURRENT_IMPLEMENTATION_AUDIT.md` contains stale, incorrect claims | Low |

**Test count correction:** 42 test functions across 9 files, not the 80 previously documented.

---

## 13. Assignment-Scope Gaps

Mapped to the rubric in Assignment 04:

| Rubric area | Weight | Current standing | Gap to close |
| :--- | ---: | :--- | :--- |
| Adaptive learning quality | 20% | **Strong** — real BKT, real in-session decisions | Persist decision audit; weight item selection by error type; test the math |
| Deep reporting AI quality | 20% | **Medium** — narrative is grounded but unstructured | Structured `{claim, evidence_ids}` output; causal-vs-correlational language guardrails; NL query interface |
| Groundedness / explainability | 15% | **Medium-risk** | Reject invalid citations; verify scope ownership; stable citation identifiers |
| Breadth of reporting touchpoints | 15% | **Strong** — all six exist and share one engine | Polish each as a real product surface |
| Production readiness & multi-tenancy | 15% | **Strong on isolation, weak on ops** | Real migrations; `.env`; realtime; performance under event growth |
| Constraint adherence | 5% | **Compliant** | Keep UI and reporting logic first-party |
| Code quality, tests & docs | 10% | **Weak** — 42 integration-only tests, 0 unit tests on core logic | Unit-test mastery + grounding specifically; the rubric names these two by name |

Transformation-brief gaps beyond the rubric: no `/explore`, no `/courses/[id]`, no `/progress`, no
`/competencies`, no admin content CRUD UI, no component library, no realtime, no quiz entity, no
content-level progress records, no prompt versioning, and 11 required documents/diagrams missing
(`LMS_ARCHITECTURE.md`, `CONTENT_MODEL.md`, `LEARNING_EVENT_PIPELINE.md`, `AI_PROVIDER_SETUP.md`,
`REAL_TIME_ARCHITECTURE.md`, `DEMO_FLOW.md`, plus four `.mmd` diagrams and `scripts/check_ai_config.py`).

---

## 14. UX Problems — Why This Does Not Feel Like a Professional LMS

1. **There is no product surface for the core LMS verb.** A learner cannot browse a catalog, open a
   course page, read what they will learn, and choose to enroll. The app opens onto a dashboard for
   courses the seed script assigned them. That single absence is what makes it read as a dashboard demo
   rather than a learning platform.
2. **Eight pages, no product.** Udemy-class products are fifty-plus screens built from thirty shared
   components. This is eight bespoke pages sharing two components.
3. **Every page looks hand-built because it is.** No shared `Card`, `Button`, or `Badge` means spacing,
   radii, and shadows drift page to page.
4. **Blank screens during load.** No skeletons; pages flash empty, then fill.
5. **Navigation labels are engineering labels.** "Adaptive Learning", "AI Insights & Why?",
   "Grounded Digests", "Executive Analytics" describe the architecture, not the user's task. A learner
   looks for "My Learning" and "Explore".
6. **Six nav links for a platform with 72 endpoints.** Most of the backend has no front door.
7. **Content consumption is not modeled as an experience.** No real video player, no reading progress,
   no lesson-to-lesson flow, no "Mark Complete", no prev/next.
8. **Dead ends.** Nothing tells a user with no data what to do next.
9. **The design system exists only in CSS comments.** Tokens are declared and then bypassed.
10. **Desktop-only assumptions.** A fixed `w-64` sidebar and no collapsible curriculum make the course
    player unusable on mobile.

---

## 15. Target Product

A multi-tenant B2B learning platform where:

- A learner lands on a personalized home (continue learning, my courses, adaptive recommendations),
  **browses a real catalog** with search/filter/sort, opens a professional course page, **enrolls**,
  and enters a course player that renders VIDEO / ARTICLE / QUIZ / ASSIGNMENT from a single
  `ContentRenderer` driven by `content_items.content_type`.
- Every interaction emits an immutable, idempotent, content-scoped learning event.
- Those events drive a per-competency BKT mastery model, which drives an adaptive decision that is
  **persisted with its reason and mastery delta**, so "Why was this recommended?" is answered from a
  record rather than regenerated.
- Deterministic analytics roll up over the event store; an evidence engine assembles scope-verified
  fact packages; an LLM behind a swappable `AIProvider` interprets them into **structured, per-claim-cited
  insights**; a validator rejects any claim whose citations do not exist or do not belong to the scope.
- Six distinct reporting surfaces consume that one insight capability.
- Managers see real team state and evidence-backed at-risk explanations; L&D admins manage content and
  read org-wide competency and drop-off analysis.

---

## 16. Migration Strategy

Guided by §3 — refactor, do not rebuild.

**Preserve untouched:** auth/RBAC, tenant middleware, async DB layer, Docker topology, BKT mastery math,
skill-gap logic, evidence builder SQL, deterministic analytics, event ingestion pipeline, export/embed/
digest endpoints, `shared/schemas/ai_provider.py`.

**Additive-first schema.** New tables (`quizzes`, `quiz_questions`, `quiz_options`, `quiz_attempts`,
`question_responses`, `content_progress`, `content_competencies`, `adaptive_decisions`) and new nullable
columns on `courses` and `learning_events`. Nothing existing is dropped, so every current endpoint keeps
working through the transition. Before any of it: replace revision 001 with real autogenerated DDL and
establish a working revision chain.

**Strangler pattern on the frontend.** Build the component library and app shell first, then introduce
new routes (`/explore`, `/courses/[id]`, `/learn/[courseId]/[contentId]`, `/progress`, `/competencies`,
`/admin/courses`) alongside the existing pages. Migrate existing pages onto shared components and
`lib/api-client.ts` one at a time. The app is never in a broken state.

**Consolidate the AI path.** Move `generate_grounded_narrative()` onto `AIProvider`, extract prompts
into a versioned `prompts/` package, add the structured Pydantic response schema, then tighten the
validator to reject. Reconcile `.env.example` with what the code actually reads, in the same change.

**Fix the foundations before building on them.** Delete the recursive `app/app` trees, write `.env`,
add `conftest.py` with fixtures, and add unit tests for `mastery.py` and `validator.py` early — the
rubric names those two modules explicitly, and every later phase depends on them being trustworthy.

**Verification gate after each phase** (§81): build → run tests → run the stack → verify prior
functionality → commit. One commit per phase, preserving the clean history the assignment requires.

---

## 17. Phase Roadmap

| Phase | Deliverable | Key risk |
| :--- | :--- | :--- |
| **0** | This audit | — |
| **1** | Design system + component library + role-aware app shell; adopt `api-client`; skeleton/empty/error states | Touching 8 live pages — migrate incrementally |
| **2** | Real migration chain; quiz/progress/decision/mapping tables; course presentation columns; expanded seed | Migration chain must be rebuilt first |
| **3** | `/explore` + `/courses/[id]` + enrollment flow + My Learning; search/filter/sort on `GET /courses` | — |
| **4** | `ContentRenderer` / `VideoPlayer` / `ArticleViewer` / `QuizRenderer` / `AssignmentRenderer`; prev/next; mobile curriculum | Retiring the 900-line player page |
| **5** | `content_id` on events; quiz/video/article/assignment event types; idempotency tests | Event schema change is additive |
| **6** | Content- and question-level competency mapping; derived progress; mastery from real responses | Derived progress replaces the stored float |
| **7** | `adaptive_decisions` audit table; "Why this?" from persisted records; error-type-weighted selection | — |
| **8** | WebSocket/SSE for competency, progress, recommendation updates | Entirely new subsystem |
| **9** | Learner / manager / admin analytics endpoints; risk detection on real signals | Query performance at volume |
| **10** | Structured insight schema; `prompts/` with versions; `AIProvider` consolidation; citation rejection | Highest rubric weight — highest care |
| **11** | Six reporting surfaces on the shared engine; evidence UI everywhere | — |
| **12** | Admin course/module/content/quiz/assignment CRUD UI; competency mapping UI | Largest remaining UI build |
| **13** | Scheduled reports, JSON/CSV export, embed hardening | Mostly exists |
| **14** | Full UX pass: responsive, a11y, empty/loading/error, navigation | — |
| **15** | Unit + integration tests across all services; `docs/DEMO_FLOW.md`; end-to-end run | Test debt is largest here |

Documentation is written **within** the phase that creates the behavior, not deferred: `CONTENT_MODEL.md`
(P2), `LEARNING_EVENT_PIPELINE.md` (P5), `ADAPTIVE_ENGINE.md` update (P7), `REAL_TIME_ARCHITECTURE.md`
(P8), `REPORTING_AI.md` + `AI_PROVIDER_SETUP.md` + `scripts/check_ai_config.py` (P10), `API.md` and
`CODE_MAP.md` continuously, `REQUIREMENTS_TRACEABILITY.md` and `DEMO_FLOW.md` (P15).

---

## Phase 0 Summary

**PHASE:** Complete repository audit.

**WHY:** Establish what exists before transforming it, per §2/§3 — do not destroy working code.

**ASSIGNMENT ALIGNMENT:** §4 (audit document), §76 Phase 0, §79/§80 (inspect before assuming).

**FILES:** Created `docs/PRODUCT_TRANSFORMATION_AUDIT.md`. **No source files modified.**

**DATABASE:** No changes.

**BACKEND:** No changes.

**FRONTEND:** No changes.

**DYNAMIC VS HARDCODED:** Nothing changed yet. The material hardcoding found is the 37 absolute API URLs,
the stored `progress_pct`, and the missing course-presentation columns — scheduled for Phases 1, 6, and 2
respectively.

**NEXT:** Awaiting `START PHASE 1` — design system, component library, and role-aware app shell.
