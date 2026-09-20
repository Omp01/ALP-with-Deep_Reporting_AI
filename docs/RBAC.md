# Role-Based Access Control

All permission checks happen **server-side**, in the API. The frontend hides links a role cannot use, but that is convenience only — nothing in the browser is trusted.

## The five roles

| Role | Sees / does | Scope |
|---|---|---|
| `learner` | Own learning data | Self |
| `manager` | Learning data and skill gaps of the teams they manage | Team |
| `ld_admin` | Learning programmes: content, courses, competencies, assessments, skill graph | Programme |
| `org_admin` | Organisation administration: users, **role assignment**, organisation-level reporting | Organisation |
| `super_admin` | Platform administration; may act in any tenant via `X-Tenant-ID` | Platform |

Roles **do not inherit**. A manager is not implicitly a learner; an org admin is not implicitly an L&D admin. Guards list the roles they accept explicitly. The one exception is `super_admin`, which passes every guard.

> Team scoping for managers ("the teams they manage") is enforced for learning events and sessions (Phase 4) and for competency states, skill gaps, evidence, cohort gaps and risk alerts (Phase 5), through one rule, `app/events/queries.py::visible_user_ids`: learner, themselves; manager, themselves and the members of teams they manage; L&D and org admins, the organisation. Outside that remit the answer is `404`. Analytics, reports and exports are still tenant-wide for managers until Phase 9. See `PRODUCT_AUDIT.md` R4.
>
> Written-answer review (`/api/v1/grading/*`) is for `ld_admin` and `org_admin` only; managers cannot grade answers.

## Data model

```text
roles(id, code UNIQUE, name, description, rank, is_system)          -- platform catalogue, seeded by migration 003
user_roles(user_id, role_id, org_id, assigned_by_id, assigned_at)   -- PK (user_id, role_id); org_id keeps it tenant-owned
users.role                                                          -- compatibility column: the user's PRIMARY role
```

`user_roles` is the authority. A user may hold several roles.

### Legacy spelling and the compatibility column

The original code stored `instructor` and `system_admin`, and 48 call sites compare against them. Rather than rewrite all of them at once:

| Canonical | Legacy (still in `users.role`) |
|---|---|
| `ld_admin` | `instructor` |
| `super_admin` | `system_admin` |

- Every check goes through `normalize_role()` (`app/core/rbac.py`), so `require_roles(["instructor"])` and `require_roles(["ld_admin"])` are identical.
- `users.role` holds the **primary** (most privileged) role in legacy spelling and is kept in step whenever roles are assigned through `PUT /users/{id}/roles`.
- API responses carry both: `role` (legacy, for the existing frontend) and `roles` (canonical list, most privileged first).
- **Fallback:** a user with no `user_roles` rows is treated as holding their `users.role`, so an un-migrated user never loses access.
- Later phases can migrate the remaining call sites to canonical names and drop the compatibility column.

## Where checks live

| Piece | File |
|---|---|
| Vocabulary, aliases, `has_any_role` (pure, unit-tested) | `services/api/app/core/rbac.py` |
| `effective_roles(user)`, `require_roles([...])`, tenant resolution | `services/api/app/api/deps.py` |
| Catalogue and assignment endpoints | `services/api/app/api/v1/roles.py` |

`require_roles` logs every denial as structured JSON (`authorization_denied`, with user, org, held and required roles) and returns a generic 403 that does not echo the role list.

## Role assignment rules

`PUT /api/v1/users/{user_id}/roles` with `{"roles": ["manager", "learner"]}` replaces the user's role set. Enforced server-side:

1. Only `org_admin` (and `super_admin`) may change roles.
2. Only `super_admin` may grant, revoke, or modify `super_admin`.
3. Nobody may change **their own** roles (no self-escalation, no self-lockout).
4. A user always keeps at least one role.
5. The target must be in the caller's tenant; otherwise 404.
6. Both spellings are accepted; unknown roles are a 400.
7. Every change writes an audit-log entry with the before and after sets.

## Endpoints

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/roles` | Any signed-in user |
| GET | `/api/v1/users/{id}/roles` | The user themself; manager, L&D admin, org admin |
| PUT | `/api/v1/users/{id}/roles` | Org admin, super admin |
| GET | `/api/v1/auth/me` | Any signed-in user (returns `role` and `roles`) |

## Tests

`tests/foundation/unit/test_rbac.py` (vocabulary, aliases, non-inheritance, super-admin bypass) and `tests/foundation/integration/test_roles_api.py` (assignment rules, immediate effect on guarded routes, legacy fallback, forged-claim rejection in `test_tenant_isolation.py`).
