# Security Specification & Threat Model

> **Adaptive LMS with Deep Reporting AI**  
> Comprehensive Reference for Authentication, Authorization, Cryptography, Input Sanitization, and Compliance.

---

## 1. Cryptography & Credentials

### Password Hashing
- **Algorithm:** Direct `bcrypt` with dynamic salt generation (`bcrypt.gensalt()`).
- **Truncation Mitigation:** Passwords are truncated at 72 UTF-8 bytes to adhere to bcrypt's underlying Blowfish cipher boundary, preventing silent truncation bugs or denial-of-service via abnormally large password payloads.
- **Salt Rounds:** Standard cost factor 12.

### JSON Web Tokens (JWT)
- **Algorithm:** `HS256` (HMAC using SHA-256) with configurable secret key loaded exclusively from environment variables (`JWT_SECRET`).
- **Token Claims:**
  - `sub`: User UUID identifier.
  - `org_id`: Tenant UUID identifier.
  - `role`: Canonical role string.
  - `email`: User email address.
  - `iat`: Issued-at UTC timestamp.
  - `exp`: Expiration UTC timestamp (default: 60 minutes).
- **Validation:** Strict rejection of expired tokens, missing subject identifiers, or tampered signatures.

---

## 2. Role-Based Access Control (RBAC) Architecture

- **Dependency Injection Enforcement:** All protected routes utilize FastAPI dependencies ([deps.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/deps.py)):
  ```python
  @router.get("/users")
  async def list_tenant_users(
      current_user: User = Depends(require_roles(["org_admin", "instructor", "manager"]))
  ):
      ...
  ```
- **Principle of Least Privilege:** Standard learners are restricted from directory traversal, administrative endpoints, and grading data.
- **Enumeration Defense:** In multi-tenant environments, unauthorized attempts to view or modify an entity belonging to another tenant return `404 Not Found` rather than `403 Forbidden` to prevent adversarial resource discovery.

---

## 3. Compliance & Audit Logging

- **Table:** `audit_logs`
- **Fields Logged:**
  - `id`: UUIDv4
  - `org_id`: Tenant UUID
  - `user_id`: Actor UUID (or NULL for unauthenticated attempts)
  - `action`: Canonical action string (e.g. `AUTH_LOGIN_SUCCESS`, `AUTH_LOGOUT`)
  - `resource_type`: Entity affected (`USER`, `COURSE`, `ORGANIZATION`)
  - `resource_id`: Target entity ID
  - `changes`: JSONB diff of prior vs updated states
  - `ip_address`: Remote client IP
  - `created_at`: Immutable UTC timestamp
- **Tamper Resistance:** Audit log entries cannot be modified or updated through the API; only appended.

---

## 4. Input Validation & Defenses

- **Pydantic Schema Validation:** All request payloads are strictly validated against Pydantic models with type checking, field length boundaries, and regex sanitation.
- **SQL Injection Prevention:** 100% of database interactions are executed via SQLAlchemy 2.0 parameterized queries and ORM abstractions. Zero raw string concatenation in SQL statements.
- **CORS Configuration:** Configured in [main.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/main.py) to explicitly restrict origins to authorized application domains, with strict method and header whitelisting.
- **Request Tracking:** Every HTTP request is assigned a unique `X-Request-ID` UUID in middleware, echoed in response headers and logged in structured JSON output for distributed tracing.

---

## 5. Object storage (hardened in Phase 3)

The bundled S3-compatible service (`services/s3-storage`) previously accepted **any** request without authentication and joined the object key straight onto a filesystem path, so a `..` in a key could read or write outside the bucket.

Now:

- every request except health checks needs `Authorization: Bearer <STORAGE_TOKEN>` (falls back to `MINIO_ROOT_PASSWORD`); the service refuses to start with no token, and there is no anonymous mode. The API client sends the token on every call;
- bucket names must match `^[a-z0-9][a-z0-9.-]{1,62}$`; object keys `^[A-Za-z0-9._\-/]+$` with no empty, `.` or `..` segments, and the resolved path must stay inside the bucket directory;
- objects are capped at `MAX_OBJECT_MB` (default 200; `413` beyond it); listings are XML-escaped.

Covered by `services/s3-storage/tests/test_storage_security.py` (21 tests, including raw-ASGI traversal attempts, since HTTP clients normalise `..` before sending). **A container built before Phase 3 still has the old code: rebuild it** (`docker compose up -d --build minio`). The compose file now publishes the storage ports on `127.0.0.1` only (they were on all interfaces); keep it that way, and do not expose port 9000 beyond the host.

## 6. Uploads and untrusted content (Phase 3)

Closes audit findings R8 (no upload validation) and R9 (no prompt-injection handling), as far as a software control can:

| Threat | Control |
|---|---|
| Executable or script uploaded under a document extension | Extension allow-list **and** magic-byte match; otherwise `content_mismatch` |
| Zip bombs / huge Office files | Entry-count and uncompressed-size limits before parsing; body read with a hard cap; `MAX_UPLOAD_SIZE_MB` |
| Path traversal / odd characters in filenames | Sanitised name; the storage key is `{org_id}/{job_id}/{safe_name}`, never the raw filename |
| Cross-tenant write | The target module is loaded with the caller's `org_id`; a foreign module is `404` and nothing is stored |
| Legacy binary Office files parsed as text | Refused (`.doc`, `.ppt`) with an actionable message |
| SSRF through "add a link" | Only YouTube URLs are accepted; only `youtube.com` hosts are contacted; caption URLs must be `https` on a YouTube host. No arbitrary URL is fetched |
| Prompt injection in documents or captions | Fenced with a per-call nonce, delimiter look-alikes neutralised, schema-validated output, every generated question checked against the source text, and human approval before publish (see `docs/CONTENT_INGESTION.md` §7) |
| Model output rendered as HTML | The review UI renders it as text; there is no `dangerouslySetInnerHTML` on generated content |
| Content changing after review | Analysis is keyed by content hash; re-analysis keeps decided questions and is an explicit action |

Residual risks, stated plainly: a prompt-injected model can still produce a misleading *summary or objective* that reads plausibly (grounding checks apply to questions, not to prose), and a document can truthfully contain wrong information. Both are what the mandatory review step is for. Uploaded files are not virus-scanned. There is still **no rate limiting** on the API (audit R9's other half), so an authenticated administrator can queue many jobs; the background runner processes two at a time.

Audit entries are written for `CONTENT_INGEST_STARTED`, `CONTENT_TRANSCRIPT_SET`, `CONTENT_PUBLISHED`, `CONTENT_UNPUBLISHED` and `CONTENT_DELETED`.

## 7. Learning events and sessions (Phase 4)

Events are the evidence every later phase reasons on, so their integrity is a security property.

| Threat | Control |
|---|---|
| A learner writes evidence about themselves (a correct answer, a completion, a grade) | The browser endpoint accepts only interaction events; graded answers, completions, results, submissions, grades and decisions are recorded by server code and refused with `403 server_only_event`, for administrators too. The browser cannot post them by any route (tested for ten types, and in a real browser) |
| A client names another tenant's course, content, question, attempt, assignment or session | Every reference is loaded with the caller's `org_id`; anything else is `404`, indistinguishable from a missing id. Course, module and competency are derived from the item, never taken from the request. An attempt must be the caller's own and still open |
| The tenant or learner is supplied in the body | Both come from the token; body fields with those names are ignored |
| Events are edited or erased afterwards (by a bug, an admin tool, a cascade) | A database trigger rejects UPDATE and DELETE on `learning_events`; foreign keys that could cascade or null them were replaced by restrictions; the composite key `(session_id, org_id, user_id)` prevents an event pointing at another learner's or tenant's session |
| Duplicate submission, retry storms, one tenant suppressing another's events (audit R7) | Idempotency keys unique per tenant, prefixed per learner, inserted with `ON CONFLICT DO NOTHING`; the client no longer chooses the primary key |
| Forged or absurd timestamps | A browser time is used only if within 2 minutes ahead and 24 hours behind, else the server's; `received_at` is always the server's clock, so the two can be compared |
| Inflated durations and response times | Response times are capped at the attempt's real elapsed time and labelled `client_clamped`; an idle session is closed at its last activity; progress time credit was already clamped (Phase 2) |
| Payload smuggling / oversized payloads | Per-type schemas (learner payloads reject unknown fields), an 8 KB limit, batches of at most 50 |
| A learner or manager reading events beyond their remit | Visibility is scoped in the query: learners, themselves; managers, the members of teams they manage; admins, the tenant. A user outside the remit returns an empty list |
| Lost delivery when Redis is down (audit A5) | Outbox written with the event; retried with backoff; nothing is swallowed |

Residual risks: the database owner can still `TRUNCATE` the table (row triggers do not fire on it); `learning_events` is unencrypted at rest like the rest of the database; there is no rate limiting on `POST /events` beyond the batch size, so an authenticated learner can generate large volumes of *interaction* events about themselves (they cannot forge evidence, but they can add noise); a manager's team scoping applies to events and sessions only (audit R4 is otherwise open).

## 8. Competency engine and grading (Phase 5)

| Threat | Control |
|---|---|
| A learner argues their way to a grade (prompt injection in a written answer) | The answer is fenced with a per-request marker and defanged; the model is told it is data; the output is **checked**: the skill must be the one asked about and the evidence quote must occur in the answer, otherwise the answer goes to a person. Answer length is capped. Residual: a model that misjudges a plausible answer is not detectable by these checks |
| The model is down, slow, or returns garbage | The answer waits for a reviewer; nothing is invented; timeouts are bounded. The learner sees "waiting for a reviewer" and the attempt is not passed |
| Editing mastery or its history after the fact | `evidence_records`, `competency_state_updates` and `grading_results` are append-only (database trigger). `verify` recomputes the chain from evidence and reports any state that does not match |
| Concurrent or repeated evidence corrupting a chain | Row lock per learner and competency; evidence unique per source event and competency |
| Evidence attached to another tenant's competency | The engine rejects it; composite foreign keys `(competency_id, org_id)` make it impossible from raw SQL |
| A learner reading another learner's mastery, or the answer key | Visibility scoped in the query (self; manager: team; admin: tenant); out of remit is `404`. The expected answer of a written question is never sent to learners |
| Reviewing or grading by the wrong person | The queue and review endpoints need L&D or org admin; a review is only allowed for an answer that is waiting (`409` otherwise), in the caller's tenant (`404` otherwise) |
| Managers seeing risk for learners outside their team | Risk list, history and resolve are scoped by `visible_user_ids` |

Residual risks: there is no rate limiting on submit, so a learner can trigger many grading calls (each written answer is a model call: cost and latency); accepted grades cannot be corrected except by adding new evidence; the database owner can still `TRUNCATE` the audit tables (as with events); learner answers are sent to the configured model provider, so a hosted provider means learner text leaves the deployment (use a local model to keep it inside).

## 9. Adaptive engine, reporting and embedding (Phases 6-9)

| Threat | Control |
|---|---|
| A reporting model invents evidence, numbers or causes | Citation validation on every claim: ids must exist in this report's package, belong to the report's tenant, scope and period; numbers must match the cited records; causal wording and causal claims are refused. Refused claims are shown with reasons |
| Prompt injection through data that reaches the reporting prompt (learner quotes, titles) | The package is fenced with a per-request marker and defanged; the output is validated as above. Deterministic findings are always shown, so a steered model cannot remove a finding |
| A manager reading learners outside their team, or raw personal activity | Team packages are built only from the manager's team and contain no event or session records; individual reports use the same visibility rule as everything else (`404` outside the remit) |
| Reading another tenant's report or evidence | Reports and evidence are loaded by `org_id`; evidence opens only through its report and is checked against the tenant again; a foreign org gets `404` |
| An unauthenticated read of a learner's competencies (the earlier `/embed/report` took a learner id and an org id from the URL) | Removed. The widget uses embed tokens: signed, expiring, one report and one scope; **refused as a login and as a refresh token**; every request re-checks that the issuer exists, is active and may still see the scope |
| Asking the adaptive engine on behalf of someone else | `/adaptive/next` has no learner parameter: the caller is who is decided for; decisions are read with the same visibility rule |
| Schedules used to reach beyond one's remit | A schedule can only be created for a report the creator may ask for, and runs with the owner's current permissions; an inactive owner disables it |
| Model cost and latency | No model call without findings; identical evidence reuses the stored report; reporting calls have a timeout and failure leaves the deterministic report |

Residual risks: reports are stored with the evidence package (including learner-identifying records for the audience that asked), so they are as sensitive as the data they cite; no rate limiting on report generation (each uncached AI report is a model call); the model provider receives the compact package (a hosted provider means learner-related text leaves the deployment: use a local model to avoid it); embed tokens cannot be revoked individually before they expire (deactivating the issuer revokes all of theirs).
