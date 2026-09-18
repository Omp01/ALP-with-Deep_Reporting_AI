# Handoff — Where to Pick Up

**Last updated:** 2026-09-18
**State:** Phase 0 complete. Phase 1 substantially complete, with a short punch list below.
**Build status:** `npm run build` passes — 9 routes prerender. `npx tsc --noEmit` clean.

Read this first, then `docs/PRODUCT_TRANSFORMATION_AUDIT.md` (what the codebase is) and
`docs/DESIGN_SYSTEM.md` (what Phase 1 built and the rules for using it).

---

## 1. Prerequisites before you run anything

None of these are in git — `.gitignore` excludes them by design, and they do not exist on a fresh
clone. The stack cannot start without the first one.

```powershell
# From the repository root
Copy-Item .env.example .env          # docker compose config fails without this
cd frontend; npm install; cd ..      # node_modules is absent
docker compose build
docker compose up
```

Then seed:

```powershell
python scripts/seed.py
python scripts/generate_demo_data.py
```

**Known `.env` gap:** `.env.example` documents `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL` /
`AI_BASE_URL`, but `services/reporting-engine/app/ai/llm_provider.py` reads `GEMINI_API_KEY`,
`GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `OLLAMA_BASE_URL` — none of which appear
in `.env.example`. Set one of the latter or the Reporting AI silently falls back to offline
generation with no error. Reconciling this is Phase 10 work.

### Demo accounts

Password for all seeded users: `Password123!`

| Email | Role | Org |
| :--- | :--- | :--- |
| `alice.learner@acme.com` | learner | Acme |
| `marcus.manager@acme.com` | manager | Acme |
| `admin@acme.com` | org_admin | Acme |
| `elena.learner@technova.com` | learner | TechNova |
| `sysadmin@adaptivelms.io` | system_admin | cross-tenant |

Two orgs exist, which is what makes tenant isolation demonstrable.

---

## 2. What was completed

### Phase 0 — Audit → `docs/PRODUCT_TRANSFORMATION_AUDIT.md`

A 17-section audit of the working tree. The headline findings, because they shape every later phase:

- The codebase is **not** a fake-data prototype. There are no `const courses = [...]` arrays in the
  React pages; `mastery.py` is a real Corbett-Anderson BKT implementation; the evidence builder runs
  real SQL and carries real `source_id` UUIDs; all six reporting touchpoints exist and share one
  engine. **Preserve all of this.**
- What is missing is the **LMS itself**: no catalogue, no course detail page, no enrolment flow, no
  admin content CRUD, no quiz entity, no realtime, no content-level progress records.
- Corrections to the older `docs/CURRENT_IMPLEMENTATION_AUDIT.md`, which is stale: the stack is
  Next 16.3.5 / React 19.2.8 (not 14/18), and there are **42** test functions (not 80).

### Phase 1 — Design system, component library, app shell

| Area | Files |
| :--- | :--- |
| Tokens | `frontend/app/globals.css` — `:root` vars **plus** an `@theme inline` bridge so tokens exist as real utilities (`bg-surface`, `text-fg-muted`) |
| Primitives | `frontend/components/ui/` — 21 components + barrel `index.ts` |
| Shell | `frontend/components/shell/` — `AppShell`, `Sidebar`, `Topbar`, `AuthGuard`, `PageHeader` |
| Hooks | `frontend/hooks/` — `useAuth`, `useApi`, `useMutation`, `useToast`, `useMediaQuery`, `useIsMounted` |
| Data | `frontend/lib/api-client.ts` (hardened), `lib/auth.ts` (new), `lib/navigation.ts` (new), `lib/utils.ts` (extended) |
| App scaffolding | `app/layout.tsx`, `app/error.tsx`, `app/not-found.tsx`, `app/loading.tsx` |
| Docs | `docs/DESIGN_SYSTEM.md` |

Three latent defects were fixed along the way:

1. `@theme inline` mapped `--font-sans` to `--font-geist-sans`, which does not exist — Inter was
   never actually applied. Now points at `--font-inter`.
2. The sidebar rendered the **learner** menu to every role, so an administrator's primary navigation
   led with learner surfaces. Navigation now resolves per role from `lib/navigation.ts`.
3. The header fell back to a hardcoded `"Acme Corporation"` whenever the org name was missing —
   displaying one tenant's name to every other tenant. It now reads the session and renders nothing
   if absent.

`components/Navbar.tsx` and `components/Sidebar.tsx` are now thin **deprecated wrappers** delegating
to the new shell, so the eight pre-existing pages inherit these fixes without being rewritten.

---

## 3. Pick up here — Phase 1 punch list

Small and self-contained. Do this before starting Phase 2.

### 3.1 Finish the React Compiler lint fixes (in progress when work stopped)

Next 16 ships React Compiler lint rules. The new code has **8 errors** remaining; the other 38 are in
the eight legacy pages and disappear as those pages are migrated in Phases 3/4/9/11/12.

```powershell
cd frontend
npx eslint components/ui components/shell hooks lib
```

| File | Error | Fix |
| :--- | :--- | :--- |
| `hooks/use-api.ts` (×3) | `Cannot access refs during render` — `fetcherRef.current = fetcher` in the render body | Assign inside a `useEffect(() => { fetcherRef.current = fetcher; })` |
| `hooks/use-api.ts` (×1) | `setState synchronously within an effect` at the `if (!enabled)` branch | Derive instead: return `loading: enabled && internalLoading`; drop the `setLoading(false)` |
| `hooks/use-auth.ts` (×1) | same rule | Rewrite over `useSyncExternalStore`. **The store is already written** — use `subscribeToSession`, `getSessionSnapshot`, `getServerSessionSnapshot` in `lib/auth.ts` (they cache the parsed user against the raw string so snapshots stay identity-stable) |
| `components/ui/dialog.tsx`, `components/ui/toast.tsx` (×1 each) | the `useState(false)` + `useEffect(setMounted(true))` portal idiom | Replace with `useIsMounted()` from `hooks/use-is-mounted.ts` — **already written for this purpose, currently unused** |
| `components/ui/avatar.tsx` (2 warnings) | stale `eslint-disable` on the wrong line | Move the directive onto the `<img>` line, or configure `next.config.ts` `images.remotePatterns` and switch to `next/image` |

`useMediaQuery` has already been converted to `useSyncExternalStore` and is clean — use it as the
reference pattern for `useAuth`.

### 3.2 Not done in Phase 1 — deliberately

Stated so the boundary is unambiguous:

- **No page was migrated to `AppShell`.** The eight existing pages still hold their own `fetch` calls.
- **The 37 hardcoded `http://localhost:8000` URLs still exist** inside those pages. The client they
  should use is now correct and ready; replacement happens as each page is rebuilt.
- No backend, database, or API change. No new data displayed; no metric changed meaning.

---

## 4. Then: Phase 2 — Real LMS data model

**Do this first, before any schema work:** `database/migrations/versions/001_initial_schema.py` is 28
lines whose `upgrade()` body is `Base.metadata.create_all(bind=op.get_bind())`. That is not a
migration — it is `create_all` wearing an Alembic revision id, with no table DDL and no way to
express an incremental change. Phase 2 adds ~8 tables and alters ~4, so **replace revision 001 with
real autogenerated DDL and establish a working revision chain before adding anything**.

New tables to add (all additive — nothing existing is dropped, so every current endpoint keeps
working through the transition):

```text
quizzes, quiz_questions, quiz_options, quiz_attempts, question_responses
content_progress          -- authoritative per-learner × content-item completion
content_competencies      -- item- and question-level mapping (§23); today competencies
                          -- map only to courses and modules
adaptive_decisions        -- decision + reason + previous/new mastery + selected content (§26)
```

New nullable columns:

- `courses`: `thumbnail_url`, `instructor_id`, `category`, `difficulty`, `rating`, `duration_minutes`
  — a discovery page (§9/§10/§48) cannot be built on the current table
- `learning_events`: `content_id` FK — events currently reference only `course_id` and `module_id`,
  so content-level analytics ("where do learners drop off?") cannot be queried relationally

Then extend `scripts/seed.py`. It is already good — 5 real courses with genuine educational content,
real competencies, video/article/quiz/assignment per module — but each course has only 1–2 modules
and needs more depth, plus enrolments and thumbnails.

---

## 5. Full roadmap

`docs/PRODUCT_TRANSFORMATION_AUDIT.md` §17 carries the Phase 0→15 table with the key risk for each.
Summary of what remains:

| Phase | Deliverable |
| :--- | :--- |
| 2 | Migration chain; quiz/progress/decision/mapping tables; course presentation columns; expanded seed |
| 3 | `/explore`, `/courses/[id]`, enrolment flow, My Learning; search/filter/sort on `GET /courses` |
| 4 | `ContentRenderer` / `VideoPlayer` / `ArticleViewer` / `QuizRenderer` / `AssignmentRenderer`; prev/next; mobile curriculum |
| 5 | `content_id` on events; quiz/video/article/assignment event types; idempotency tests |
| 6 | Content- and question-level competency mapping; **derived** progress replacing the stored `progress_pct` float |
| 7 | `adaptive_decisions` audit table; "Why this?" answered from persisted records; error-type-weighted item selection |
| 8 | WebSocket/SSE — there is currently **zero** realtime anywhere in the repo |
| 9 | Learner/manager/admin analytics endpoints; risk detection on real signals |
| 10 | **Highest rubric weight.** Structured `{claim, evidence_ids}` insight schema; versioned `prompts/`; consolidate the Reporting AI onto `shared/schemas/ai_provider.py`; **reject** invalid citations rather than merely penalising them; verify scope ownership |
| 11 | Six reporting surfaces on the shared engine; evidence UI everywhere |
| 12 | Admin course/module/content/quiz/assignment CRUD UI — largest remaining UI build |
| 13 | Scheduled reports, JSON/CSV export, embed hardening (mostly exists) |
| 14 | Full UX pass: responsive, a11y, empty/loading/error states, navigation |
| 15 | Unit + integration tests across all services; `docs/DEMO_FLOW.md`; end-to-end run |

### Highest-value work if time is short

Ranked by rubric weight against current standing:

1. **Phase 10 citation rejection** (15% of the grade). Today `validate_grounded_citations()` returns
   `is_valid=False` and subtracts 0.30 from the score, but nothing blocks or regenerates the report,
   and scope ownership is never checked. The rubric treats unverifiable insights as a *critical
   failure*.
2. **Unit tests for `mastery.py` and `validator.py`** (10%). The rubric names these two modules
   explicitly. There are currently **zero** unit tests for either — all 42 tests are live-HTTP
   integration tests against `localhost:8000` requiring a seeded stack, with no `conftest.py`.
   `services/{adaptive-engine,reporting-engine,ingestion}/tests/` contain only `__init__.py`.
3. **Phases 3 + 4** (the LMS experience). This is what makes the product read as a learning platform
   rather than a dashboard demo.

---

## 6. Repository hygiene issues still open

| Issue | Note |
| :--- | :--- |
| `services/adaptive-engine/app/app/` and `app/app/app/` | Two complete recursive copies (114 KB), **still tracked in git** despite commit `5929c29` claiming their removal. Editing `mastery.py` leaves two stale copies behind. `git rm -r` them. |
| Three separate SQLAlchemy model definitions | `api/app/models/`, `adaptive-engine/.../tables.py`, `reporting-engine/.../tables.py` — schema drift risk as Phase 2 adds tables |
| Business logic in route handlers | Only 2 of 19 routers use the declared `app/services/` layer |
| No DELETE endpoints | Course/module/content CRUD is create/read/update only — blocks Phase 12 |
| `docs/CURRENT_IMPLEMENTATION_AUDIT.md` | Contains stale, incorrect claims. Superseded by `PRODUCT_TRANSFORMATION_AUDIT.md`; consider deleting it |

---

## 7. Conventions to follow

From `docs/DESIGN_SYSTEM.md`, repeated here because they are easy to violate:

- **Never call `fetch` from a component.** Use `apiClient` — a raw fetch skips the timeout, the error
  normalisation, and the 401 path, and reintroduces the hardcoded host.
- **Use token utilities** (`bg-surface`, `text-fg-muted`), never raw palette classes (`bg-slate-50`).
- **Primitives are presentational.** They never fetch and never compute a business metric.
- **Handle all four data states** — loading, error, empty, populated. `useApi` returns all four.
- **Never fake data to fill space.** An empty state says it is empty. When evidence is insufficient,
  `InsufficientEvidenceState` says so rather than generating an insight anyway.
- **Navigation is not a security boundary.** `AuthGuard` decides what is *offered*; the backend
  re-authorises every request.
- Adding a route means adding it to `lib/navigation.ts` and flipping its `status` to `ready`. Items
  marked `planned` are not rendered, because a nav link that 404s is a broken flow.
