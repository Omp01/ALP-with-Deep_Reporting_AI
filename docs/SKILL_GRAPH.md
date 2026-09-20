# Skill Graph

The skill graph records which competencies must be learned before others. It is a fundamental input to the adaptive engine and the risk engine (Phases 5–6): "this learner is stuck on JOINs, and their prerequisite Filtering mastery is 0.35" is a prerequisite-blockage signal that only exists because the graph does.

## Competency

Table `competencies` (tenant-owned):

| Field | Meaning |
|---|---|
| `id`, `org_id` | identity and tenant |
| `code` | unique per tenant, e.g. `sql.joins` |
| `name`, `description` | display |
| `domain` | grouping such as `sql`, `python`; derived from the code prefix by migration 003 |
| `difficulty` | 0 (easiest) – 1 (hardest); DB-checked range |
| `taxonomy_level` | Bloom: remember, understand, apply, analyze, evaluate, create |
| `parent_id` | optional *hierarchy* (topic tree) — different from prerequisites |
| `metadata` (`competency_metadata` in code) | free-form JSON |

`difficulty` for rows that existed before migration 003 was derived from `taxonomy_level` (remember 0.10 … create 0.90). New competencies set it explicitly (default 0.5).

**Hierarchy vs prerequisites.** `parent_id` says "Window Functions is *part of* Advanced SQL". A prerequisite says "you should learn Aggregation *before* Window Functions". They answer different questions and both are kept.

## Edges

Table `competency_prerequisites`. A row `(competency_id, prerequisite_id, min_mastery)` means *competency requires prerequisite*, unblocked once the learner's mastery of the prerequisite reaches `min_mastery` (default 0.6).

```text
Python Basics ──▶ Functions ──▶ OOP
                     └──────▶ Async ──▶ Stream Processing
SQL Joins ──▶ Aggregation ──▶ Window Functions
    └──────▶ Indexing
```

### What the database guarantees

These hold even for raw SQL, imports and future code paths:

| Guarantee | Mechanism |
|---|---|
| An edge only connects competencies of **one tenant** | Composite foreign keys `(competency_id, org_id)` and `(prerequisite_id, org_id)` → `competencies(id, org_id)` |
| No self-loop | `CHECK competency_id <> prerequisite_id` |
| `min_mastery` is a probability | `CHECK 0 <= min_mastery <= 1` |
| No duplicate edge | primary key `(competency_id, prerequisite_id)` |
| Deleting a competency removes its edges | `ON DELETE CASCADE` |

### What the service guarantees

Acyclicity cannot be a table constraint, so `add_prerequisite` checks it before inserting. Adding "A requires B" is a cycle exactly when B already (transitively) requires A; the API returns **409** with the loop:

```json
{ "detail": { "code": "prerequisite_cycle",
              "message": "Adding this prerequisite would create a circular dependency",
              "cycle": ["<A>", "<B>", "<C>", "<A>"] } }
```

Other stable error codes: `self_prerequisite` (400), `duplicate_prerequisite` (409), `competency_not_found` (404 — identical for "missing" and "belongs to another tenant").

## Algorithms (`app/services/skill_graph.py`)

Pure functions over edge tuples, unit-tested without a database:

| Function | Purpose |
|---|---|
| `find_cycle_path(edges, c, p)` | Would adding *c requires p* create a loop? Returns the loop or `None` |
| `topological_levels(nodes, edges)` | Depth of each competency (longest path from a root); raises on a cycle |
| `transitive_prerequisites(edges, c)` | Every ancestor of `c` |
| `unmet_prerequisites(requirements, mastery_by_competency)` | Which direct prerequisites are below their threshold; no evidence counts as 0.0. **Used by the adaptive and risk engines from Phase 5** |

## API

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/competencies/graph` | Any signed-in user of the tenant |
| GET | `/api/v1/competencies/{id}/prerequisites?transitive=false` | Any signed-in user |
| POST | `/api/v1/competencies/{id}/prerequisites` `{prerequisite_id, min_mastery, rationale}` | L&D admin, org admin |
| DELETE | `/api/v1/competencies/{id}/prerequisites/{prerequisite_id}` | L&D admin, org admin |
| POST / PUT | `/api/v1/competencies`, `/api/v1/competencies/{id}` | L&D admin, org admin |

`GET /competencies/graph` returns nodes (with `level`, `prerequisite_ids`, `dependent_ids`), edges, `domains` and `max_level`, ready to render. It is registered *before* `/competencies/{id}` so the literal path is not captured as an id.

## UI

Admin → **Skill graph** (`/admin/skill-graph`): competencies grouped by depth, each showing what it requires and what it unlocks, with add/remove prerequisite. A rejected loop is explained in plain language using competency names.

## Demo data

`scripts/seed.py` defines the demo curriculum's graph as data (`SKILL_GRAPH`: 18 edges, depth 3) and inserts it through the same tables and constraints as any tenant's graph, then asserts acyclicity. Nothing downstream special-cases those competencies.
