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

1. **Explainable Competency Modelling** — Mastery comes from graded answers only, through one deterministic soft-evidence Bayesian Knowledge Tracing update. Written answers are graded by an AI agent that produces a _signal_ (never a mastery figure), checked against the answer and reviewed by a person when it is not trustworthy. Every figure has an audit chain you can open ("Why is this 68%?") and recompute. See [docs/COMPETENCY_ENGINE.md](./docs/COMPETENCY_ENGINE.md) and [docs/GRADING_AGENT.md](./docs/GRADING_AGENT.md).
2. **Evidence-Based Adaptation with "Why this?"** — The next step (continue, remediate, easier, harder, change format, revisit, skip ahead, assess) is decided by documented rules over stored evidence and the skill graph, saved with its facts, and explained to the learner from those facts. See [docs/ADAPTIVE_ENGINE.md](./docs/ADAPTIVE_ENGINE.md).
   **Login check-in** — every learner login opens an AI-written quiz on their own course material (each question verified against the material) and a short self-report; both are scored in code and produce a report with the source passage of every question. The self-report is private to the learner. See [docs/CHECKIN.md](./docs/CHECKIN.md).
3. **Explained Early Warning** — Documented rules over stored evidence and activity (persistent low mastery, declining trend, repeated failed attempts, retries, long time on task, inactivity, prerequisite gaps). Every reason cites the real figures; too little evidence is reported as such, not as risk.
4. **Evidence-Grounded AI Reporting** — Four distinct reports (learner, manager, L&D, organization) built from an evidence package. Every claim cites stored records that open in an evidence drawer; a claim with an invented id, a number the evidence does not contain, or a causal statement is refused and listed. Digests, an embeddable widget and BI endpoints use the same backend. See [docs/REPORTING_AI.md](./docs/REPORTING_AI.md).
5. **Interactive Video Learning with Anti-Skipping Checkpoints & AI Flash Cards** — Continuous mapping of video playback to timestamped transcripts. Periodically pauses for AI-generated flash-card comprehension checks strictly grounded in watched content. Anti-skipping seek guard intercepts forward scrubbing past incomplete checkpoints and clamps playback to the missed milestone. Persistent learner progress in PostgreSQL.

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

| Feature                        | Description                                                                                                                                                                                                                                                                                                 |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Multi-Tenancy**              | `org_id` scoped at database query level — zero cross-tenant data leaks                                                                                                                                                                                                                                      |
| **5-Role RBAC**                | `learner`, `instructor`, `manager`, `org_admin`, `super_admin` with route guards                                                                                                                                                                                                                            |
| **Content Ingestion**          | Upload PDF/DOCX/PPTX/TXT/MD/audio/video or add a YouTube link → validation → extraction → chunking → AI analysis (objectives, competencies, source-quoted questions) → **admin review** → publish. Local-first AI (Ollama), no fake fallbacks. See [docs/CONTENT_INGESTION.md](./docs/CONTENT_INGESTION.md) |
| **Learning Events & Sessions** | Append-only event store (enforced by the database), real learning sessions, 20 event types, per-answer evidence, server-recorded facts a browser cannot forge, idempotent ingestion, outbox delivery to Redis. See [docs/EVENT_MODEL.md](./docs/EVENT_MODEL.md)                                             |
| **Bayesian Mastery Model**     | Multi-factor weighted formula with correctness, difficulty, recency, errors, consistency                                                                                                                                                                                                                    |
| **Adaptive Sequencing**        | Deterministic pedagogical policies: remediate, advance, skip, change_modality, revisit                                                                                                                                                                                                                      |
| **6-Signal Risk Engine**       | Autonomous anomaly scanning with severity tiers: `low`, `medium`, `high`, `critical`                                                                                                                                                                                                                        |
| **Grounded AI Insights**       | Evidence-first — AI reasons over verified facts with mandatory `[E-#]` citations                                                                                                                                                                                                                            |
| **Proactive Digests**          | Scheduled weekly leadership digest dispatched to managers and executives                                                                                                                                                                                                                                    |
| **BI Export**                  | Streaming CSV & JSON endpoints for events, competencies, and risk signals                                                                                                                                                                                                                                   |
| **Embeddable Widget**          | Zero-config `<iframe>` embed card for enterprise portals and intranets                                                                                                                                                                                                                                      |
| **Automated Tests**            | **80/80 tests passing** — multi-tenancy, RBAC, adaptive, risks, reporting                                                                                                                                                                                                                                   |

---

## Tech Stack

| Layer                   | Technology                                                          |
| ----------------------- | ------------------------------------------------------------------- |
| **Frontend**            | Next.js 14 App Router · TypeScript · Tailwind CSS · Recharts        |
| **API Gateway**         | Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 async            |
| **Database**            | PostgreSQL 16 + pgvector · Alembic migrations                       |
| **Cache / Streams**     | Redis 7 · Redis Streams (XADD/XREADGROUP/XACK)                      |
| **Object Storage**      | MinIO (S3-compatible)                                               |
| **AI Provider**         | Abstracted `AIProvider` interface (OpenAI-compatible, any endpoint) |
| **Document Processing** | PyMuPDF · python-docx · python-pptx · sentence-transformers         |
| **Testing**             | Pytest 9 · pytest-asyncio · httpx                                   |
| **Containerization**    | Docker 24 · Docker Compose v2                                       |

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

## Running Manually (Without Docker)

You can run the frontend and API manually on your local machine, but the system still requires **PostgreSQL** and **Redis** to be running. You can launch just the infrastructure via Docker, then run the services natively.

### 1. Start Infrastructure

```bash
docker compose up -d postgres redis minio
```

### 2. Start Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
# Frontend is at http://localhost:3000
```

### 3. Start API Gateway (FastAPI)

```bash
cd services/api

# Set PYTHONPATH so Python can locate both 'app' and the root 'shared' modules
# On PowerShell:
$env:PYTHONPATH=".;..\..\shared;."
# On CMD:
set PYTHONPATH=.;..\..\shared;.
# On Bash/Linux/Mac:
export PYTHONPATH=.:../../shared:.

python -m uvicorn app.main:app --reload --port 8000
# API Swagger is at http://localhost:8000/docs
```

---

## Demo Credentials

All demo users share the password: **`Password123!`**

| Persona            | Role        | Email                     | What to Explore                                                                                         |
| ------------------ | ----------- | ------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Arthur Admin**   | `org_admin` | `admin@acme.com`          | Content Library (add, review, publish), BI Export Hub, Embeddable Widget                                |
| **Marcus Manager** | `manager`   | `marcus.manager@acme.com` | Cohort Skill Gaps, Early Warning Alerts, Scheduled Digest                                               |
| **Alice Learner**  | `learner`   | `alice.learner@acme.com`  | High mastery from correct answers, improving trend, the "Why?" evidence chain                           |
| **Bob Learner**    | `learner`   | `bob.learner@acme.com`    | Course content completed but weak mastery (completion is not comprehension), skill gaps, explained risk |
| **Carol Learner**  | `learner`   | `carol.learner@acme.com`  | Strong start then a run of wrong answers: declining trend                                               |
| **Dan Learner**    | `learner`   | `dan.learner@acme.com`    | Few answers, two weeks of inactivity                                                                    |

The learners' history is **synthetic**: `python scripts/generate_demo_data.py` writes answers (labelled `seed_history`) and the competency engine derives mastery, trend, gaps and risk from them. No mastery number is typed in.

> **Quick Demo Login:** Click any persona card on the `/login` page to sign in instantly without typing credentials.

---

## Foundation, Learning Experience & Migrations (Phases 1-2)

```powershell
# Infrastructure
docker compose up -d postgres redis minio

# Apply migrations (from the repository root)
$env:DATABASE_URL_SYNC = "postgresql://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"
python -m alembic -c database/alembic.ini upgrade head

# Seed demo data (idempotent; also assigns roles and the skill graph)
python scripts/seed.py

# Synthetic learner history, run through the real competency engine (Phase 5)
python scripts/generate_demo_data.py

# Run the foundation tests (builds its own throwaway database; needs only postgres)
cd services\api
python -m pytest tests\foundation
```

Restart the API after migrating so it loads the new models (`alembic upgrade head` now applies revisions 003 and 004). See [docs/LEARNING_EXPERIENCE.md](./docs/LEARNING_EXPERIENCE.md), [docs/TESTING.md](./docs/TESTING.md) (including the real-browser journey in `scripts/e2e/`), [docs/RBAC.md](./docs/RBAC.md), [docs/SKILL_GRAPH.md](./docs/SKILL_GRAPH.md) and [docs/CONTENT_MODEL.md](./docs/CONTENT_MODEL.md).

> **Note:** the test-count badge and "80/80" figures elsewhere in this README predate Phase 1 and are inaccurate; see `docs/TESTING.md`.

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
│       └── admin/              # Executive hub, content library / add-content / review, BI export
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

| Document                                                                 | Description                                       |
| ------------------------------------------------------------------------ | ------------------------------------------------- |
| [ARCHITECTURE.md](./ARCHITECTURE.md)                                     | System architecture, design decisions, trade-offs |
| [docs/API.md](./docs/API.md)                                             | Complete endpoint reference (11 API modules)      |
| [docs/DEMO_SCRIPT.md](./docs/DEMO_SCRIPT.md)                             | 3–5 minute screen-demo walkthrough                |
| [docs/TESTING.md](./docs/TESTING.md)                                     | Automated test strategy and verification          |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)                               | Deployment guide and production hardening         |
| [docs/DATA_MODEL.md](./docs/DATA_MODEL.md)                               | All 25 domain entities and schema diagrams        |
| [docs/EVENT_MODEL.md](./docs/EVENT_MODEL.md)                             | 12 canonical learning event types                 |
| [docs/ADAPTIVE_ENGINE.md](./docs/ADAPTIVE_ENGINE.md)                     | Bayesian mastery formula and sequencing policies  |
| [docs/REPORTING_AI.md](./docs/REPORTING_AI.md)                           | Evidence builder, citation validator, grounding   |
| [docs/CONTENT_INGESTION.md](./docs/CONTENT_INGESTION.md)                 | Document parsing and semantic chunking            |
| [docs/MULTI_TENANCY.md](./docs/MULTI_TENANCY.md)                         | Multi-tenancy strategy and tenant isolation       |
| [docs/SECURITY.md](./docs/SECURITY.md)                                   | Security architecture and RBAC design             |
| [docs/CODE_MAP.md](./docs/CODE_MAP.md)                                   | Requirements → code file traceability matrix      |
| [docs/REQUIREMENTS_TRACEABILITY.md](./docs/REQUIREMENTS_TRACEABILITY.md) | All requirements implementation status            |

---

## Known Limitations

| Limitation                                                 | Notes                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **An AI provider must be configured for content analysis** | `AI_PROVIDER=ollama` (free, local) or an external provider; see [docs/AI_PROVIDER.md](./docs/AI_PROVIDER.md). With none configured, ingestion says so and content can still be authored by hand; nothing is invented. (Reporting AI, Phase 7, is separate.)                                                                                |
| **Transcription is optional**                              | Uploaded audio/video is transcribed only if `faster-whisper` is installed; otherwise the admin pastes a transcript. YouTube uses the video's own captions. Nothing is ever faked. See [docs/ZERO_COST_MODE.md](./docs/ZERO_COST_MODE.md)                                                                                                   |
| **Embeddings are optional**                                | Set `AI_EMBEDDING_MODEL` (e.g. Ollama `nomic-embed-text`) to enable the stage. Vectors are stored with their model name; nothing retrieves by them until the reporting AI (Phase 7).                                                                                                                                                       |
| **No real email delivery**                                 | The digest worker generates and stores digests but does not send emails (SMTP not configured). Recipients are logged to PostgreSQL only.                                                                                                                                                                                                   |
| **Competency parameters are defaults, not fitted**         | The mastery update uses documented, standard starting values (`MASTERY_*` in `.env.example`); they have not been tuned on real learner data. Grading quality on a real model has not been measured. See [docs/COMPETENCY_ENGINE.md](./docs/COMPETENCY_ENGINE.md) section 9 and [docs/GRADING_AGENT.md](./docs/GRADING_AGENT.md) section 7. |
| **Adaptive sequencing still uses the earlier rules**       | `/adaptive/next` still hard-codes some inputs and returns the first content item of a module; it is rebuilt in Phase 6. Mastery, gaps and risk are already on the new engine.                                                                                                                                                              |
| **In-memory adaptive decisions**                           | The adaptive engine currently holds open sessions in memory. Restarting the container resets in-flight session state (no crash recovery).                                                                                                                                                                                                  |
| **Single-region deployment**                               | The architecture supports multi-region via read replicas but requires manual DNS and connection string configuration.                                                                                                                                                                                                                      |

---

## License

Proprietary — internal use only. © 2026 Adaptive LMS Engineering.
