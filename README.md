# Adaptive Learning Platform with Deep Reporting AI

> A production-oriented, containerized B2B SaaS Adaptive Learning Management System that models actual learner understanding, adapts learning within sessions, and generates grounded AI reporting for multiple audiences.

---

## Problem

Traditional Learning Management Systems track **completion** — not **understanding**. A learner can complete 100% of a course while retaining 10% of the material. Managers receive shallow completion dashboards that don't reveal skill gaps, declining performance, or at-risk learners.

**This platform solves that by:**

1. **Live Competency Modelling** — tracking real understanding through evidence-based mastery calculation (not completion percentage)
2. **Real-Time Adaptive Sequencing** — adjusting content difficulty, modality, and sequence based on current competency state
3. **Grounded AI Reporting** — generating insights that are traceable to underlying learning events, with citation validation

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Tenancy** | Full tenant isolation — data never leaks across organizations |
| **RBAC** | Learner, Manager, Admin roles with scoped access |
| **Content Ingestion** | Upload PDF/PPT/DOC/audio/video → AI extracts competencies + generates assessments |
| **Learning Events** | Immutable event store tracking every meaningful learner action |
| **Competency Model** | Evidence-based mastery with confidence, trend, error distribution |
| **Adaptive Engine** | Real-time sequencing: remediate, advance, skip, change modality |
| **Risk Detection** | Deterministic signals: declining mastery, consecutive failures, stagnation |
| **Grounded AI Insights** | LLM reasons over computed analytics, every claim has evidence IDs |
| **5 Reporting Surfaces** | Learner, Manager, Admin dashboards + Scheduled Digest + Embeddable Widget |
| **BI Export** | JSON/CSV export of events, competencies, reports, risks |

---

## Architecture

```
Frontend (Next.js) → API Service (FastAPI) → Adaptive Engine
                                           → Reporting Engine
                                           → Ingestion Service
                                           → Background Workers
                         ↕                       ↕
                    PostgreSQL + pgvector    Redis Streams
                         MinIO (Object Storage)
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full architecture document.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 14, TypeScript, App Router, Tailwind CSS, shadcn/ui, React Query, Recharts |
| **Backend** | Python 3.11, FastAPI, Pydantic, SQLAlchemy, Alembic |
| **Database** | PostgreSQL 16 + pgvector |
| **Cache/Async** | Redis 7 + Redis Streams |
| **Object Storage** | MinIO (S3-compatible) |
| **AI** | OpenAI-compatible provider (abstracted), sentence-transformers for embeddings |
| **Document Processing** | PyMuPDF, python-pptx, python-docx, FFmpeg, Whisper |
| **Testing** | Pytest, Playwright |
| **DevOps** | Docker, Docker Compose |

---

## Prerequisites

- **Docker Desktop** (v4.0+) with at least 8 GB RAM allocated
- **Git**
- **Node.js 20+** (for local frontend development only)
- **Python 3.11+** (for local backend development only)

---

## Quick Start

### 1. Clone the repository

```bash
git clone <repository-url>
cd adaptive-lms
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env to set your AI_API_KEY and other secrets
```

### 3. Start all services

```bash
docker compose up --build
```

### 4. Access the application

| Service | URL |
|---------|-----|
| **Frontend** | [http://localhost:3000](http://localhost:3000) |
| **API** | [http://localhost:8000](http://localhost:8000) |
| **Swagger** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **MinIO Console** | [http://localhost:9001](http://localhost:9001) |

### 5. Seed demo data

```bash
docker compose exec api python -m scripts.seed
```

### 6. Demo credentials

| Role | Email | Password |
|------|-------|----------|
| Admin (Org A) | admin@engineering-academy.com | admin123 |
| Manager (Org A) | manager@engineering-academy.com | manager123 |
| Learner (Org A) | learner1@engineering-academy.com | learner123 |
| Admin (Org B) | admin@data-academy.com | admin123 |

---

## Environment Variables

See [.env.example](./.env.example) for all configuration options:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `MINIO_ENDPOINT` | MinIO/S3 endpoint |
| `JWT_SECRET` | Secret key for JWT tokens |
| `AI_API_KEY` | API key for AI provider |
| `AI_MODEL` | AI model name (e.g., gpt-4o-mini) |
| `AI_BASE_URL` | AI provider base URL |

---

## Running Tests

```bash
# Unit + Integration tests
docker compose exec api pytest tests/ -v

# Adaptive Engine tests
docker compose exec adaptive-engine pytest tests/ -v

# Reporting Engine tests
docker compose exec reporting-engine pytest tests/ -v

# E2E tests (requires services running)
cd tests/e2e && npx playwright test
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System architecture overview |
| [docs/DATA_MODEL.md](./docs/DATA_MODEL.md) | Database schema documentation |
| [docs/EVENT_MODEL.md](./docs/EVENT_MODEL.md) | Learning event specification |
| [docs/ADAPTIVE_ENGINE.md](./docs/ADAPTIVE_ENGINE.md) | Competency model & sequencing |
| [docs/REPORTING_AI.md](./docs/REPORTING_AI.md) | Grounded AI reporting pipeline |
| [docs/CONTENT_INGESTION.md](./docs/CONTENT_INGESTION.md) | Content processing pipeline |
| [docs/MULTI_TENANCY.md](./docs/MULTI_TENANCY.md) | Multi-tenancy strategy |
| [docs/SECURITY.md](./docs/SECURITY.md) | Security architecture |
| [docs/TESTING.md](./docs/TESTING.md) | Test strategy & coverage |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Deployment guide |
| [docs/API.md](./docs/API.md) | API endpoint reference |
| [docs/CODE_MAP.md](./docs/CODE_MAP.md) | Requirement → code mapping |
| [docs/DEMO_SCRIPT.md](./docs/DEMO_SCRIPT.md) | Demo walkthrough |

---

## Known Limitations (Phase 1)

- Database models not yet created (Phase 2)
- Authentication not yet implemented (Phase 3)
- Frontend pages are placeholders (Phase 12–14)
- AI features require a valid `AI_API_KEY` in `.env`
- Whisper transcription requires FFmpeg in the ingestion container

---

## License

Proprietary — internal use only.
