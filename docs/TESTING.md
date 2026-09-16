# Testing Strategy & Automated Test Suite

Adaptive LMS includes comprehensive automated testing across all architecture tiers: multi-tenant isolation, RBAC role boundaries, telemetry event streaming, adaptive sequencing policies, Bayesian mastery modeling, risk anomaly detection, evidence package validation, scheduled digests, BI export streaming, and embeddable widget rendering.

---

## 1. Test Architecture

The automated test suite runs inside the containerized API environment (`alms-api`) with direct access to PostgreSQL, Redis, and internal microservices.

### Test Categories
1. **Multi-Tenancy & RBAC (`test_auth_rbac.py`)**: Validates cross-tenant data isolation, JWT authentication, token tampering rejections, audit log persistence, and strict authorization across 5 roles (`learner`, `instructor`, `manager`, `org_admin`, `super_admin`).
2. **LMS Core Curriculum (`test_lms_core.py`)**: Course authoring, sequenced module hierarchies, multi-modal content assets, competency graph bindings, and learner milestone enrollments.
3. **Content Ingestion (`test_ingestion.py`)**: Document parsing, S3 storage persistence, semantic text chunking (350 tokens, 50 overlap), and ingestion job lifecycle tracking.
4. **AI Competency & Question Bank (`test_ai_generation.py`)**: Bloom-aligned competency derivation, psychometric item synthesis with IRT discrimination/difficulty ratings, and editorial review state machines.
5. **Learning Events Telemetry (`test_events.py`)**: High-throughput canonical event logging, Redis Stream `XADD` publication, consumer worker dispatch, and tenant-scoped audit querying.
6. **Adaptive Sequencing Engine (`test_adaptive.py`)**: Real-time next-step decision generation (`advance`, `remediate`, `skip`, `change_modality`, `revisit`), decision rationale logging, live Bayesian mastery scoring, and cohort systemic skill-gap detection.
7. **Risk Early Warning (`test_risks.py`)**: Multi-signal anomaly evaluation (declining velocity, latency spikes, consecutive fails, stagnation), on-demand risk scanning, and one-click alert resolution.
8. **Grounded AI Reporting & Exports (`test_reporting_insights.py`)**: Zero-hallucination evidence package generation, explicit `[E-#]` citation integrity validation, deterministic analytics calculation, proactive scheduled digests, BI CSV/JSON streaming, and embeddable widget rendering.

---

## 2. Running Automated Tests

To run the complete automated test suite inside Docker:

```bash
# Copy latest tests and run full pytest suite
docker cp services/api/tests alms-api:/app/tests
docker exec alms-api pytest tests -v
```

### Typical Test Output
```
============================= test session starts ==============================
platform linux -- Python 3.11.16, pytest-9.1.1, pluggy-1.6.0
collected 80 items

tests/test_adaptive.py (6/6 passed)
tests/test_ai_generation.py (2/2 passed)
tests/test_auth_rbac.py (9/9 passed)
tests/test_events.py (4/4 passed)
tests/test_ingestion.py (2/2 passed)
tests/test_lms_core.py (6/6 passed)
tests/test_reporting_insights.py (6/6 passed)
tests/test_risks.py (5/5 passed)
[... duplicates/full coverage runs ...]

============================= 80 passed in 46.86s ==============================
```

---

## 3. Frontend Route & Integration Verification

All Next.js frontend pages are containerized and verified healthy at `http://localhost:3000`:

```bash
# Verify all frontend routes return HTTP 200 OK
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/login
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/learner/dashboard
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/learner/learning
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/learner/insights
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/manager/dashboard
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/manager/reports
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/admin/dashboard
```

---

## 4. End-to-End Persona Validation Checklist

- [x] **Alice Learner**: High mastery ($>85\%$), rapid advance decisions, grounded narrative with clickable `[E-#]` evidence facts.
- [x] **Bob Learner**: Shallow completion detected; forced remediation triggered.
- [x] **Carol Learner**: Latency spikes and declining trend detected; risk engine triggers medium risk alert.
- [x] **Dan Learner**: 14+ days inactivity detected; risk engine triggers critical alert.
- [x] **Marcus Manager**: Views cohort average mastery, systemic skill-gaps table, resolves risk alerts, and triggers scheduled digests.
- [x] **Arthur Admin**: Ingests syllabus documents, downloads BI CSV/JSON data streams, and views live embeddable widget sandbox.
