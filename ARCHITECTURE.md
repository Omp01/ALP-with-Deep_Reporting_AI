# Architecture

## System Architecture

The Adaptive LMS is a modular microservice-oriented platform consisting of **5 application services**, **3 infrastructure components**, and **1 frontend application**.

```
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js 14)                        │
│         App Router · TypeScript · Tailwind · shadcn/ui           │
│              Learner | Manager | Admin | Embed                   │
└───────────────────────────────┬──────────────────────────────────┘
                                │ REST /api/v1/*
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     API SERVICE (FastAPI)                         │
│      Authentication · RBAC · Multi-tenancy · Request routing     │
│                   Single entry point for all clients             │
└─────────┬───────────────────────┬───────────────────┬────────────┘
          │ Internal HTTP         │ Internal HTTP      │ Internal HTTP
          ▼                       ▼                   ▼
┌─────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│ ADAPTIVE ENGINE │  │  REPORTING ENGINE   │  │ INGESTION SERVICE  │
│ Competency model│  │ Analytics engine   │  │ PDF/PPT/DOC parser │
│ Mastery calc    │  │ Evidence builder   │  │ Whisper transcribe │
│ Sequencing      │  │ Grounded AI/LLM   │  │ Competency extract │
│ Policy engine   │  │ Citation validator │  │ Assessment gen     │
│ Decision store  │  │ Risk detection     │  │ Embeddings         │
└────────┬────────┘  └─────────┬──────────┘  └─────────┬──────────┘
         │                     │                        │
         └─────────┬───────────┴────────────┬───────────┘
                   │                        │
          ┌────────┴────────┐     ┌─────────┴─────────┐
          │  BACKGROUND     │     │   INFRASTRUCTURE   │
          │  WORKERS        │     │                    │
          │  Event Worker   │     │  PostgreSQL+pgvec  │
          │  Risk Worker    │     │  Redis Streams     │
          │  Digest Worker  │     │  MinIO (S3)        │
          └─────────────────┘     └────────────────────┘
```

## Service Boundaries

### API Service (Port 8000)
- **Responsibility**: All external-facing operations. Authentication, authorization, tenant resolution, CRUD, event ingestion, request routing.
- **Does NOT**: Calculate mastery, generate insights, parse documents.
- **Communicates with**: All internal services via HTTP. PostgreSQL for data persistence. Redis for caching and stream publishing.

### Adaptive Engine (Port 8001)
- **Responsibility**: Competency modelling, mastery calculation, adaptive sequencing decisions.
- **Key principle**: Decisions are deterministic and explainable. Every decision is stored with its reason and mastery state.
- **Communicates with**: PostgreSQL (reads events, writes competency state + decisions).

### Reporting Engine (Port 8002)
- **Responsibility**: Deterministic analytics, evidence building, LLM insight generation, citation validation, risk scoring, digest generation.
- **Key principle**: Consumes learning events directly — never calls Adaptive Engine internal functions. All AI claims must be traceable to evidence.
- **Communicates with**: PostgreSQL (reads events + competencies), AI Provider (LLM).

### Ingestion Service (Port 8003)
- **Responsibility**: Content file processing, text extraction, chunking, AI competency extraction, AI assessment generation, embedding generation.
- **Communicates with**: MinIO (file storage), PostgreSQL (content + competency records), AI Provider (content analysis).

### Background Workers
- **Event Worker**: Consumes learning events from Redis Streams → triggers competency updates.
- **Risk Worker**: Periodic scan of learner data → detects risk signals → updates risk scores.
- **Digest Worker**: Scheduled generation of narrative learning intelligence reports.

## Data Flow

### Learning Event Flow
```
Learner action → Frontend → POST /api/v1/events → API Service
                                                      │
                                                      ├─→ PostgreSQL (immutable insert)
                                                      └─→ Redis Stream "learning_events"
                                                              │
                                                              └─→ Event Worker
                                                                      │
                                                                      └─→ Adaptive Engine
                                                                              │
                                                                              ├─→ Update learner_competencies
                                                                              └─→ Create competency_evidence
```

### Adaptive Decision Flow
```
Learner requests next content → POST /api/v1/adaptive/next → API Service
                                                                  │
                                                                  └─→ Adaptive Engine
                                                                          │
                                                                          ├─→ Read learner_competencies
                                                                          ├─→ Apply sequencing policy
                                                                          ├─→ Store adaptive_decision
                                                                          └─→ Return recommendation
```

### Reporting Flow
```
User requests insight → POST /api/v1/insights/generate → API Service
                                                              │
                                                              └─→ Reporting Engine
                                                                      │
                                                                      ├─→ Analytics Calculator (deterministic)
                                                                      ├─→ Evidence Builder (select relevant events)
                                                                      ├─→ LLM (reason over facts, return structured JSON)
                                                                      ├─→ Citation Validator (verify evidence IDs exist)
                                                                      └─→ Store validated insight
```

## Multi-Tenancy Strategy

- Every tenant-owned table includes `tenant_id` (FK → organizations).
- A `TenantMiddleware` resolves `tenant_id` from the JWT on every request.
- Repository base class automatically applies `WHERE tenant_id = :current` to all queries.
- Cross-tenant access is blocked at the database query level, not the frontend.
- Tests explicitly verify Organization A cannot access Organization B data.

## AI Architecture

- **Provider Abstraction**: `AIProvider` interface with `OpenAICompatibleProvider` implementation.
- **Embedding**: sentence-transformers `all-MiniLM-L6-v2` (384-dim) runs locally in the Ingestion Service.
- **LLM**: Used for competency extraction, assessment generation, and insight generation.
- **Grounding**: Backend computes deterministic analytics first. LLM reasons over pre-computed facts. Every claim must reference evidence IDs. Citation validator rejects unsupported claims.

## Scaling Strategy

- **Database**: PostgreSQL with proper indexes, pagination, aggregation queries.
- **Caching**: Redis for frequently accessed data (competency states, analytics).
- **Background Processing**: Redis Streams for async event processing.
- **Service Independence**: Each service can be scaled independently.
- **Evidence Bounding**: Evidence builder limits events to relevant scope — never loads entire database.

## Major Design Decisions

See [docs/decisions/](./docs/decisions/) for Architecture Decision Records.

| Decision | Rationale |
|----------|-----------|
| PostgreSQL + pgvector | Single database simplifies deployment; pgvector enables semantic search |
| Redis Streams (not Kafka) | Simpler operations for the current scale; migrable to Kafka if needed |
| Shared database | Reduces operational complexity vs. database-per-service |
| API as gateway | Single auth/tenant resolution point; internal services trust the gateway |
| Deterministic mastery formula | Transparent, explainable, configurable; avoids ML black box |
| Evidence-first AI | LLM never fabricates data; backend is source of truth |

## Trade-offs

| Trade-off | Accepted | Mitigated By |
|-----------|----------|-------------|
| Shared database limits service independence | Yes | Clean table ownership boundaries |
| API gateway is a single point of failure | Yes | Docker health checks + restart policies |
| In-process embeddings slow ingestion startup | Yes | Model cached after first load |
| Redis Streams lack Kafka durability | Yes | Events are persisted to PostgreSQL first |
