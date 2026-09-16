# Architecture — Adaptive Learning Platform with Deep Reporting AI

## 1. System Overview

The Adaptive LMS is a modular, containerized B2B SaaS platform consisting of **5 application services**, **3 background workers**, **3 infrastructure components**, and **1 frontend application** — all orchestrated through Docker Compose with a single `docker compose up` command.

```
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js 14)                        │
│         App Router · TypeScript · Tailwind CSS                   │
│    Learner Dashboard | Manager Insights | Admin Hub | Login      │
└───────────────────────────────┬──────────────────────────────────┘
                                │ REST /api/v1/*  (HTTP, JWT)
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (FastAPI, Port 8000)              │
│    Authentication · 5-Role RBAC · Multi-Tenant Resolution        │
│          Event Publishing · Request Proxying · CRUD              │
└──────────┬─────────────────────┬──────────────────┬─────────────┘
           │ Internal HTTP       │ Internal HTTP     │ Internal HTTP
           ▼                     ▼                   ▼
┌─────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│ ADAPTIVE ENGINE │  │  REPORTING ENGINE   │  │    API INGESTION   │
│   Port 8001     │  │    Port 8002        │  │   (via API svc)    │
│                 │  │                    │  │                    │
│ Bayesian mastery│  │  Evidence builder  │  │ PDF/DOCX/TXT parse │
│ Policy engine   │  │  Citation validator│  │ Semantic chunker   │
│ Skill-gap detect│  │  Analytics calc    │  │ AI competency gen  │
│ Sequence history│  │  Digest generator  │  │ Assessment synth   │
└────────┬────────┘  └─────────┬──────────┘  └──────────┬─────────┘
         │                     │                         │
         └──────────┬──────────┴──────────────┬──────────┘
                    │                         │
         ┌──────────┴──────────┐   ┌──────────┴──────────┐
         │  BACKGROUND WORKERS │   │   INFRASTRUCTURE     │
         │  • Event Worker     │   │   • PostgreSQL 16    │
         │  • Risk Worker      │   │   • Redis 7 Streams  │
         │  • Digest Worker    │   │   • MinIO (S3)       │
         └─────────────────────┘   └─────────────────────┘
```

---

## 2. Service Boundaries and Responsibilities

### API Gateway (Port 8000)
**Owns:** Authentication, authorization, tenant resolution, CRUD operations, event publishing, request proxying to internal services.

**Does NOT own:** Mastery calculations, AI narrative generation, document parsing.

**Reason:** Centralizing auth/RBAC at the gateway means internal services can trust inbound requests without reimplementing security checks. This is the "trusted ambassador" pattern — complexity lives at the edge, not replicated in every service.

### Adaptive Engine (Port 8001)
**Owns:** Bayesian mastery calculations, pedagogical policy decisions, skill-gap detection, cohort bottleneck aggregation.

**Key design principle:** All decisions are **deterministic and explainable**. Every adaptive decision is persisted with the mastery state and policy rationale that produced it. This is intentional — black-box ML models were rejected because L&D stakeholders need to audit why a learner was sent to remediation.

**Mastery Formula:**
```
mastery = (0.40 × correctness_rate)
        + (0.15 × difficulty_weight)
        + (0.15 × recency_decay)
        - (0.15 × error_penalty)
        + (0.15 × consistency_bonus)
```

### Reporting Engine (Port 8002)
**Owns:** Evidence package construction, deterministic analytics, AI narrative synthesis, citation grounding validation, digest generation.

**Key design principle:** The AI layer is **evidence-first** — the backend computes all analytics deterministically first, builds a verified fact package indexed as `[E-1]`, `[E-2]`, etc., then the LLM reasons over those pre-verified facts. A citation validator rejects any AI claim that doesn't reference a valid evidence key. This eliminates hallucinations structurally rather than via prompt engineering.

### Background Workers
- **Event Worker:** Consumes Redis Stream `learning_events` via `XREADGROUP` consumer group `event_workers`, dispatches events to the Adaptive Engine for mastery updates. Uses `XACK` to prevent duplicate processing.
- **Risk Worker:** Periodically scans all active enrollments, evaluates 6 anomaly signals, and upserts risk records to `learner_risks` table.
- **Digest Worker:** Runs on a scheduled loop, generates leadership analytics narrative, and persists to `report_digests` table for distribution.

---

## 3. Data Flow Diagrams

### Learning Event → Mastery Update
```
Learner answer → POST /api/v1/events
                     │
                     ├─→ INSERT INTO learning_events (immutable audit)
                     └─→ XADD learning_events Redis Stream
                                 │
                                 └─→ Event Worker (XREADGROUP)
                                         │
                                         └─→ POST adaptive-engine/events
                                                 │
                                                 ├─→ Recalculate mastery score
                                                 ├─→ UPDATE learner_competencies
                                                 └─→ INSERT competency_history
```

### Adaptive Next-Step Decision
```
Learner requests next content → POST /api/v1/adaptive/next
                                       │
                                       └─→ Adaptive Engine
                                               │
                                               ├─→ SELECT learner_competencies (mastery, confidence, trend)
                                               ├─→ Apply pedagogical policy rules
                                               │     • advance: mastery ≥ 0.80, confidence ≥ 0.75
                                               │     • remediate: mastery < 0.50, 2+ consecutive fails
                                               │     • skip: mastery ≥ 0.95 (expert bypass)
                                               │     • change_modality: high error rate, same content type
                                               │     • revisit: declining trend detected
                                               ├─→ INSERT session_sequence_steps (audit trail)
                                               └─→ Return recommendation with rationale
```

### Evidence-Grounded AI Report
```
POST /api/v1/insights/generate { scope_type, scope_id, question }
       │
       └─→ Reporting Engine
               │
               ├─→ Evidence Builder
               │     • SELECT recent learning_events (scoped to org + scope_id)
               │     • SELECT learner_competencies (mastery states, trends)
               │     • SELECT learner_risks (anomaly signals)
               │     • Index each fact as [E-1], [E-2], ... [E-N]
               │
               ├─→ AI Narrative Synthesis
               │     • Prompt forces use of [E-#] keys in every claim
               │     • Deterministic fallback if AI key absent
               │
               ├─→ Citation Validator
               │     • Verify every [E-#] reference maps to real evidence
               │     • Apply hallucination score penalty for unsupported claims
               │
               ├─→ INSERT INTO ai_insights
               └─→ Return InsightResponse { claims, summary, citations }
```

---

## 4. Multi-Tenancy Design

**Strategy:** Logical multi-tenancy via `org_id` column on all tenant-owned tables.

**Enforcement chain:**
1. `JWT` embeds `org_id` on login.
2. `TenantMiddleware` extracts `org_id` from JWT on every request.
3. `TenantContext` dependency is injected into all routes that touch tenant data.
4. Every SQLAlchemy query includes `.where(Model.org_id == tenant_ctx.org_id)`.
5. Internal services receive `org_id` as an explicit query parameter, never inferred.

**Why not database-per-tenant?** At the current scale, schema-per-tenant or database-per-tenant would multiply operational overhead without proportional benefit. The `org_id`-column approach enables easy migration to physical separation if a specific tenant's load justifies it.

**Automated verification:** `test_auth_rbac.py::test_cross_tenant_isolation` explicitly verifies that Organization A's JWT cannot retrieve Organization B's data.

---

## 5. Key Design Decisions & Trade-offs

### Decision 1: API Gateway as Single Entry Point
**Rationale:** A single external-facing service centralizes auth, RBAC, and tenant resolution. Internal services operate in a trusted network — no redundant JWT verification in every microservice.

**Trade-off accepted:** The API Gateway becomes a single point of failure.

**Mitigation:** Docker health checks, `restart: unless-stopped` policy, and response-time monitoring via structured logging.

---

### Decision 2: PostgreSQL (Not MongoDB / DynamoDB)
**Rationale:** The data model has strong relational structure (courses → modules → content → competencies → enrollments → events). PostgreSQL enforces foreign key integrity, supports complex JOIN queries for analytics, and pgvector enables semantic search on content embeddings without a separate vector store.

**Trade-off accepted:** A shared database between microservices couples their schemas.

**Mitigation:** Clean table ownership — each service has designated tables it writes to. Cross-service data access is read-only and mediated through the API gateway, never direct cross-service SQL.

---

### Decision 3: Redis Streams (Not Apache Kafka)
**Rationale:** Kafka requires ZooKeeper/KRaft brokers, specific partition management, and significant DevOps overhead. Redis Streams offer the same consumer group semantics (`XREADGROUP`, `XACK`, `XPENDING`) with a fraction of the operational complexity. For the current event volume, Redis Streams are sufficient and are migratable to Kafka by swapping the publisher/consumer implementations.

**Trade-off accepted:** Redis Streams have weaker durability guarantees than Kafka's WAL-based log.

**Mitigation:** Learning events are written to PostgreSQL _before_ Redis publication. If Redis is lost, events are not lost — only real-time processing is delayed until the stream is restored.

---

### Decision 4: Deterministic Mastery Formula (Not ML Model)
**Rationale:** A multi-factor weighted Bayesian formula produces explainable, auditable mastery scores that L&D directors can understand and tune. A neural mastery model would be a black box — L&D professionals need to understand _why_ a learner was marked as at-risk or advanced.

**Trade-off accepted:** The formula is less adaptive than a trained ML model and cannot learn latent learner traits automatically.

**Mitigation:** The formula parameters are configurable constants. The architecture is designed so the mastery calculator can be swapped for a trained model if observational data accumulates.

---

### Decision 5: Evidence-First AI Reporting (Not Direct LLM Prompting)
**Rationale:** Direct LLM prompting over raw data hallucinate — statistics are invented, names are confused, trends are fabricated. By computing all analytics deterministically first and passing only verified, indexed facts to the LLM, hallucinations are structurally eliminated. The citation validator enforces this as a hard constraint.

**Trade-off accepted:** More engineering complexity than simple prompt engineering. Deterministic analytics must be maintained as schema changes occur.

**Mitigation:** The Evidence Builder is fully testable independently. The Citation Validator provides a hallucination score that can gate report publication.

---

### Decision 6: Shared Library (`shared/`)
**Rationale:** Event schemas, data contracts, and parsing utilities are used across multiple services. A shared library prevents drift and ensures all services speak the same data language (e.g., `LearningEventType` enum, `InsightResponse` contract).

**Trade-off accepted:** Changes to `shared/` require coordinated deployments across all dependent services.

**Mitigation:** Contracts use versioned Pydantic models. Breaking changes require updating the contract version, making breaking changes visible.

---

## 6. Scaling Strategy

| Component | Horizontal Scale Strategy |
|-----------|--------------------------|
| **API Gateway** | Stateless — multiple instances behind a load balancer |
| **Adaptive Engine** | Stateless per-request — scale as needed, decisions are persisted to DB |
| **Reporting Engine** | CPU-bound (analytics) — scale vertically or horizontally with DB connection pooling |
| **Workers** | Redis Streams support multiple consumer group members; add worker containers freely |
| **PostgreSQL** | Read replicas for analytics queries; pgBouncer for connection pooling |
| **MinIO** | Cluster mode with distributed erasure coding for production |

---

## 7. Architecture Decision Records

Full ADRs available in [`docs/decisions/`](./docs/decisions/):

- [ADR-001: PostgreSQL + pgvector](./docs/decisions/001-postgresql.md)
- [ADR-002: Redis Streams](./docs/decisions/002-redis-streams.md)
- [ADR-003: pgvector for Semantic Search](./docs/decisions/003-pgvector.md)
