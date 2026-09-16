# ADR-005: Event-Driven Reporting (Decoupled from Adaptive Engine)

## Status
Accepted

## Context
The assignment requires the reporting layer to be architecturally independent from the adaptive engine. Reports must consume learning events without depending on adaptive engine internals.

## Decision
The Reporting Engine reads learning events and competency states directly from PostgreSQL. It never calls Adaptive Engine internal functions or APIs.

## Alternatives Considered
- **Reporting Engine calls Adaptive Engine API** — creates coupling; if adaptive engine changes its competency model, reporting breaks
- **Shared library between engines** — code sharing creates implicit coupling
- **CQRS with separate read model** — good separation, but adds complexity for the initial version

## Why Selected
1. Clean architectural boundary: Reporting Engine is a consumer of data, not a collaborator
2. Learning events and competency states are shared via the database (well-defined schema)
3. Reporting can evolve independently (different analytics, different insight formats)
4. If the Adaptive Engine's mastery formula changes, historical competency states remain accurate

## Trade-offs
- Some data duplication (both services query similar tables)
- Reporting Engine must understand the competency state schema

## Future Migration Path
- Introduce CQRS with materialized views if query patterns diverge significantly
