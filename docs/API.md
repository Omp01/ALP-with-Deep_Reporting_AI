# Adaptive LMS — API Reference

All requests must include the JWT bearer token in the `Authorization` header:
```
Authorization: Bearer <access_token>
```
The API automatically scopes every query to the caller's verified `org_id` (multi-tenancy) and validates permissions against 5 supported roles: `learner`, `instructor`, `manager`, `org_admin`, and `super_admin`.

Interactive OpenAPI Swagger UI is available locally at: **[http://localhost:8000/docs](http://localhost:8000/docs)**.

---

## 1. Authentication & RBAC

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Public | Authenticates credentials, generates JWT access token, and logs audit record. |
| `GET` | `/api/v1/auth/me` | Any Authenticated | Returns profile, active tenant ID, and permissions for current caller. |
| `POST` | `/api/v1/auth/refresh` | Any Authenticated | Refreshes expired access tokens. |
| `POST` | `/api/v1/auth/logout` | Any Authenticated | Invalidate session tokens. |

---

## 2. LMS Core Curriculum & Enrollments

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/courses` | Any Authenticated | Lists published courses for caller's organization. |
| `POST` | `/api/v1/courses` | Instructor, Admin | Creates a new curriculum course. |
| `GET` | `/api/v1/courses/{id}` | Any Authenticated | Retrieves course details and sequenced modules. |
| `POST` | `/api/v1/courses/{id}/modules` | Instructor, Admin | Adds a sequenced module to a course. |
| `POST` | `/api/v1/modules/{id}/content` | Instructor, Admin | Adds a content asset to a module (text, slide, video, quiz). |
| `GET` | `/api/v1/enrollments` | Any Authenticated | Lists learner course enrollments and milestone progress. |
| `POST` | `/api/v1/enrollments` | Any Authenticated | Enrolls a learner in a curriculum course. |

---

## 3. Content Ingestion Pipeline

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/ingestion/upload` | Instructor, Admin | Uploads syllabus document (`.pdf`, `.docx`, `.txt`, `.md`) to S3 MinIO storage. |
| `POST` | `/api/v1/ingestion/jobs/{id}/process` | Instructor, Admin | Triggers semantic chunking (350 tokens, 50 overlap) and knowledge extraction. |
| `GET` | `/api/v1/ingestion/jobs` | Instructor, Admin | Lists recent ingestion jobs and extraction status. |
| `GET` | `/api/v1/ingestion/jobs/{id}` | Instructor, Admin | Retrieves granular progress and chunk count for a job. |

---

## 4. Learning Events Telemetry

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/events` | Any Authenticated | Ingests a canonical learning event into PostgreSQL and publishes to Redis Stream `learning_events`. |
| `POST` | `/api/v1/events/batch` | Any Authenticated | High-throughput batch telemetry ingestion. |
| `GET` | `/api/v1/events` | Any Authenticated | Retrieves event audit trail (learners scoped to self; managers scoped to team; admins scoped to org). |
| `GET` | `/api/v1/events/stats` | Instructor, Admin | Aggregate event frequency and distribution statistics. |

---

## 5. Real-Time Adaptive Sequencing Engine

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/adaptive/next` | Any Authenticated | Computes next-step recommendation based on deterministic pedagogical policy (`advance`, `remediate`, `skip`, `change_modality`, `revisit`). |
| `GET` | `/api/v1/adaptive/decisions/{learner_id}` | Any Authenticated | Explainable decision audit log explaining the rationale behind adaptive sequencing. |
| `GET` | `/api/v1/adaptive/competencies/{learner_id}` | Any Authenticated | Live Bayesian mastery scores ($0.0–1.0$), confidence ratings, and trend vectors. |
| `GET` | `/api/v1/adaptive/skill-gaps/{learner_id}` | Any Authenticated | Individual learner skill gaps with targeted remediation recommendations. |
| `GET` | `/api/v1/adaptive/cohort-gaps/{team_id}` | Manager, Admin | Systemic cohort skill bottlenecks where average mastery falls below $70\%$. |

---

## 6. Risk Engine (Early Warning & Interventions)

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/risks` | Manager, Admin | Lists at-risk learners across the organization with risk scores ($0.0–1.0$) and anomaly triggers. |
| `GET` | `/api/v1/risks/{learner_id}` | Any Authenticated | Risk history and anomaly breakdown for a specific learner. |
| `POST` | `/api/v1/risks/scan` | Manager, Admin | On-demand organization-wide risk scanner trigger. |
| `PUT` | `/api/v1/risks/{risk_id}/resolve` | Manager, Admin | Marks an at-risk alert as resolved post-coaching intervention. |

---

## 7. Grounded AI Insights & Evidence Engine

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/insights/generate` | Any Authenticated | Synthesizes an evidence-grounded AI narrative report with explicit `[E-#]` citation keys. |
| `GET` | `/api/v1/insights/{id}` | Any Authenticated | Retrieves generated insight, claims list, and grounding confidence score. |
| `GET` | `/api/v1/insights/{id}/evidence` | Any Authenticated | Returns backing telemetry fact package for "Why?" evidence inspection. |

---

## 8. Deterministic Analytics Gateway

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/learner/{user_id}` | Any Authenticated | Progress, velocity, and mastery analytics for a learner. |
| `GET` | `/api/v1/analytics/team/{team_id}` | Manager, Admin | Cohort velocity, active rate, and average team mastery index. |
| `GET` | `/api/v1/analytics/organization` | Admin | Executive high-level KPIs across all courses and cohorts. |

---

## 9. Scheduled Digests & Proactive Reporting

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/reports/digest/generate` | Manager, Admin | Triggers on-demand execution of the proactive scheduled leadership digest. |
| `GET` | `/api/v1/reports/digest/latest` | Manager, Admin | Retrieves the latest scheduled leadership digest and dispatch metadata. |

---

## 10. BI Export & Data Warehouse Streaming

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/export/events` | Admin | Streams learning events in CSV or JSON format for data warehouses. |
| `GET` | `/api/v1/export/competencies` | Admin | Streams competency mastery ledger in CSV or JSON format. |
| `GET` | `/api/v1/export/risks` | Admin | Streams risk signals and resolution histories in CSV or JSON format. |

---

## 11. Embeddable Reporting Widget

| Method | Path | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/embed/report` | Public / Token | Returns responsive HTML card widget or JSON summary for enterprise intranet embeds. |
