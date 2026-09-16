# ADR-006: Row-Level Multi-Tenancy

## Status
Accepted

## Context
The platform serves multiple organizations (tenants). Each organization's data must be completely isolated. The multi-tenancy model must prevent data leakage without excessive infrastructure cost.

## Decision
Use row-level multi-tenancy: every tenant-owned table includes a `tenant_id` column. A base repository class enforces `WHERE tenant_id = :current` on every query.

## Alternatives Considered
- **Schema-per-tenant** — strong isolation, but complicates migrations and increases PostgreSQL connection overhead
- **Database-per-tenant** — strongest isolation, but significantly increases operational complexity
- **Application-level filtering** — simplest, but error-prone (easy to forget a filter)

## Why Selected
1. Single schema simplifies Alembic migrations (run once, applies to all tenants)
2. Repository base class makes the filter automatic, reducing human error
3. Sufficient isolation for a B2B SaaS product at this scale
4. PostgreSQL Row-Level Security (RLS) can be added as a defense-in-depth measure

## Trade-offs
- A single database bug could theoretically leak data across tenants
- Query performance may degrade without proper indexing on `tenant_id`
- All tenants share database resources (noisy neighbor risk)

## Future Migration Path
- Add PostgreSQL RLS policies as defense-in-depth
- Migrate to schema-per-tenant if tenant count grows significantly
- Migrate high-value tenants to dedicated databases if needed
