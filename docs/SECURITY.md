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
