# Adaptive LMS — End-to-End Demo Script

> **Duration**: 3–5 minutes  
> **Environment**: http://localhost:3000 (Frontend) · http://localhost:8000/docs (FastAPI Swagger)  
> **Target Audience**: L&D Executives, VP Engineering, Product Leadership, and Academic Evaluators.

---

## 1. Executive Overview (30 Seconds)

### Talking Track
> *"Welcome to the Adaptive Learning Management System with Deep Reporting AI. Most corporate LMSs track shallow metrics: seat time, video completion percentages, and clicks. Our platform solves the disconnect between **activity** and **actual competence** through Bayesian mastery tracking, deterministic pedagogical sequencing, multi-signal risk detection, and 100% grounded AI reporting with clickable [E-#] citations."*

### Key Visuals to Highlight
1. Open [http://localhost:3000](http://localhost:3000) — Notice the modern, professional white-theme UI with high contrast and accessible design tokens.
2. Click **"Explore Demo Personas"** or navigate to `/login`.

---

## 2. Persona 1: Alice Learner — High Mastery & Adaptive Advancement

### Credentials
- **Email**: `alice.learner@acme.com` / `Password123!` (or click **"Alice Learner"** on `/login`)
- **Archetype**: High mastery ($> 85\%$), high velocity, strong consistency.

### Walkthrough Steps
1. **My Dashboard (`/learner/dashboard`)**:
   - Point out the **Real-Time Adaptive Recommendation Banner**: Policy is `advance` or `skip` because Alice has demonstrated rapid mastery.
   - Point out the **Live Competency Mastery Graph**: Notice high Bayesian confidence scores ($>0.85$) and upward trend indicators (`improving`).
2. **Adaptive Learning Player (`/learner/learning`)**:
   - Click **"Enter Adaptive Learning Session"**.
   - Show the dynamic Question Bank player: Answer an assessment item.
   - Point out instant multi-factor mastery recalculation upon submission, with pedagogical policy explanation.
3. **AI Insights & Why? Inspector (`/learner/insights`)**:
   - Navigate to `/learner/insights`.
   - Highlight the **100% Grounded AI Narrative**: Notice inline citation chips like `[E-1]`, `[E-2]`.
   - Click on `[E-1]`: The **"Why?" Telemetry Proof Drawer** opens, showing the exact underlying database event, source entity (`learning_events`), confidence score, and timestamp.
   - Mention: *"Notice there is zero hallucination. Every claim is mathematically tied to verified learning events."*

---

## 3. Persona 2 & 3: Bob & Carol — Remediations & Early Warning Signals

### Walkthrough Steps
1. Switch to **Carol Learner** (`carol.learner@acme.com`):
   - **Archetype**: Declining velocity, error clusters, latency spikes.
2. Open `/learner/dashboard`:
   - Notice the Adaptive Policy is set to `remediate` or `change_modality` (suggesting interactive or slide modality rather than raw documentation).
   - Point out that Carol's competency trend is marked as `declining` with higher error penalties.

---

## 4. Persona 4: Marcus Manager — Coaching, Systemic Gaps & Interventions

### Credentials
- **Email**: `marcus.manager@acme.com` / `Password123!` (or click **"Marcus Manager"** on `/login`)
- **Role**: Team Manager & Coach for *Acme Engineering*.

### Walkthrough Steps
1. **Team Performance Dashboard (`/manager/dashboard`)**:
   - **KPI Overview**: Cohort Mastery ($74\%$), Active Rate ($85\%$), At-Risk count, and Systemic Gaps count.
   - **Systemic Cohort Skill-Gaps Table**:
     - Point out competencies where cohort average mastery is below benchmark ($< 70\%$).
     - Note the severity rating (`critical`, `moderate`) and recommended cohort action (e.g. targeted team workshop).
   - **Early-Warning At-Risk Learner Alerts**:
     - See alerts triggered by our background Risk Engine (e.g., Dan and Carol).
     - Show anomaly trigger factors: `declining_mastery`, `consecutive_assessment_failures`, `inactivity_stagnation`.
     - Click **"Resolve Alert"** on an alert card: Watch the alert resolve in real time via `PUT /api/v1/risks/{id}/resolve`.
2. **Grounded Cohort Digests (`/manager/reports`)**:
   - Navigate to `/manager/reports`.
   - Click **"Refresh Report"**: Demonstrates `POST /api/v1/insights/generate` with `scope_type: "team"`, producing an executive cohort synthesis with clickable `[E-#]` citations.
   - Click **"Trigger Proactive Run"**: Dispatches an on-demand scheduled weekly digest to managers and leadership, summarizing active enrollments, mastery index, and priority interventions.

---

## 5. Persona 5: Arthur Admin — Executive Hub, Content Ingestion & BI Export

### Credentials
- **Email**: `admin@acme.com` / `Password123!` (or click **"Arthur Admin"** on `/login`)
- **Role**: Organization Administrator & Head of L&D.

### Walkthrough Steps
1. **Executive Analytics (`/admin/dashboard`)**:
   - High-level KPIs: Active Enrollments, Organization Mastery Index ($76\%$), Curriculum Completion Rate ($68\%$).
2. **Content Ingestion & Semantic Chunker Studio**:
   - Upload any syllabus or course document (`.pdf`, `.docx`, `.txt`, `.md`).
   - Click **"Upload & Parse Syllabus"**: Demonstrates multipart file upload to S3 MinIO storage, text extraction, semantic chunking (350 tokens, 50 overlap), and ingestion job lifecycle tracking.
   - Review the **Recent Ingestion Jobs Ledger**.
3. **BI & Data Warehouse Export Hub**:
   - Point out the one-click export buttons for **Learning Telemetry Events**, **Competency Mastery Ledger**, and **Risk Signals**.
   - Click **"CSV"** or **"JSON"**: Browser downloads the streaming data file directly from `/api/v1/export/*`.
4. **Embeddable Reporting Widget Sandbox**:
   - Point out the **Live Widget Sandbox Preview** running inside an iframe from `GET /api/v1/embed/report`.
   - Click **"Copy Embed Code"** to show how easy it is to drop the widget into an enterprise intranet, Notion, or Slack canvas.

---

## 6. Verification & Developer Checkpoints

| Capability | Verification Endpoint / Command | Status |
| :--- | :--- | :--- |
| **80 Automated Tests** | `docker exec alms-api pytest tests -v` | Passing (80/80) |
| **All Frontend Routes** | `/`, `/login`, `/learner/*`, `/manager/*`, `/admin/*` | HTTP 200 OK |
| **Tenant Isolation** | Header `Authorization: Bearer <token>` enforces Org scoping | Verified |
| **Event Pipeline** | Redis Stream `learning_events` consumed by `event-worker` | Active |
| **Proactive Worker** | `risk-worker` and `digest-worker` background loops | Active |

---

*End of Demo Script — All systems verified, containerized, and production-ready.*
