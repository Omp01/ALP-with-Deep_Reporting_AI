# Deployment Guide

Adaptive LMS is designed for containerized deployment across multi-cloud environments (Docker Compose for local evaluation and Kubernetes / AWS ECS for enterprise production).

---

## 1. Local Evaluation Deployment (Docker Compose)

### Prerequisites
- Docker Engine 24.0+ and Docker Compose v2.20+
- Minimum system resources: 4 CPU cores, 8GB RAM, 10GB free disk space

### Quick Start
```bash
# 1. Clone repository & navigate to project root
cd adaptive-lms

# 2. Copy environment file
cp .env.example .env

# 3. Launch all services, workers, and infrastructure
docker compose up -d

# 4. Initialize database schema & seed demo archetypes
docker exec -it alms-api python -m scripts.init_db
docker exec -it alms-api python -m scripts.seed_demo_data
```

### Access Ports & Services
| Component | Local URL | Port | Health Check |
| :--- | :--- | :--- | :--- |
| **Next.js 14 Frontend** | [http://localhost:3000](http://localhost:3000) | 3000 | `/` (HTTP 200) |
| **FastAPI API Gateway** | [http://localhost:8000/docs](http://localhost:8000/docs) | 8000 | `/health` |
| **Adaptive Engine** | Internal | 8001 | `/health` |
| **Reporting Engine** | Internal | 8002 | `/health` |
| **PostgreSQL Database** | `localhost:5432` | 5432 | `pg_isready` |
| **Redis Cache & Streams** | `localhost:6379` | 6379 | `redis-cli ping` |
| **MinIO S3 Storage Console** | [http://localhost:9001](http://localhost:9001) | 9001 | MinIO Web UI |

---

## 2. Seeded User Personas for Demonstration

| Persona | Role | Email | Password | Primary Showcase |
| :--- | :--- | :--- | :--- | :--- |
| **Arthur Admin** | `org_admin` | `admin@acme.com` | `Password123!` | Ingestion Studio, BI Export Hub, Embeddable Widget |
| **Marcus Manager** | `manager` | `marcus.manager@acme.com` | `Password123!` | Cohort Skill Gaps, Early Warning Risk Alerts, Scheduled Digest |
| **Alice Learner** | `learner` | `alice.learner@acme.com` | `Password123!` | High Mastery ($>85\%$), Adaptive Advancement, Grounded AI "Why?" Citations |
| **Bob Learner** | `learner` | `bob.learner@acme.com` | `Password123!` | Fast Progress but Low Assessment Mastery ($42\%$), Remediation Policy |
| **Carol Learner** | `learner` | `carol.learner@acme.com` | `Password123!` | Error Clusters, Latency Spikes, Declining Trajectory Alert |
| **Dan Learner** | `learner` | `dan.learner@acme.com` | `Password123!` | Inactivity Stagnation, High Dropout Risk Warning |

---

## 3. Production Hardening Checklist

1. **Secrets Management**: Replace default `.env` JWT secret keys and database passwords with AWS Secrets Manager or HashiCorp Vault.
2. **PostgreSQL Connection Pooling**: Utilize PgBouncer for multi-service connection pooling under high concurrency.
3. **Redis Cluster**: Scale Redis into a replicated Redis Sentinel or Redis Enterprise Cluster for stream high availability.
4. **S3 Object Storage**: Point `S3_ENDPOINT_URL` to AWS S3, Google Cloud Storage, or Cloudflare R2 with IAM role credentials.
5. **TLS Termination**: Place Next.js and FastAPI behind an AWS ALB or Cloudflare CDN with TLS 1.3 encryption.
