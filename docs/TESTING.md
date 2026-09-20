# Testing

There are three test surfaces. They are independent.

| Suite | Location | Needs | Status |
|---|---|---|---|
| **Foundation + learning experience + content ingestion + events + competency engine** (Phases 1-5) | `services/api/tests/foundation/` | PostgreSQL only (the compose `postgres` container) | 1017 passed, 1 skipped (PPTX needs `python-pptx`, so one test skips). The expected failure for audit R7 is gone: it is fixed |
| **Storage service** (Phase 3) | `services/s3-storage/tests/` | Nothing (in-process) | 21 passed |
| **Browser journey, learner** (Phase 2) | `scripts/e2e/learner_journey.mjs` | A running API, frontend, and Chrome or Edge (no npm packages) | 25 of 25 checks pass |
| **Browser journey, learning events** (Phase 4) | `scripts/e2e/learning_events_journey.mjs` | A running API, frontend, and Chrome or Edge; a freshly seeded database per learner | 32 of 32 checks pass |
| **Browser journey, admin content** (Phase 3) | `scripts/e2e/admin_content_journey.mjs` | The above plus `scripts/e2e/fake_llm_server.py` and a running storage service | 37 of 37 checks pass |
| **Browser journey, adaptive engine and reporting** (Phases 6-8) | `scripts/e2e/reporting_journey.mjs` | The same servers, and the fake model (which also answers reporting requests; start the API with `AI_MODEL_REPORTING=fake`) | 33 of 33 checks pass |
| **Browser journey, competency engine** (Phase 5) | `scripts/e2e/competency_journey.mjs` | The same as the admin journey, plus `python scripts/generate_demo_data.py` on the scratch database | 48 of 48 checks pass |
| **Legacy live-HTTP** | `services/api/tests/test_*.py` (fewer since Phase 4: `test_events.py` and `test_event_idempotency.py` were replaced by the foundation event tests) | A running API on `:8000`, a seeded dev database, and for some tests Redis and the adaptive/reporting services | **Not re-run in Phases 1–2.** They were written for the old schema; expect to revisit them as Phases 4–7 replace what they test. One (`test_lms_core.py`) was edited in Phase 2, because it asserted that a learner can declare their own enrollment 100 % complete |

The earlier claim of "80/80 tests passing" was wrong: the legacy suite contains 45 test functions.

## Foundation suite

```powershell
cd services\api
python -m pytest tests\foundation              # everything (about 50 s)
python -m pytest tests\foundation\unit         # pure logic, no database (under 1 s)
python -m pytest tests\foundation -m integration
```

Requires the `postgres` container to be up (`docker compose up -d postgres`). No API server, Redis, or MinIO is needed: HTTP tests call the FastAPI app in-process.

### How it works

1. A throwaway database named `adaptive_lms_test` is dropped and recreated at the start of the run. **It never touches your dev database**: the runner refuses to start unless the name contains `test` and differs from the app database. Override the name with `TEST_DATABASE_NAME`.
2. The schema is built by running the project's real **Alembic migrations** (`alembic upgrade head`), so the schema under test is the schema that ships, constraints included, and the migration chain is exercised on every run.
3. Tests arrange state with small factories (`make_org`, `make_user`, `make_competency`, `make_course`) that write straight to the database, then call the API in-process with `httpx` and a real signed token.

### What it covers

| File | What it proves |
|---|---|
| `unit/test_rbac.py` | Role vocabulary, legacy aliases, no inheritance, super-admin bypass |
| `unit/test_skill_graph_algorithms.py` | Levels, cycle detection with the full path, transitive prerequisites, unmet-prerequisite logic |
| `unit/test_learning_rules.py` | Completion percent, time-credit clamp, resume choice, YouTube URL parsing (including hostile URLs), media resolution, duration, activity wording |
| `integration/test_schema.py` | The database itself rejects self-loops, cross-tenant edges, out-of-range values and unknown content status; role catalogue seeded |
| `integration/test_skill_graph_api.py` | Add/remove, duplicate, self, direct and indirect cycles, levels, permissions, route ordering |
| `integration/test_roles_api.py` | Assignment rules, audit trail, effect on guarded routes, legacy fallback |
| `integration/test_courses_foundation.py` | No fabricated rating, computed duration, real enrolment counts, full content persistence |
| `integration/test_progress_api.py` | Derived progress, server-verified quiz/assignment completion, time clamp, events emitted once, enrolment sync, the retired "set my progress" endpoint |
| `integration/test_learning_api.py` | Overview, player payload, home: published-only visibility, prerequisites, objectives fallback, recommendations and their stated reasons, honest empty states |
| `integration/test_tenant_isolation.py` | Tenant A cannot touch tenant B's data — see [MULTI_TENANCY.md](MULTI_TENANCY.md) |
| `unit/test_ingestion_rules.py` | Upload validation (extension, magic bytes, zip limits, hostile filenames, content/extension mismatch), YouTube URL and page/caption parsing, JSON extraction, schema coercion, grounding and near-duplicate checks, deterministic shuffle, competency matching, excerpt selection, prompt fencing, provider error wording, Ollama model selection |
| `unit/test_text_extraction.py` | Real PDF/DOCX/text extraction, multi-page PDFs, tables and headings, broken files raise named errors, formats that are not documents are refused (PPTX skipped when `python-pptx` is missing) |
| `integration/test_ingestion_api.py` | The whole pipeline through the API: file and YouTube ingestion, stages, validation rejections, duplicates, storage and AI outages (kept content, visible reason, retry), malformed model output and its one repair attempt, ungrounded questions dropped, prompt-injection fencing, caching and forced re-analysis, transcripts, embeddings, library filters, job polling, restart recovery |
| `integration/test_ingestion_review_publish.py` | Review edits (metadata, analysis, competency decisions, question edit/approve/reject/bulk/manual/delete, option validation) and publish (competency create/link + mappings, only approved questions become a quiz, republish appends, unique codes, blockers, locking, unpublish hides from learners, delete rules) |
| `integration/test_ingestion_tenant_isolation.py` | 16 foreign-id requests against the content admin API all return 404 and change nothing; library and search never leak; a foreign competency cannot be used |
| `services/s3-storage/tests/test_storage_security.py` | Storage requires a token, rejects traversal (including raw `..` that HTTP clients normalise away), bad bucket names, oversize objects, and escapes listings |

### Known expected failure

`test_event_ids_do_not_collide_across_tenants` is a strict `xfail` documenting audit finding R7. When Phase 4 fixes it the test will start passing, pytest will report it as `XPASS(strict)` and fail the run until the marker is removed — a deliberate prompt to delete the `xfail`.

### Verifying the tests can fail

The isolation tests were mutation-checked: removing the `org_id` filter from `GET /content/{id}` made `test_foreign_resources_are_not_found[8]` fail, and restoring it made it pass. Repeat this after adding new tenant-owned endpoints.

## Browser journey (real Chrome, real pages)

`scripts/e2e/learner_journey.mjs` signs in through the real login API and drives the real pages with a small dependency-free Chrome DevTools client (`scripts/e2e/cdp.mjs`; Node 22+ has a built-in WebSocket). It checks Home, Course Detail, the player for a video, a reading (Markdown, code blocks, completing it), a quiz (grading, and that the server's status matches), an assignment (submission and server-side completion), the mobile layout (outline drawer, no horizontal scroll), and a weak-competency learner's recommendations. It saves screenshots and fails on unexpected browser console errors.

It completes lessons as it goes, so run it against a **freshly seeded database**, and against servers you start for the purpose so your own are not touched:

```powershell
# 1. A scratch copy of your data (from the repository root)
docker exec alms-postgres psql -U adaptive_lms -d postgres -c "CREATE DATABASE alms_e2e"
docker exec alms-postgres pg_dump -U adaptive_lms adaptive_lms | docker exec -i alms-postgres psql -U adaptive_lms -d alms_e2e -q
$env:DATABASE_URL_SYNC = "postgresql://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/alms_e2e"
python -m alembic -c database/alembic.ini upgrade head
python scripts/seed.py

# 2. An API on :8100 that allows the test frontend's origin
cd services\api
$env:DATABASE_URL = "postgresql+asyncpg://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/alms_e2e"
$env:CORS_ORIGINS = "http://localhost:3100"
python -m uvicorn app.main:app --port 8100          # leave running

# 3. A frontend on :3100 with its own build directory (new terminal, from frontend\)
$env:NEXT_DIST_DIR = ".next-e2e"; $env:NEXT_PUBLIC_API_URL = "http://localhost:8100"
npx next dev -p 3100                                  # leave running

# 4. The journey (new terminal, from the repository root)
node scripts/e2e/learner_journey.mjs
```

`NEXT_DIST_DIR` and `CORS_ORIGINS` exist so this run cannot disturb a dev server on :3000. Next may rewrite `frontend/tsconfig.json` to mention the extra build directory; `git checkout frontend/tsconfig.json` undoes it.

**What it cannot show.** In the environment where it was written there was no outbound internet, so the YouTube iframe was verified to be present with the right URL, but actual playback was not.

## Migrations

```powershell
# from the repository root
$env:DATABASE_URL_SYNC = "postgresql://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"
python -m alembic -c database/alembic.ini upgrade head      # apply
python -m alembic -c database/alembic.ini current          # show revision
python -m alembic -c database/alembic.ini downgrade 002_lms_entities
```

Revisions `003_foundation` and `004_learning_experience` were each verified on a brand-new database and on a copy of a populated dev database; 003 also through a downgrade followed by an upgrade. Revision 004 merges duplicate progress rows before adding a unique index, back-fills tenant ownership and quiz links, and reconciles enrollment progress with real lesson records.

Revision `007_competency_engine` was verified the same ways: on a brand-new database (the migration tests), on a database with data at revision 006 (`test_migration_007.py`), and on a `pg_dump` copy of the developer's own database, which was still at revision 002, so the whole 002 to 007 chain ran over real rows (its 7 competency rows became `legacy_unverified`). It also runs again on an already-migrated schema without changing anything and without demoting a state written by the new engine.

Revision 001 still runs `create_all()` from the current models, so on a fresh database every later object already exists; revisions 002, 003 and 004 detect that and skip what is present. New revisions from 005 onward should be plain DDL.

## Legacy live suite

```powershell
# API on :8000 and a seeded dev database must be running
cd services\api
python -m pytest tests\test_auth_rbac.py -v
```

Run each file separately; several assume the demo seed data (`alice.learner@acme.com`, and so on).

## Frontend

```powershell
cd frontend
npx tsc --noEmit        # type check
npx eslint .            # lint
npm run build           # production build (stop `npm run dev` first; both use .next)
```

The Phase 2 learner pages are covered by the browser journey above, and `npm run build` succeeds (run it with `NEXT_DIST_DIR` set to a separate directory if `npm run dev` is running). The Phase 1 skill-graph page was type-checked, linted and confirmed to compile, but its interactions (add, remove, cycle message) have **not** been exercised in a browser.

## Content ingestion: what is real and what is a test double

`tests/foundation/fakes.py` replaces only what cannot run in a test: object storage (in memory), the language model (`ScriptedAI`, an *extractive* model that answers from the sentences in the prompt, so grounding checks pass for honest reasons and can be made to fail on purpose), and YouTube (`httpx.MockTransport` serving realistic watch-page and caption payloads). File parsing, chunking, validation, verification, competency matching, review and publishing all run for real, against a real PostgreSQL schema built by the migrations. `build_pdf` writes a genuine PDF and `build_docx` a genuine DOCX for the extractors.

**Not verified in this environment:** a real LLM's behaviour on real material, real YouTube responses, real transcription, real embeddings, and PPTX extraction (no `python-pptx`). The first live run may need prompt or model tuning; see [AI_PROVIDER.md](AI_PROVIDER.md).

## Admin content journey (real Chrome)

`scripts/e2e/admin_content_journey.mjs` adds a document through the wizard, watches it process, approves / rejects / edits / writes questions, edits the analysis, publishes, checks as a learner (API and browser) that the lesson and quiz appeared and that nothing did before publishing, unpublishes, provokes a duplicate, an unsupported file, a legacy `.doc`, a non-YouTube link and an AI outage (then retries), and checks the mobile layout and console errors.

It needs, besides the API and frontend, the hardened storage service and a model server. `scripts/e2e/fake_llm_server.py` is an OpenAI-compatible stand-in (extractive; `POST /__mode {"fail": true}` simulates an outage). The platform's own code does everything else.

```powershell
# from the repository root; scratch database as in the learner journey above (alms_e2e, migrated to head)
# 1. storage (new terminal)
cd services\s3-storage
$env:STORAGE_ROOT = "$env:TEMP\alms-e2e-storage"; $env:STORAGE_TOKEN = "e2e-token"
python -m uvicorn app.main:app --port 9100
# 2. the fake model (new terminal, repository root)
python scripts\e2e\fake_llm_server.py 8199
# 3. the API (new terminal, services\api)
$env:DATABASE_URL = "postgresql+asyncpg://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/alms_e2e"
$env:CORS_ORIGINS = "http://localhost:3100"
$env:MINIO_ENDPOINT = "127.0.0.1:9100"; $env:STORAGE_TOKEN = "e2e-token"
$env:AI_PROVIDER = "ollama"; $env:OLLAMA_BASE_URL = "http://127.0.0.1:8199"; $env:AI_MODEL_ANALYSIS = "fake"; $env:AI_MODEL_QUESTIONS = "fake"
$env:ALLOWED_FILE_TYPES = "pdf,docx,pptx,txt,md,mp4,webm,mov,mp3,wav,m4a"
python -m uvicorn app.main:app --port 8100
# 4. the frontend (new terminal, frontend\)
$env:NEXT_DIST_DIR = ".next-e2e"; $env:NEXT_PUBLIC_API_URL = "http://localhost:8100"; npx next dev -p 3100
# 5. the journey (repository root)
node scripts\e2e\admin_content_journey.mjs
```

Each run uses content unique to that run, so it can be repeated on the same database. Afterwards: stop the servers, `DROP DATABASE alms_e2e`, `git checkout frontend\tsconfig.json`, and delete `frontend\.next-e2e`.

## Learning events and sessions (Phase 4)

`services/api/tests/foundation/`:

| File | What it proves |
|---|---|
| `unit/test_event_vocabulary.py` | Every event type has a policy; the spec's vocabulary exists; a browser can report only interaction, never evidence; legacy names map to current ones; payload validation (strict for learners, bounded, JSON-safe); the held-back stream events; error types are not inferred from timing; response times are clamped; browser timestamps are believed only when plausible; cursors round-trip and reject garbage |
| `integration/test_event_store.py` | The database itself: UPDATE and DELETE on events are rejected (including through the ORM); removing a user, course, module, content item or organisation that events refer to is refused, not cascaded; an event cannot name another learner's or another tenant's session; session time and reason constraints; one open session per learner per course. The store under concurrency: eight simultaneous retries record one event, six simultaneous starts open one session; the same key in two tenants is two events. The outbox: streamed events get a row and held-back ones do not, delivery marks it, an outage delays delivery and records the error, retries back off and are capped, batch limits |
| `integration/test_sessions_api.py` | Start, resume, per-course sessions, tenant-checked course, end (twice), heartbeat, the active endpoint; a forgotten session is closed **at its last activity**, not when noticed; implicit sessions from progress; explicit sessions reused by later activity; visibility for learners, managers (their team only) and admins; summaries counted from events; filters |
| `integration/test_events_api.py` | What a browser may report, and every check on it: server-only types refused (10 of them, and for an administrator too), unknown and retired types, references derived from the item and tenant-checked, mismatched course, strict payloads, per-learner idempotency keys, timestamp bounds, session ownership and end, question events needing the caller's open attempt (and late but genuine ones accepted), assignment references, batches (atomic, bounded, retry-safe). Queries: every filter, combined types, time windows, keyset pagination with equal timestamps and while new events arrive, ordering, cursors, visibility, stats |
| `integration/test_event_emission.py` | What the server records as a learner works: progress (started, completed, typed completion pointing at it, once), quiz attempts (started, retry, every answer with the spec's per-answer fields, the completion), answer rows holding the same evidence, whole quiz in one session in order, assignment submit and grade (the grade is the learner's evidence and belongs to no session), the outbox holds streamed facts and skips held-back ones, a stream outage cannot fail a request, content with activity cannot be deleted |
| `integration/test_events_tenant_isolation.py` | Tenant B's sessions, events, attempts and assignments cannot be read, ended, joined or written into by tenant A's admins, learners or managers; listings and statistics never include them; a super admin reaches them only by naming the tenant |
| `integration/test_migration_006.py` | The migration on a database that holds data: adaptive sessions carried over with their ids (a second open session is superseded), event references filled from payloads only where the row exists **in the same tenant**, garbage payloads ignored, append-only afterwards, upgrade / downgrade / upgrade |

The migration test builds a second scratch database (`<test db>_mig006`, dropped afterwards) because the shared test database is built on an empty schema and cannot show what a migration does to existing rows. Revision 001 is `create_all` from the current models, so on a fresh database the new tables already exist without their constraints when 006 runs; 006 therefore ensures each constraint and index individually. A test caught this.

**Mutation checks** (Phase 4): the visibility scoping, the server-only rule, the tenant checks on content and question references, idempotency, session ownership, idle-at-last-activity, response-time clamping and the held-back stream events were each broken in turn; nine of nine broken versions failed the tests. One survived at first (the tenant check on question references was masked by the attempt-ownership check), which led to a test where only the tenant check can stop the request.

### Browser journey: learning events

`scripts/e2e/learning_events_journey.mjs` needs only the API and frontend (no storage or model server). A learner opens a lesson, reads an article to completion, takes a quiz, hands in an assignment and leaves; then the browser tries to forge a graded answer; then an administrator opens the Learning Activity page and a session's timeline. Every assertion reads what the **server stored** (events, session, summary), not what the page shows: lesson opened with its source, one session for the visit, the article's started / completed / typed events, each question shown and answered with time and error type, order, the session summary, the session ending when the page is left, the forged event refused and not stored, the activity page and timeline, a learner refused the page and the statistics. **32 of 32 checks passed** (run for three different learners on freshly seeded databases). It needs a fresh seed per learner because it completes lessons.

The run also exercised the delivery path against a real Redis: every event that was queued reached the stream (54 published, 0 pending) with the dispatcher running in the API.

It found three real defects, all fixed: the first lesson's `lesson_opened` was silently dropped when the lesson and the course loaded in the same render (React runs child effects before parent effects); the last question's `question_shown` was rejected because it reached the server after the attempt was submitted; and the same lateness applied to the last events before a session ends. Not covered: video playback events (the seeded videos are YouTube embeds and there is no internet in the build environment); they are covered by the API tests.

## Competency engine and grading (Phase 5)

`services/api/tests/foundation/`:

| File | What it proves |
|---|---|
| `unit/test_bkt.py` | The update stays a probability for every combination of signal, confidence, difficulty, attempt and guess floor; is deterministic; moves the right way (monotonic in the signal; a hard question counts more when right and less when wrong; a coin-flip question proves less than a four-way one; retries and unsure sources weigh less); confidence is `n / (n + K)` and grows with evidence whatever the answers; `fold` equals the step chain; parameters are returned so it can be redone; the trend reads history and not the level |
| `unit/test_grading_rules.py` | What is done with a model's answer: accepted only with the right skill, a quote found in the answer, and enough confidence; each failure sends it to review; scores are clamped, percentages understood, garbage rejected; the learner's answer is fenced and cannot close the fence; a blank answer never reaches the model; outage, timeout, garbage and wrong shape all leave the answer for a person; an injected answer that fools the model is still caught by the checks |
| `unit/test_gaps_and_risk_rules.py` | Every gap and risk rule with its thresholds and the figures in its wording; "not enough evidence" instead of a gap; other signals do not make a gap; cohort summaries count learners and skip those with too little evidence; levels from points |
| `integration/test_competency_engine.py` | Multiple-choice, written and assignment answers each leave evidence and an update; the stored state equals the pure function over that evidence; blank answers and reading are not evidence; retries weigh less; `competency_updated` per update; written answers: accepted grade with quote and events in order, blank scored 0 without a model call, model down / low confidence / unverified quote / wrong skill / garbage all held for review with no evidence and no invented grade; the review queue, a human grade (confidence 1.0) finalising the attempt, lesson and `assessment_completed` once, an attempt with two waiting answers, wrong-role and wrong-state review; `explain` and `verify` (including detecting a tampered state); evidence and updates cannot be edited or deleted; one source event applies once; concurrent evidence forms one ordered chain; a foreign competency is rejected; unverified legacy numbers are hidden and replaced with a note; visibility for learner, manager and admin; another tenant reaches nothing; gaps with reasons, one answer is not a gap, cohort counts, managers' team scope; risk from evidence with figures and evidence ids, no invented risk |
| `integration/test_written_authoring.py` | Written questions can be authored (answer key and rubric required, no options, competency required, types validated, edits, tenant), publishing carries the key and rubric, learners see the rubric and not the key, and an answer is graded into evidence or waits for review |
| `integration/test_migration_007.py` | The migration on a database with data: old figures kept but marked unverified, duplicates resolved to the newest, out-of-range values clamped, uniqueness and range enforced afterwards, evidence tables append-only with tenant-safe keys, re-running changes nothing and never demotes real evidence, downgrade / upgrade |

`tests/foundation/fakes.py::ScriptedAI` now also plays the grading model: it reads the grading prompt the product sends and answers from the overlap between the answer and the expected answer (or from a callable / fixed output / outage per test). It is a test double only.

**Mutation checks** (Phase 5): the quote check, skill check, confidence threshold, retry discount, difficulty adjustment, legacy-row filter, learner visibility, grading tenant filter, blank-answer rule, idempotency, state lock, the rule that a waiting attempt cannot pass, and managers' risk scoping were each broken in turn; 13 of 14 broken versions failed the tests. The survivor removed the tenant filter on `GET /mastery/evidence/{id}`: the learner-visibility check that follows it also scopes by tenant, so the filter is defence in depth and no request can tell the difference.

### Browser journey: competency engine

`scripts/e2e/competency_journey.mjs` needs the API, the frontend and `scripts/e2e/fake_llm_server.py` (which now also plays the grading model). Use a freshly migrated and seeded database and run `python scripts/generate_demo_data.py` once. Start the servers as for the admin content journey, with one more variable on the API: `$env:AI_MODEL_GRADING = "fake"`. An admin adds material, writes a short-answer question with a rubric in the review screen and publishes; a learner answers the quiz and sees a graded written answer with feedback; the Competencies page shows the mastery and "Why?" opens a chain that recomputes; with the model down a second learner's answer waits for a reviewer, is not evidence and the attempt is not passed; the admin grades it in "Answers to review" and the attempt is finalised with the reviewer's grade as evidence at full confidence; the gaps and risk page shows counts and reasons that match the API; learners and managers are refused what they should be. Assertions read what the server stored.

Results on freshly seeded scratch databases (a copy of the developer's database, migrated 002 to 007): competency journey **48 of 48**, and the earlier journeys as regression: learner **25 of 25** (its "weak-competency learner is recommended content" check now reads mastery the engine derived from synthetic answers: "Your Python Functions, Scope & Closures mastery is 34%"), learning events **32 of 32** (the session summary now also counts the `competency_updated` events), admin content **37 of 37** (with the new question editor). The journeys that complete lessons need a fresh database, as before.

What the browser journeys found: one real defect, that the shared table row component dropped `data-*` attributes (fixed: it now passes them through). They also showed that a second run of the competency journey on the same database has to measure evidence before and after rather than assume none exists, which the script now does.

**Not verified** in this environment: a real language model grading real answers (the grading model is a test double that reads the same prompt the product sends), and video playback events.

## Adaptive engine, reporting, widget (Phases 6-9)

`services/api/tests/foundation/`:

| File | What it proves |
|---|---|
| `unit/test_adaptive_engine.py` | Every rule of the decision function in isolation (no evidence -> learn or assess; prerequisite gap; repeated typed error -> another format, and not when nothing else exists; hard questions -> easier; struggling -> remediate or revisit; content since the last answer -> assess; low confidence; declining; mastered streak -> skip ahead; above target -> harder; default; nothing mapped is reported, not invented) and that the explanation contains only facts the data supports |
| `unit/test_citation_validator.py` | What stops a reporting model from inventing: numbers must match the cited evidence (as a fraction, a percentage or rounded) and uncited numbers do not count; no evidence, invented ids and metrics, another tenant's record, another learner's record, records outside the period, causal claims and causal wording are all refused, while "does not establish that ... caused ..." is accepted; narrative summaries are held to the same numbers; package hashing and the compact form the model sees |
| `integration/test_adaptive_api.py` | Adaptation inside one session through the API (five decisions, one session, all stored with their facts and as events); decisions readable with the usual visibility; another tenant refused; nobody can ask for another learner; a course without competencies says so |
| `integration/test_reports_api.py` | Learner report from real evidence with every claim cited and numbers equal to the stored figures; the evidence drawer (previous and new mastery, the record's tenant, which claims cite it); an empty report is honest; a faithful model adds cited claims; outage and malformed answers leave the deterministic report with an honest status; a lying model has its invented ids, numbers, causes and uncited claims refused claim by claim and its summary replaced; the prompt fence; identical requests reuse the stored report and do not call the model again; no model call without findings; team reports for managers cover their team only, name stuck learners with evidence, and carry no raw activity; a manager cannot reach another team; L&D and organization reports are admin-only and differ; content effectiveness is calculated, worded as an association, and needs enough learners; tenant isolation of reports and evidence; stored reports are visible only within the remit; BI endpoints and analytics scoped; scheduled digests (create, run, list, isolation, due schedules, schedule only what you may ask for); the embed token (scoped, refused as login and refresh, tampering, issuer deactivation, remit, script served, the unauthenticated legacy endpoint gone) |
| `unit/test_bkt.py` (extended) | A run of wrong, discounted retries never raises mastery. The integration tests found this: the learning step ignored the evidence weight, so twelve wrong answers on retries raised mastery to 0.48 and a "stuck" learner was reported as improving. Fixed in the formula and documented |

`tests/foundation/fakes.py::ScriptedAI` now also plays the reporting model (`faithful_report`, or a callable / fixed output / outage per test).

### Browser journey: adaptive engine and reporting

`scripts/e2e/reporting_journey.mjs` (fresh seeded database, `generate_demo_data.py` run once). A struggling learner opens the course player: the engine recommends a step and "Why am I seeing this?" shows her stored answers and mastery; she completes it and the recommendation changes (in the run: a gentler step, then a different format because the same mistake kept recurring, each stored with its rule and facts and recorded as events in her session). Her AI Learning Insights: every claim cites evidence, the drawer shows the stored records, a mastery-update record carries previous and new mastery, an invented id is not found; with the model down the page says the AI interpretation is missing and keeps the findings; the manager's report states counts equal to the cohort figures and shows no raw activity; the organization and L&D reports differ; a digest is generated and stored; the embeddable widget renders skill gaps from a scoped token; an embed token is refused as a login and as a refresh token; learners and managers are refused what they should be. **33 of 33.** The learner (25), learning-events (32), and admin-content (37 earlier in Phase 5, unchanged code paths since apart from the question editor) journeys were re-run as regression where they touch changed code.

**Not verified**: a real model answering reporting or grading prompts; video events; email delivery (there is none).

## Login check-in (Phase 11)

`services/api/tests/foundation/`:

| File | What it proves |
|---|---|
| `unit/test_checkin_rules.py` | Self-report scoring (reverse-keyed statements flipped, 0-100 scale, band edges, fewer than two answers is not scored, change since last time only "meaningful" past the threshold), validation of model-written statements (unknown constructs, questions, duplicates, too few), passage splitting and selection (unused passages first, different seeds differ), quiz scoring by lesson with unanswered questions named, and the observations (no cause is ever stated) |
| `integration/test_checkin_api.py` | A check-in written from the course's own text with every quote verified in it; no answers, explanations, quotes or keys in what the learner takes; scoring of quiz and self-report; the review after submitting; wrong ids refused and nothing scored; scored once; the event carries no self-report; each check-in tells the model what to avoid and the second differs; a new login replaces an unfinished one and a reload resumes it; skip; change since the previous check-in; no course, no material, model down, invented quotes and unusable statements all fail honestly with nothing invented; a coaching note with an invented number, diagnostic or causal wording is discarded and the report stands, and gets one correction attempt; a model outage at report time leaves the scores; nobody else (peer, manager, L&D, another tenant) can open, submit or skip it; the self-report never reaches a team report; the daily limit |
| `unit/test_ai_model_selection.py` | Each provider uses its own model, and thinking models get output headroom |

Browser journey `scripts/e2e/checkin_journey.mjs` (18 checks; against the running app and the real provider configured in `.env`, so it makes real model calls): sign in as a learner and land on the check-in, a model writes it, the quiz has no answers on the page, twelve self-report statements, the report matches the stored one, every question reviewable with its passage, scored once, a manager cannot open it, the next login gives different questions, skipping, and a manager's login is not interrupted. **18 of 18** on the last run.

Found by running against a real Gemini key rather than a double: the generic `AI_MODEL` was sent to Gemini; retired model names; "thinking" tokens truncating JSON; the API key appearing in request logs (now a header); a daily quota retried as if it were a rate limit; a failed generation left running because the failure handler read an expired object.
