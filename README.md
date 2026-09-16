# Adaptive Learning Platform with Deep Reporting AI

> A production-grade, containerized, multi-tenant B2B SaaS Adaptive Learning Management System (LMS) that models **actual learner understanding** — not just completion. Real-time Bayesian competency modelling, deterministic pedagogical sequencing, multi-signal early warning detection, and 100% grounded AI reporting with clickable evidence citations.

[![Backend Tests](https://img.shields.io/badge/Tests-80%2F80%20PASSED-brightgreen)](./docs/TESTING.md)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose%20Ready-blue)](./docker-compose.yml)
[![API Docs](https://img.shields.io/badge/API-Swagger%20UI-orange)](http://localhost:8000/docs)
[![License](https://img.shields.io/badge/License-Proprietary-red)](#)

---

## The Problem

Traditional LMSs track **completion — not comprehension**. A learner can click through 100% of a course while retaining 10% of the material. Managers receive shallow completion dashboards that don't reveal skill gaps, declining performance, or at-risk learners.

**This platform solves the comprehension gap by:**

1. **Live Bayesian Competency Modelling** — Multi-factor mastery scoring with correctness weighting, IRT difficulty calibration, recency decay, error penalty, and consistency bonuses.
2. **Real-Time Adaptive Sequencing** — Deterministic pedagogical policy engine that selects between `advance`, `remediate`, `skip`, `change_modality`, and `revisit` based on live competency state.
3. **Multi-Signal Early Warning** — Autonomous anomaly detection across six risk dimensions: declining mastery, consecutive failures, retry frequency, latency spikes, low assessment scores, and inactivity stagnation.
4. **Evidence-Grounded AI Reporting** — AI narratives backed by a verifiable telemetry fact package. Every claim is mapped to an `[E-#]` citation that links to a concrete database record.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js 14)                        │
│         App Router · TypeScript · Tailwind CSS                   │
│    Learner Dashboard | Manager Insights | Admin Hub | Login      │
└───────────────────────────────┬──────────────────────────────────┘
                                │ REST /api/v1/*  (HTTP, JWT)
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (FastAPI)                         │
│    Authentication · 5-Role RBAC · Multi-Tenant Resolution        │
│          Event Publishing · Request Proxying · CRUD              │
└──────────┬─────────────────────┬──────────────────┬─────────────┘
           │ Internal HTTP       │ Internal HTTP     │ Internal HTTP
           ▼                     ▼                   ▼
┌─────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│ ADAPTIVE ENGINE │  │  REPORTING ENGINE   │  │ INGESTION (API)    │
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

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full design decisions and trade-offs document.

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Tenancy** | `org_id` scoped at database query level — zero cross-tenant data leaks |
| **5-Role RBAC** | `learner`, `instructor`, `manager`, `org_admin`, `super_admin` with route guards |
| **Content Ingestion** | Upload PDF/DOCX/TXT → semantic chunking → S3 storage → knowledge extraction |
| **Learning Event Telemetry** | 12 canonical event types, immutable audit log, Redis Stream fan-out |
| **Bayesian Mastery Model** | Multi-factor weighted formula with correctness, difficulty, recency, errors, consistency |
| **Adaptive Sequencing** | Deterministic pedagogical policies: remediate, advance, skip, change_modality, revisit |
| **6-Signal Risk Engine** | Autonomous anomaly scanning with severity tiers: `low`, `medium`, `high`, `critical` |
| **Grounded AI Insights** | Evidence-first — AI reasons over verified facts with mandatory `[E-#]` citations |
| **Proactive Digests** | Scheduled weekly leadership digest dispatched to managers and executives |
| **BI Export** | Streaming CSV & JSON endpoints for events, competencies, and risk signals |
| **Embeddable Widget** | Zero-config `<iframe>` embed card for enterprise portals and intranets |
| **Automated Tests** | **80/80 tests passing** — multi-tenancy, RBAC, adaptive, risks, reporting |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 14 App Router · TypeScript · Tailwind CSS · Recharts |
| **API Gateway** | Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 async |
| **Database** | PostgreSQL 16 + pgvector · Alembic migrations |
| **Cache / Streams** | Redis 7 · Redis Streams (XADD/XREADGROUP/XACK) |
| **Object Storage** | MinIO (S3-compatible) |
| **AI Provider** | Abstracted `AIProvider` interface (OpenAI-compatible, any endpoint) |
| **Document Processing** | PyMuPDF · python-docx · python-pptx · sentence-transformers |
| **Testing** | Pytest 9 · pytest-asyncio · httpx |
| **Containerization** | Docker 24 · Docker Compose v2 |

---

## Quick Start (Single Command)

```bash
# 1. Clone
git clone <repository-url>
cd adaptive-lms

# 2. Configure environment (copy .env.example — the demo key is pre-configured)
cp .env.example .env

# 3. Launch all services, workers, and infrastructure
docker compose up --build

# 4. Wait for all services to become healthy (~60s on first run)
# Then open your browser to:
#   Frontend:      http://localhost:3000
#   API Swagger:   http://localhost:8000/docs
#   MinIO Console: http://localhost:9001 (user: minioadmin / pass: minioadmin)
```

> **Note:** The database is automatically initialized and seeded with demo data (2 organizations, 13 users, 4 learner archetypes, courses, competencies, and telemetry events) on first startup via the API container entrypoint.

---

## Demo Credentials

All demo users share the password: **`Password123!`**

| Persona | Role | Email | What to Explore |
|---------|------|-------|----------------|
| **Arthur Admin** | `org_admin` | `admin@acme.com` | Ingestion Studio, BI Export Hub, Embeddable Widget |
| **Marcus Manager** | `manager` | `marcus.manager@acme.com` | Cohort Skill Gaps, Early Warning Alerts, Scheduled Digest |
| **Alice Learner** | `learner` | `alice.learner@acme.com` | High mastery (88%), adaptive advancement, AI "Why?" citations |
| **Bob Learner** | `learner` | `bob.learner@acme.com` | Shallow mastery (38%), skill gap detection, remediation |
| **Carol Learner** | `learner` | `carol.learner@acme.com` | Declining trajectory, latency spikes, medium risk alert |
| **Dan Learner** | `learner` | `dan.learner@acme.com` | 14-day inactivity stagnation, critical dropout risk |

> **Quick Demo Login:** Click any persona card on the `/login` page to sign in instantly without typing credentials.

---

## Running Tests

```bash
# Full backend test suite (80 tests, runs inside the API container)
docker cp services/api/tests alms-api:/app/tests
docker exec alms-api pytest tests -v

# OR using docker compose exec after services are running:
docker compose exec api pytest tests -v
```

Expected output:
```
================================ 80 passed in 46.86s ==============================
```

---

## Project Structure

```
adaptive-lms/
├── docker-compose.yml          # Single-command deployment
├── .env.example                # All environment variable defaults
├── ARCHITECTURE.md             # Design decisions & trade-offs
├── README.md                   # This file
│
├── frontend/                   # Next.js 14 App Router frontend
│   └── app/
│       ├── login/              # Persona quick switcher
│       ├── learner/            # Learner dashboard, learning session, AI insights
│       ├── manager/            # Team performance, cohort reports, digests
│       └── admin/              # Executive hub, ingestion studio, BI export
│
├── services/
│   ├── api/                    # API Gateway (FastAPI, port 8000)
│   ├── adaptive-engine/        # Mastery modelling & sequencing (port 8001)
│   ├── reporting-engine/       # Evidence builder & AI insights (port 8002)
│   └── ingestion/              # Document parser stub
│
├── workers/
│   ├── event-worker/           # Redis Stream consumer → adaptive engine
│   ├── risk-worker/            # Periodic risk anomaly scanner
│   └── digest-worker/          # Scheduled leadership digest generator
│
├── shared/                     # Cross-service contracts, event schemas, parsers
├── database/                   # Alembic migrations (001_initial_schema)
├── scripts/                    # Seed data, demo data, health checks
├── tests/e2e/                  # Playwright E2E test specs
└── docs/                       # Full technical documentation suite
```

---

## API Documentation

Interactive Swagger UI: **[http://localhost:8000/docs](http://localhost:8000/docs)**

Full endpoint reference: **[docs/API.md](./docs/API.md)**

Key API modules:
- `POST /api/v1/auth/login` — JWT authentication
- `POST /api/v1/adaptive/next` — Real-time next-step recommendation
- `POST /api/v1/insights/generate` — Grounded AI narrative with `[E-#]` citations
- `GET /api/v1/risks` — Multi-signal at-risk learner dashboard
- `GET /api/v1/export/events` — BI streaming export (CSV or JSON)
- `GET /api/v1/embed/report` — Embeddable widget HTML card

---

## Documentation Suite

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System architecture, design decisions, trade-offs |
| [docs/API.md](./docs/API.md) | Complete endpoint reference (11 API modules) |
| [docs/DEMO_SCRIPT.md](./docs/DEMO_SCRIPT.md) | 3–5 minute screen-demo walkthrough |
| [docs/TESTING.md](./docs/TESTING.md) | Automated test strategy and verification |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Deployment guide and production hardening |
| [docs/DATA_MODEL.md](./docs/DATA_MODEL.md) | All 25 domain entities and schema diagrams |
| [docs/EVENT_MODEL.md](./docs/EVENT_MODEL.md) | 12 canonical learning event types |
| [docs/ADAPTIVE_ENGINE.md](./docs/ADAPTIVE_ENGINE.md) | Bayesian mastery formula and sequencing policies |
| [docs/REPORTING_AI.md](./docs/REPORTING_AI.md) | Evidence builder, citation validator, grounding |
| [docs/CONTENT_INGESTION.md](./docs/CONTENT_INGESTION.md) | Document parsing and semantic chunking |
| [docs/MULTI_TENANCY.md](./docs/MULTI_TENANCY.md) | Multi-tenancy strategy and tenant isolation |
| [docs/SECURITY.md](./docs/SECURITY.md) | Security architecture and RBAC design |
| [docs/CODE_MAP.md](./docs/CODE_MAP.md) | Requirements → code file traceability matrix |
| [docs/REQUIREMENTS_TRACEABILITY.md](./docs/REQUIREMENTS_TRACEABILITY.md) | All requirements implementation status |

---

## Known Limitations

| Limitation | Notes |
|------------|-------|
| **LLM provider requires API key** | Set `AI_API_KEY` in `.env`. The system uses a deterministic fallback if the key is absent — all grounded AI reports still run with pre-computed evidence (no OpenAI calls required for the demo). |
| **Whisper transcription is stubbed** | Audio/video file ingestion extracts placeholder text. Full Whisper integration requires `FFmpeg` and a GPU-enabled container. |
| **Embeddings use sentence-transformers** | Running `all-MiniLM-L6-v2` locally in the ingestion container. Cold start may take 15–30s on first container launch. |
| **No real email delivery** | The digest worker generates and stores digests but does not send emails (SMTP not configured). Recipients are logged to PostgreSQL only. |
| **In-memory adaptive decisions** | The adaptive engine currently holds open sessions in memory. Restarting the container resets in-flight session state (no crash recovery). |
| **Single-region deployment** | The architecture supports multi-region via read replicas but requires manual DNS and connection string configuration. |

---

## License

Proprietary — internal use only. © 2026 Adaptive LMS Engineering.
