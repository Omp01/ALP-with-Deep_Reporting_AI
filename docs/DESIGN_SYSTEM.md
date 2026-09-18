# Design System & Application Shell

**Phase:** 1
**Scope:** `frontend/app/globals.css`, `frontend/components/ui/`, `frontend/components/shell/`,
`frontend/hooks/`, `frontend/lib/`

This document describes the visual and structural foundation every subsequent phase builds on. It is
the reference for "which component do I use" and "why is it built this way".

---

## 1. Why this phase existed

The Phase 0 audit found a frontend of eight bespoke pages sharing two components. `components/ui/`,
`features/`, `hooks/`, and `services/` were five-line `export {}` placeholders. Every button, card,
and badge was hand-written inline, so spacing and colour drifted page to page. A complete token set
was declared in `globals.css` and then bypassed by raw `slate-*` utilities, which meant the palette
could not actually retheme anything.

Three defects were fixed here because everything downstream depends on them:

| Defect | Consequence | Fix |
| :--- | :--- | :--- |
| `lib/api-client.ts` imported by zero files; 37 hardcoded `http://localhost:8000` URLs | App undeployable anywhere but a dev laptop | Client hardened and made the only HTTP path; `NEXT_PUBLIC_API_URL` now actually read |
| `@theme inline` mapped `--font-sans` to `--font-geist-sans`, which does not exist | Inter never applied; app rendered in the browser default font | Mapped to `--font-inter`, the variable `next/font` actually injects |
| Sidebar rendered the learner menu to every role | An administrator's primary navigation led with learner surfaces | Per-role IA resolved from `lib/navigation.ts` |

---

## 2. Token layer

`frontend/app/globals.css` defines tokens twice, deliberately:

1. **`:root`** — raw custom properties, readable from hand-written CSS.
2. **`@theme inline`** — the Tailwind v4 bridge that turns each token into a real utility class.

Layer 2 is what makes the system enforceable. Without it, `bg-surface` and `text-fg-muted` simply do
not exist as classes, so a developer reaching for a token has no choice but to fall back to
`bg-slate-50`. That is exactly how the previous build ended up with a design system nothing used.

### Available token utilities

| Group | Tokens | Example utilities |
| :--- | :--- | :--- |
| Surfaces | `background`, `surface`, `surface-elevated`, `surface-sunken` | `bg-surface`, `bg-surface-elevated` |
| Brand | `primary`, `primary-hover`, `primary-active`, `primary-light`, `primary-border`, `primary-foreground` | `bg-primary`, `text-primary`, `border-primary-border` |
| Semantic | `success`, `warning`, `danger`, `info` — each with `-light` and `-border` | `bg-danger-light`, `text-success`, `border-warning-border` |
| Text | `fg`, `fg-muted`, `fg-subtle`, `fg-inverse` | `text-fg`, `text-fg-muted` |
| Lines | `border`, `border-strong` | `border-border`, `hover:border-border-strong` |
| Sidebar | `sidebar-bg`, `sidebar-surface`, `sidebar-text`, `sidebar-text-active`, `sidebar-text-subtle`, `sidebar-accent`, `sidebar-hover` | `bg-sidebar-bg`, `text-sidebar-text` |
| Charts | `chart-1` … `chart-6` | `text-chart-2`, `bg-chart-3/12` |
| Mastery | `mastery-high`, `mastery-medium`, `mastery-low`, `mastery-critical` | `bg-mastery-high` |
| Radius | `sm`, `md`, `lg`, `xl`, `2xl` | `rounded-lg` |
| Elevation | `xs`, `sm`, `md`, `lg` | `shadow-xs`, `shadow-md` |

**Rule:** new code uses a token utility. `bg-slate-50` in a new file is a review comment. The one
sanctioned exception is the modal scrim (`bg-slate-900/40`), which is a fixed overlay colour rather
than a themeable surface.

### Motion

Four keyframes (`fadeIn`, `slideInRight`, `slideUpIn`, `pulse-subtle`) plus a `shimmer` used by
skeletons. All of them are disabled under `@media (prefers-reduced-motion: reduce)` by a global
override — animation must never be a prerequisite for understanding a state change.

---

## 3. Component library

One component per file in `frontend/components/ui/`, re-exported from `index.ts`. Import from the
barrel: `import { Button, Card, EmptyState } from "@/components/ui"`.

### Rules for this directory

- **Presentational only.** A primitive never fetches, and never computes a business metric. It
  receives what it displays. Deriving a completion percentage inside a card is how a UI starts
  disagreeing with its own API (§45).
- **Tokens, not palette classes.**
- **Keyboard-operable, with the ARIA roles its pattern requires.**

### Inventory

| Component | File | Notes |
| :--- | :--- | :--- |
| `Button` | `button.tsx` | 6 variants, 4 sizes. `loading` keeps the label mounted so the button does not resize mid-request. |
| `Card` + `CardHeader/Title/Description/Content/Footer/Toolbar` | `card.tsx` | 4 variants; `interactive` for whole-card targets. |
| `Badge`, `StatusDot` | `badge.tsx` | 7 variants. `StatusDot` carries an `sr-only` label or is decorative. |
| `Input`, `Textarea`, `Label`, `Field`, `FieldError`, `FieldHint` | `input.tsx` | `Field` wires `aria-describedby` between control and message automatically. |
| `Select` | `select.tsx` | Native `<select>` — correct by construction, uses the platform picker on mobile. |
| `Skeleton`, `SkeletonText/Stat/Card/Table`, `LoadingRegion` | `skeleton.tsx` | Shapes approximate their content to avoid layout jump on load. |
| `Spinner`, `SpinnerBlock` | `spinner.tsx` | For *actions*; prefer a skeleton for page loads. |
| `Progress`, `MasteryBar`, `masteryBand`, `masteryLabel` | `progress.tsx` | `MasteryBar` takes a 0–1 probability — the engine's native scale — so a caller cannot pass an already-scaled number. |
| `Avatar` | `avatar.tsx` | Deterministic colour from the name; same person, same colour everywhere. |
| `Alert` | `alert.tsx` | Persistent inline condition. |
| `EmptyState`, `InsufficientEvidenceState` | `empty-state.tsx` | See §5. |
| `ErrorState`, `InlineError` | `error-state.tsx` | See §5. |
| `Tabs` + `TabsList/Trigger/Content` | `tabs.tsx` | Full WAI-ARIA tabs pattern with roving focus. |
| `Breadcrumb` | `breadcrumb.tsx` | Matters most in the player and admin editors. |
| `Dialog`, `ConfirmDialog` | `dialog.tsx` | Focus trap, focus restore, Escape, scroll lock. `drawer` variant backs the evidence panel. |
| `DropdownMenu` + `DropdownItem/Label/Separator` | `dropdown-menu.tsx` | Arrow-key navigation, outside-click and Escape dismissal. |
| `Tooltip` | `tooltip.tsx` | Opens on hover **and focus**. Never the only source of information. |
| `ToastProvider`, `useToastContext` | `toast.tsx` | Mounted once at the root. Errors do not auto-dismiss. |
| `Stat`, `StatGrid` | `stat.tsx` | `trend` requires `trendPeriod` — an arrow without a period means nothing. |
| `Table` primitives | `table.tsx` | `TableContainer` scrolls the table inside its own box, never the page body. |
| `Separator` | `separator.tsx` | Optional centred label. |

---

## 4. Application shell

`frontend/components/shell/`.

```tsx
export default function TeamPage() {
  return (
    <AppShell roles={["manager"]}>
      <PageHeader title="My Team" description="…" />
      …
    </AppShell>
  );
}
```

| Component | Responsibility |
| :--- | :--- |
| `AppShell` | The frame: guard, sidebar, topbar, `<main>` landmark, skip link, responsive behaviour. `bleed` drops the padded container for full-bleed screens like the course player. |
| `Sidebar` | Renders the role's IA from `lib/navigation.ts`. `overlay` variant (default) is a drawer below `lg` and a sticky rail above; `static` sits in flow for legacy pages. |
| `Topbar` | Menu toggle, tenant name **from the session**, profile dropdown, sign-out. |
| `AuthGuard` | Redirects unauthenticated users to `/login`; shows an explicit message to a signed-in user lacking the role. |
| `PageHeader`, `SectionHeader` | The single `h1` treatment and action placement for every page. |

### `min-w-0` on the content column

`AppShell` sets `min-w-0` on the flex child holding the main column. Without it, a wide table inside
the content well stretches the flex item and scrolls the entire page sideways. This is the single
most common cause of horizontal overflow in a sidebar layout.

### Navigation is not a security boundary

`AuthGuard` and `navigationForRole` decide **what is offered**, never **what is permitted**. Every
request is re-authorised server-side by `require_roles()` and the tenant dependency in
`services/api/app/api/deps.py`. The guard exists so a user is not shown a screen whose requests will
all return 403.

---

## 5. The four data states

Every data-backed view must handle four states. `useApi` returns all four, and there is a component
for each.

| State | Component | Rule |
| :--- | :--- | :--- |
| Loading | `Skeleton*` / `SpinnerBlock` | Never a blank screen (§65). |
| Error | `ErrorState` / `InlineError` | Shows `ApiError.userMessage`, never a raw stack trace (§51). Retry is hidden for 403, where retrying cannot help. |
| Empty | `EmptyState` | States the situation and offers the one action that resolves it. **Never** filled with placeholder numbers to look busy (§64/§75). |
| Populated | the view itself | — |

`InsufficientEvidenceState` deserves special mention. "Not enough learning activity to generate an
insight yet" is the correct product behaviour when the evidence package is thin — the alternative is
generating an insight anyway, which the rubric treats as a critical failure. It is a component rather
than ad-hoc copy so that every AI surface refuses identically.

---

## 6. Data access

### `lib/api-client.ts`

The single HTTP entry point. Do not call `fetch` from a component — a raw fetch skips the timeout,
the error normalisation, and the 401 path, and reintroduces the hardcoded host.

- Base URL from `NEXT_PUBLIC_API_URL`.
- Per-request timeout via `AbortController`, chained to a caller-supplied signal.
- Normalises all three FastAPI error shapes — `{"error": {...}}`, `{"detail": "string"}`, and
  Pydantic's `{"detail": [...]}` array — into one `ApiError`.
- `ApiError` exposes `isUnauthorized` / `isForbidden` / `isNotFound` / `isNetworkError` /
  `isServerError` and a `userMessage` that is safe to display.
- A 401 clears the session once; routing is left to the UI, which reacts to the session change.

### `hooks/use-api.ts`

`useApi(fetcher, { deps, enabled, isEmpty })` returns `{ data, loading, refreshing, error, isEmpty,
refetch, setData }`.

The `loading` / `refreshing` split is what stops a page flashing back to skeletons on every refetch:
first load shows skeletons; subsequent loads keep current data on screen. In-flight requests abort on
unmount and are superseded by newer ones, so a slow response can never overwrite a fresher one.

`useMutation` is the write-side equivalent; it returns `undefined` on failure rather than throwing,
so a click handler needs no `try`/`catch`.

### `hooks/use-auth.ts`

Replaces the per-page `useEffect` + `localStorage.getItem` + `JSON.parse` block. Listens for session
changes in this tab and, via the `storage` event, in others — so signing out in one tab signs out the
rest.

`ready` matters: storage is unavailable during the server render, so a component that redirects on
`!user` without checking `ready` bounces every authenticated user to `/login` on first paint.

**Storage trade-off:** the token lives in `localStorage` because that is what the existing login flow
writes. It is XSS-exposed. Moving to an httpOnly refresh cookie is a known limitation, recorded here
rather than silently accepted. All reads are confined to `lib/auth.ts`.

---

## 7. Information architecture

`lib/navigation.ts` is the single definition of what each role can reach. Sidebar and mobile nav both
render from it, so navigation cannot drift between surfaces.

Each item carries a `status`:

- **`ready`** — the route exists and is rendered.
- **`planned`** — the target route is declared but not built, and is **not rendered**. A nav link
  that 404s is a broken flow, and a greyed-out "coming soon" row advertises a feature the product
  does not have. Each planned item records the phase that delivers it; that phase flips the flag.

`navigationForRole(role, includePlanned)` resolves the set. Passing `includePlanned = true` shows the
full target IA — useful in development, off in the product.

### Current state

| Role | Ready now | Planned |
| :--- | :--- | :--- |
| Learner | Home, Continue Learning, AI Insights | My Learning, Explore, Learning Paths (P3); Assessments (P4); Competencies (P6); Progress (P9); Profile (P14) |
| Manager | Dashboard, Reports | My Team, Learners, Team Progress, Competencies, At-Risk (P9); AI Insights (P11) |
| Admin | Dashboard | Analytics (P9); Reporting AI (P11); Courses, Content, Assessments, Competencies, Users (P12); Settings (P14) |

Roles get their **own** IA — not the learner menu with rows appended.

---

## 8. Accessibility baseline

- Skip link as the first tab stop on every shell page.
- `<main id="main-content">` landmark; `<nav aria-label="Primary">`.
- Focus-visible ring from a single global rule, using the primary token.
- `Dialog` traps focus, restores it to the trigger on close, closes on Escape, locks body scroll.
- `Tabs` implements roving focus (arrows, Home, End).
- `DropdownMenu` supports arrow navigation and returns focus to its trigger on Escape.
- `Tooltip` opens on focus as well as hover.
- Toasts announce via `aria-live="polite"`; errors use `role="alert"`.
- `prefers-reduced-motion` neutralises all animation globally.
- Form messages are linked to their control through `aria-describedby` by `Field`.

Not yet done: a full contrast audit and a screen-reader pass over the migrated pages. Both are
Phase 14.

---

## 9. Backwards compatibility

The eight pre-existing pages compose `<Navbar />` and `<Sidebar />` themselves. Rather than rewrite
all eight in this phase, `components/Navbar.tsx` and `components/Sidebar.tsx` are now thin deprecated
wrappers delegating to `<Topbar>` and `<Sidebar variant="static">`.

Those pages therefore inherit the Phase 1 fixes — per-role navigation, session-derived tenant name,
keyboard-operable profile menu — without being touched. They are migrated to `<AppShell>` as Phases
3, 4, 9, 11, and 12 rebuild them, at which point both wrappers are deleted.

---

## 10. What this phase did **not** do

Stated plainly so the boundary is unambiguous:

- No page was migrated to `AppShell`; the eight existing pages still hold their own `fetch` calls.
- The 37 hardcoded `localhost:8000` URLs still exist inside those pages. The client they should use
  is now correct and ready; the replacement happens as each page is rebuilt.
- No backend, database, or API change.
- No new data is displayed, and no metric changed meaning.
