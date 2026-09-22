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
**Owns:** Bayesian Knowledge Tracing (BKT) mastery calculations, pedagogical policy decisions, skill-gap detection, cohort bottleneck aggregation.

**Key design principle:** All decisions are **deterministic, explainable, and grounded in Bayesian probability theory**. Every adaptive decision is persisted with the mastery state and policy rationale that produced it.

**Bayesian Knowledge Tracing (BKT) Model (Corbett & Anderson):**
The platform models knowledge acquisition over discrete practice opportunities using standard 4-parameter BKT:
- $P(L_0)$: Prior probability of knowing the skill before any practice (default: `0.10`)
- $P(T)$: Transition / learning probability of acquiring the skill after an opportunity (default: `0.15`)
- $P(G)$: Guess probability of answering correctly despite not knowing the skill (default: `0.20`)
- $P(S)$: Slip probability of answering incorrectly despite knowing the skill (default: `0.05`)

**Posterior Update Equations:**
1. *Observation Update (Given correctness $obs \in \{0, 1\}$):*
$$P(L_t \mid \text{obs}=1) = \frac{P(L_{t-1}) \cdot (1 - P(S))}{P(L_{t-1}) \cdot (1 - P(S)) + (1 - P(L_{t-1})) \cdot P(G)}$$
$$P(L_t \mid \text{obs}=0) = \frac{P(L_{t-1}) \cdot P(S)}{P(L_{t-1}) \cdot P(S) + (1 - P(L_{t-1})) \cdot (1 - P(G))}$$

2. *Transition to Next Step:*
$$P(L_{t+1}) = P(L_t \mid \text{obs}) + (1 - P(L_t \mid \text{obs})) \cdot P(T)$$

### Reporting Engine (Port 8002)
**Owns:** Evidence package construction, deterministic analytics, AI narrative synthesis, citation grounding validation, digest generation.

**Key design principle:** The AI layer is **evidence-first and multi-provider**:
1. **Evidence Builder:** Pre-computes all analytics deterministically, indexing atomic facts as `[E-1]`, `[E-2]`, ... `[E-N]` with exact timestamps, metrics, and student IDs.
2. **Hybrid Multi-Provider LLM Integration:**
   - Google Gemini (`gemini-1.5-flash` / `gemini-1.5-pro`)
   - Groq (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`)
   - OpenAI (`gpt-4o` / `gpt-4o-mini`)
   - Ollama (Local LLMs via HTTP)
   - **Deterministic Grounded Fallback:** When API keys are not supplied or network is offline, the deterministic engine generates structured executive insights with 100% compliant citation grounding.
3. **Citation Validator:** Validates every generated statement against the evidence index, calculating citation coverage and hallucination penalty scores.

### Background Workers
- **Event Worker (`alms-event-worker`):** Consumes Redis Stream `learning_events` via `XREADGROUP` consumer group `event_workers`, dispatches events to the Adaptive Engine for mastery updates. Uses `XACK` to prevent duplicate processing.
- **Risk Worker (`alms-risk-worker`):** Periodically scans all active enrollments, evaluates 6 anomaly signals (stalling, failure spikes, regression, low velocity, consecutive quiz fails, disengagement), and upserts risk records to `learner_risks` table.
- **Digest Worker (`alms-digest-worker`):** Runs on a scheduled loop, generates leadership analytics narrative, and persists to `report_digests` table for distribution.

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
                                                 ├─→ Update BKT Bayesian probability
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
               ├─→ Multi-Provider AI Narrative Synthesis (Gemini / Groq / OpenAI / Ollama / Fallback)
               │     • Prompt forces use of [E-#] keys in every claim
               │     • Offline deterministic fallback if external AI unavailable
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

**Automated verification:** `test_auth_rbac.py::test_cross_tenant_isolation` explicitly verifies that Organization A's JWT cannot retrieve Organization B's data.

---

## 5. Key Design Decisions & Trade-offs

### Decision 1: API Gateway as Single Entry Point
**Rationale:** A single external-facing service centralizes auth, RBAC, and tenant resolution. Internal services operate in a trusted network — no redundant JWT verification in every microservice.
**Trade-off accepted:** The API Gateway is a central dependency.
**Mitigation:** Docker health checks, `restart: unless-stopped` policy, and response-time monitoring via structured logging.

---

### Decision 2: PostgreSQL with pgvector (Unified Operational + Vector Store)
**Rationale:** The data model has strong relational structure (courses → modules → content → competencies → enrollments → events). PostgreSQL enforces foreign key integrity, supports complex JOIN queries for analytics, and pgvector enables semantic search on content embeddings without a separate vector database.
**Trade-off accepted:** Single operational datastore.
**Mitigation:** Clean table ownership per service, connection pooling via SQLAlchemy asyncpg.

---

### Decision 3: Redis Streams for Idempotent Telemetry
**Rationale:** Redis Streams offer lightweight consumer group semantics (`XREADGROUP`, `XACK`, `XPENDING`) without the heavy ops footprint of Kafka.
**Trade-off accepted:** Memory-based stream storage.
**Mitigation:** Learning events are committed to PostgreSQL *before* Redis stream publication.

---

### Decision 4: Bayesian Knowledge Tracing (Corbett & Anderson)
**Rationale:** BKT is mathematically sound, explainable, and gives precise probabilistic mastery values $P(L_t)$ that update dynamically per attempt.
**Trade-off accepted:** Fixed slip and guess assumptions.
**Mitigation:** Parameters are parameterized per competency and difficulty tier.

---

### Decision 5: Evidence-First Grounded AI Reporting
**Rationale:** Standard LLM zero-shot analysis suffers from hallucinated numbers and dates. By building indexed evidence facts (`[E-1]`, `[E-2]`) first, the LLM is constrained to verifiable citations.
**Trade-off accepted:** Upfront computation of evidence facts.
**Mitigation:** Evidence builder queries are optimized and cached per session.

---

### Decision 6: Hybrid Multi-Provider LLM with Zero-Dependency Fallback
**Rationale:** Enables using Google Gemini, Groq, OpenAI, or Ollama seamlessly with a unified interface while guaranteeing full offline functionality and zero runtime errors if API keys are not provided.
**Trade-off accepted:** Deterministic fallback has template-based narrative structure compared to LLM prose.
**Mitigation:** Deterministic narratives include complete analytical summaries and exact `[E-#]` citation grounding.

---

### Decision 7: Checkpoint-Based Anti-Skipping Video Verification
**Rationale:** Standard video completion tracking relies on the final playback timestamp or raw percent, allowing users to scrub to the end without absorbing the material. Checkpoint-based validation evaluates contiguous playback against discrete, timestamped milestones.
**Enforcement:** Forward seeks that bypass incomplete checkpoints are strictly intercepted on both client and server; playback is locked to the first uncompleted checkpoint until the flash-card check is answered. Backward seeking is unrestricted.
**Anti-Cheating:** Correct option IDs and explanations are omitted from API payloads until the learner registers an answer. Progress is persisted in `learner_video_checkpoints` so page refreshes cannot bypass checks.

---

## 6. Scaling Strategy

| Component | Horizontal Scale Strategy |
|-----------|--------------------------|
| **API Gateway** | Stateless — multiple instances behind a load balancer |
| **Adaptive Engine** | Stateless per-request — decisions persisted to PostgreSQL |
| **Reporting Engine** | CPU-bound analytics — scale horizontally with DB connection pooling |
| **Workers** | Redis Streams support multiple consumer group members; add worker instances |
| **PostgreSQL** | Read replicas for reporting queries; pgBouncer connection pooling |
| **MinIO** | S3-compatible cluster mode with distributed erasure coding |

---

## 7. Architecture Decision Records

Full ADRs available in [`docs/decisions/`](./docs/decisions/):

- [ADR-001: PostgreSQL + pgvector](./docs/decisions/001-postgresql.md)
- [ADR-002: Redis Streams](./docs/decisions/002-redis-streams.md)
- [ADR-003: pgvector for Semantic Search](./docs/decisions/003-pgvector.md)
- [ADR-004: Bayesian Knowledge Tracing Engine](./docs/decisions/004-bkt-mastery.md)

