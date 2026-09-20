# Adaptive LMS — Complete Demo Recording Walkthrough Script

> **A step-by-step, screen-by-screen recording script with verbatim voiceover dialogue, UI action cues, visual proof points, and pre-flight instructions.**
>
> **Target Duration:** ~8–9 minutes (Deep Dive) or ~5 minutes (Executive Cut)  
> **Target Audience:** Engineering leadership, enterprise buyers, product juries, or portfolio reviewers  
> **Core Theme:** *Traditional LMSs track completion — this platform proves comprehension through deterministic Bayesian modeling and 100% evidence-grounded AI reporting.*

---

## Pre-Flight Setup Checklist (Complete Before Recording)

Run these commands once from the `adaptive-lms/` directory in PowerShell / Bash:

```powershell
# 1. Start core infrastructure (Postgres 16, Redis 7, MinIO S3)
docker compose up -d postgres redis minio

# 2. Run database migrations to head
$env:DATABASE_URL_SYNC = "postgresql://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"
python -m alembic -c database/alembic.ini upgrade head

# 3. Seed curriculum, organizations, users, and skill graph
python scripts/seed.py

# 4. Generate synthetic learner telemetry through the real Bayesian engine
python scripts/generate_demo_data.py

# 5. Start API & background services
# In Terminal 1 (API Gateway - port 8000):
$env:PYTHONPATH=".;..\..\shared;."
python -m uvicorn services.api.app.main:app --reload --port 8000

# In Terminal 2 (Frontend - port 3000):
cd frontend
npm run dev

# (Optional) If running offline without Ollama/OpenAI, run the mock LLM server:
# python scripts/e2e/fake_llm_server.py 8199
```

### Recording Setup & Tips
- **Resolution:** 1080p (1920 × 1080) at 60 fps.
- **Browser:** Chrome or Edge at 100% zoom with clean bookmarks bar.
- **Quick Switching:** Keep `http://localhost:3000/login` bookmarked. All personas can be logged in with a single click from the persona cards.
- **Password (if needed):** `Password123!` for every seeded account.
- **Tone:** Confident, technical, and grounded. Emphasize *verifiability*, *mathematical rigor*, and *zero hallucination*.

---

## Demo Personas Cheat Sheet

| Persona | Role | Email | Key Narrative Purpose |
| :--- | :--- | :--- | :--- |
| **Carol Clark** | Learner | `carol.learner@acme.com` | Login check-in, in-session adaptation, "Why am I seeing this?" |
| **Bob Bennett** | Learner | `bob.learner@acme.com` | "Completion is not comprehension" — 100% progress but low mastery |
| **Alice Adams** | Learner | `alice.learner@acme.com` | High mastery, fast advancement, verified evidence chain |
| **Dan Davis** | Learner | `dan.learner@acme.com` | Inactivity dropout risk detection |
| **Marcus Miller** | Manager | `marcus.manager@acme.com` | Cohort skill gaps, early warning alerts, team AI insights, digests |
| **Sarah / Arthur** | Org Admin | `admin@acme.com` | Ingestion pipeline, question review, skill graph DAG, BI exports |
| **Elena / Admin** | TechNova | `admin@technova.com` | Multi-tenant zero data-leak demonstration |

---

## Visual Architecture Overview (30-Second Framing)

```
┌────────────────────────────────────────────────────────────────────────┐
│                        THE CLOSED LEARNING LOOP                        │
│                                                                        │
│  Multi-Modal Content Ingestion (PDF / DOCX / YouTube)                  │
│       │                                                                │
│       ▼                                                                │
│  Daily Learner Check-in (AI Quizzes + Psychometrics)                   │
│       │                                                                │
│       ▼                                                                │
│  Append-Only Learning Telemetry (20 Real-Time Event Types)             │
│       │                                                                │
│       ▼                                                                │
│  Deterministic Bayesian Knowledge Tracing (Corbett-Anderson BKT)       │
│       │                                                                │
│       ▼                                                                │
│  Explainable Next Step Recommendation ("Why am I seeing this?")        │
│       │                                                                │
│       ▼                                                                │
│  Multi-Signal Early Warning Detection (6 Risk Anomaly Signals)         │
│       │                                                                │
│       ▼                                                                │
│  Grounded AI Reporting with Clickable [E-#] Evidence Drawers           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Master Walkthrough Script

```
TIMELINE SUMMARY:
[0:00 - 0:45] Scene 0: Introduction & The Core Problem (Login Page)
[0:45 - 2:15] Scene 1: Daily Diagnostic Check-in & Psychometrics (Carol)
[2:15 - 4:00] Scene 2: In-Session Adaptive Player & AI Grading (Carol)
[4:00 - 5:30] Scene 3: Explainable Competencies & The Audit Chain (Bob & Alice)
[5:30 - 7:00] Scene 4: Manager Intelligence & Multi-Signal Early Warning (Marcus)
[7:00 - 8:30] Scene 5: Multi-Modal Ingestion, Skill Graph DAG & BI Hub (Admin)
[8:30 - 9:00] Scene 6: Cross-Tenant Isolation & Zero-Hallucination Wrap-Up
```

---

### Scene 0: Introduction & The Core Problem (0:00 – 0:45)

**Location:** `http://localhost:3000/login`  
**Persona:** Persona Switcher Grid

#### What to Do on Screen:
1. Open `http://localhost:3000/login` showing the 6 persona cards.
2. Hover over **Bob Bennett** ("Shallow Completion") and **Alice Adams** ("High Mastery").
3. Keep the mouse cursor steady and highlight the persona badges (`Mastery > 0.85`, `Fast Scroll / Low Accuracy`, `Declining Mastery`).

#### Spoken Script (Voiceover):
> *"Welcome. In corporate learning today, platforms track **seat time and completion, not comprehension**. A learner can click through 100% of a course, mark every slide finished, and still lack the core skills required for their job.*
>
> *This is an Adaptive Learning Platform engineered to solve the comprehension crisis. It combines real-time Bayesian Knowledge Tracing, deterministic pedagogical sequencing, multi-signal early warning anomaly detection, and 100% grounded AI reporting where every single statement links to verifiable database evidence.*
>
> *Let's see the entire closed loop in action, starting with our learner Carol Clark."*

---

### Scene 1: Daily Diagnostic Check-in & Psychometrics (0:45 – 2:15)

**Location:** `http://localhost:3000/learner/checkin`  
**Persona:** `carol.learner@acme.com` (Carol Clark — Struggling / Declining)

#### What to Do on Screen:
1. Click the **Carol Clark** persona card on `/login`. The system signs in and immediately routes to `/learner/checkin`.
2. Scroll through the check-in interface:
   - Point to the **5 diagnostic questions** generated from her active curriculum.
   - Point to the **12 psychometric statements** organized across 4 dimensions: Cognitive Load, Learning Anxiety, Self-Efficacy, and Engagement.
3. Answer a couple of questions quickly (select choices, rate sliders 1–5).
4. Click **"Submit Check-in"**.
5. Once submitted, review the **Check-in Results**:
   - Highlight the **Coaching Note**.
   - Expand the **Question Review accordion**: show that each question quotes the exact source passage from the course material.
   - Show the **Private Self-Report Score card**: emphasize the privacy disclaimer (*"Visible only to you — never shared with your manager"*).
6. Click **"Go to Dashboard"** (or navigate to `/learner/dashboard`).

#### Spoken Script (Voiceover):
> *"Every time a learner signs in, the platform opens an active diagnostic check-in. This isn't generic trivia — an AI model synthesizes five targeted questions directly from Carol's enrolled courses, and each question is checked against the course text.*
>
> *Below the quiz are twelve psychometric self-report statements measuring cognitive load, learning anxiety, self-efficacy, and engagement.*
>
> *When Carol submits, the platform instantly evaluates her performance. Notice the question review: every single question displays the exact passage from the source curriculum it was derived from.*
>
> *Crucially, her psychometric scores are strictly private to her. They help personalize her learning pace, but are never exposed to managers to ensure psychological safety.*
>
> *Now let's step into Carol's learning experience."*

---

### Scene 2: In-Session Adaptive Player & AI Grading (2:15 – 4:00)

**Location:** `http://localhost:3000/learner/dashboard` ➔ `http://localhost:3000/learner/learning`  
**Persona:** `carol.learner@acme.com`

#### What to Do on Screen:
1. On `/learner/dashboard`, highlight the **"Recommended for you"** card and the continue learning progress.
2. Click **"Continue"** to enter the Learning Player (`/learner/learning`).
3. In the sidebar of the player, point to the **"Recommended: Review first"** or **"Recommended next step"** card.
4. Click the link: **"Why am I seeing this?"** to expand the explanation drawer.
   - Show that the panel displays: *Reason headline, exact failure evidence (e.g. repeated procedural errors in stream processing), current estimated mastery (e.g. 38%), confidence level, and alternative actions considered.*
5. Emphasize: *Nothing in this text is hardcoded.*
6. Complete the current lesson (click **"Mark as Complete"** or advance).
7. Show that the recommendation **instantly updates** to **"Check your understanding"** (Assessment). This demonstrates *in-session real-time adaptation*.
8. Open the assessment item containing a **short written answer**.
9. Type a response: `"Stream consumers use consumer groups and offset commits to achieve at-least-once delivery."` and click **Submit**.
10. Show the grading feedback: evaluated against a deterministic rubric. Point out that if the AI grader is ever unsure, it flags the answer for human instructor review rather than fabricating a score.

#### Spoken Script (Voiceover):
> *"In the learning player, Carol doesn't just get a static linear playlist. Look at this recommendation widget. It's currently directing her to remediate. But instead of an opaque black box, Carol can click **'Why am I seeing this?'**.*
>
> *The engine explains its reasoning directly from stored facts: her recent pattern of procedural errors, her current estimated mastery, and the pedagogical rule applied. Nothing here is a template or hardcoded.*
>
> *Watch what happens when she completes this review lesson: the engine immediately re-evaluates her session state in real time and changes the recommendation to an assessment.*
>
> *When Carol submits a written answer, our AI grading agent evaluates her response against a structured rubric. It produces an assessment signal—never an arbitrary grade. And if the model lacks confidence, the response is routed to an instructor's review queue. The system never guesses."*

---

### Scene 3: Explainable Competencies & The Audit Chain (4:00 – 5:30)

**Location:** `http://localhost:3000/learner/competencies`  
**Persona:** Switch to `bob.learner@acme.com` (Bob Bennett — Shallow Completion)

#### What to Do on Screen:
1. Click logout or navigate to `/login`, and click **Bob Bennett** (`bob.learner@acme.com`).
2. Skip the check-in to jump directly to `/learner/competencies`.
3. Highlight Bob's profile:
   - Point out that Bob completed all modules of his course.
   - Look at the competency table: `python.functions` shows **Mastery: 29%**, **Trend: Declining**, and **below target (80%)**.
4. Click the button: **"Why 29%?"**.
5. The **Evidence Chain Drawer** slides open from the right.
6. Scroll down through the audit chain:
   - Point out each discrete attempt: *Signal (0.0), Previous Mastery (0.42) ➔ New Mastery (0.34), Error taxonomy: `conceptual_misunderstanding`.*
   - Point to the green shield badge at the top: **"Chain Verified & Recomputed"**.
7. Close the drawer and point out the **"Where you are below your target"** section listing specific skill gaps with concrete reasons.

#### Spoken Script (Voiceover):
> *"Now let's look at Bob Bennett to understand why traditional completion metrics fail. Bob clicked through 100% of his Python and Data courses. In a legacy LMS, he would be marked certified.*
>
> *Here on his Competencies page, the truth is obvious: his estimated mastery in Python Functions is only 29%. Reading or watching a video never increases mastery on this platform—only verified, graded evidence does.*
>
> *When Bob or an auditor asks: **'Why 29%?'**, they don't get a hallucinated summary. They click this button to open the complete cryptographic and mathematical audit chain.*
>
> *Here is every single graded response Bob has ever submitted, timestamped, tagged with error taxonomy, and updated through deterministic Corbett-Anderson Bayesian Knowledge Tracing.*
>
> *Notice this green badge: **'Chain Verified & Recomputed'**. The server recomputes the entire mathematical formula from raw evidence in real time. If any record were altered, the badge would fail.*
>
> *This turns competency modeling from a black box into a verifiable accounting ledger."*

---

### Scene 4: Manager Intelligence & Multi-Signal Early Warning (5:30 – 7:00)

**Location:** `http://localhost:3000/manager/dashboard` ➔ `/manager/insights` ➔ `/manager/reports`  
**Persona:** `marcus.manager@acme.com` (Marcus Miller — Engineering Lead)

#### What to Do on Screen:
1. Switch to Marcus Miller via `/login`. You arrive at `/manager/dashboard`.
2. **Team Analytics & Cohort Gaps:**
   - Scroll to **Cohort Skill Gaps**. Point out: *Assessed Learners, Below Target, Declining, Median Mastery*. Highlight that the system shows distribution and median mastery, *never a deceptive single team average*.
3. **Early Warning Risk Engine:**
   - Scroll to the **Risk Alerts** section.
   - Point out **Dan Davis**: Severity `HIGH` / `CRITICAL` — *Reason: 14 days of complete inactivity (dropout anomaly).*
   - Point out **Carol Clark**: Severity `MEDIUM` — *Reason: Declining performance and repeated retries on Stream Processing.*
4. **AI Team Insights:**
   - In the sidebar, click **AI Team Insights** (`/manager/insights`).
   - Show the generated report. Point out the citations: `[E-1]`, `[E-2]`.
   - Click one of the **Evidence buttons** (e.g. `[E-1]`). The **Evidence Drawer** opens showing the exact underlying database records cited by the AI.
5. **Reports & Digests:**
   - In the sidebar, click **Reports & Digests** (`/manager/reports`).
   - Click **"Generate weekly digest now"**. Watch the digest generate and display in the feed.
   - Click **"Create Embed Snippet"**: Show the generated iframe embed snippet powered by a time-limited, scoped JWT token for embedding into company intranets.

#### Spoken Script (Voiceover):
> *"Let's switch to Marcus Miller, our engineering manager. On Marcus's dashboard, we don't show superficial course completion percentages. We show true cohort skill health.*
>
> *Notice our Cohort Gaps table: we report the exact count of assessed learners, who is below target, and median mastery. We never mask weak performers behind a misleading average.*
>
> *Below that is our autonomous **Multi-Signal Early Warning Engine**. It monitors six objective risk signals: persistent low mastery, negative velocity, retry loops, response latency anomalies, and inactivity.*
>
> *Dan Davis is flagged for immediate dropout risk because of fourteen days of zero activity. Carol is flagged for a declining mastery trajectory.*
>
> *Over on **AI Team Insights**, the reporting engine synthesizes these findings into actionable executive intelligence. Notice these citation pills: `[E-1]`, `[E-2]`. If Marcus clicks `[E-1]`, the Evidence Drawer opens showing the exact database rows that prove the claim. The AI is strictly barred from making unsupported statements.*
>
> *Finally, managers can generate automated weekly digests on demand and create scoped, expiring embed widgets to bring these insights directly into Slack, Notion, or internal executive portals."*

---

### Scene 5: Content Ingestion, Skill Graph DAG & BI Hub (7:00 – 8:30)

**Location:** `http://localhost:3000/admin/content` ➔ `/admin/skill-graph` ➔ `/admin/grading` ➔ `/admin/activity`  
**Persona:** `admin@acme.com` (Sarah / Arthur Admin)

#### What to Do on Screen:
1. Switch to Arthur / Sarah Admin via `/login`.
2. **Multi-Modal Content Ingestion (`/admin/content`):**
   - Click **"Add Content"** (`/admin/content/new`).
   - Show the upload options: PDF, DOCX, TXT, Markdown, or YouTube link.
   - Walk through the pipeline: *Document Parsing ➔ Semantic Chunking ➔ AI Objective Extraction (Bloom's Taxonomy) ➔ Automated Question Drafting with verbatim source citations.*
   - Show that before anything goes live, admins have an **Approval & Review stage** where they can edit, accept, or reject questions.
3. **Skill Graph DAG (`/admin/skill-graph`):**
   - In the sidebar, click **Skill Graph**.
   - Show the interactive graph of competency prerequisites (e.g. *Python Basics ➔ Functions ➔ OOP / Async ➔ Stream Processing*).
   - Point out the **Prerequisite Constraints & Minimum Mastery thresholds** (e.g. minimum 60% mastery required).
   - Mention the built-in cycle detection algorithm that prevents recursive prerequisite deadlocks.
4. **Instructor Grading Queue (`/admin/grading`):**
   - Click **Grading Queue**. Show the pending submissions where the AI grader requested human-in-the-loop review.
5. **Activity Stream & BI Export (`/admin/activity`):**
   - Click **Activity**. Show the live telemetry feed: 20 distinct learning event types (video playback, question answers, pauses, session starts).
   - Point out the **Export BI Data** buttons (CSV / JSON streaming endpoints) ready for Snowflake, Databricks, or PowerBI.

#### Spoken Script (Voiceover):
> *"Now we move into the Administrator and L&D Director console.*
>
> *Under Content Management, we have a complete multi-modal ingestion pipeline. An admin can upload a corporate PDF handbook, technical documentation, or paste a YouTube training link.*
>
> *The system parses the document, splits it into semantic chunks, and extracts learning objectives categorized by Bloom's Taxonomy. It automatically drafts diagnostic assessment items—each quoting the exact source sentence it tests.*
>
> *Admins retain total human-in-the-loop control to review, edit, and approve every question before publication.*
>
> *Under **Skill Graph**, you can see our curriculum visualized as a Directed Acyclic Graph (DAG). Competencies have strict prerequisite relationships and minimum mastery thresholds. The engine includes automated cycle detection to guarantee curriculum integrity.*
>
> *Under **Grading Queue**, instructors can review any written submissions that the AI grader held back due to low confidence.*
>
> *And under **Activity**, administrators have access to an immutable, append-only event stream tracking twenty distinct micro-interactions. Every event is server-validated and exportable via streaming CSV and JSON endpoints for enterprise data warehouses."*

---

### Scene 6: Cross-Tenant Isolation & Zero-Hallucination Wrap-Up (8:30 – 9:00)

**Location:** `http://localhost:3000/login` ➔ `admin@technova.com`  
**Persona:** TechNova Systems Admin

#### What to Do on Screen:
1. Log out and sign in as `admin@technova.com` (TechNova Systems).
2. Show the topbar and dashboard:
   - Organization name displays **TechNova Systems**.
   - Show that Acme's courses, learners (Alice, Bob, Carol, Dan), and teams are completely invisible.
   - Mention that every database query is scoped by `org_id` at the SQLAlchemy ORM layer.
3. Bring up the final closing slide or return to the main dashboard.

#### Spoken Script (Voiceover):
> *"Finally, the entire architecture is built for enterprise multi-tenancy. Signing in as an administrator for TechNova Systems, you can see that tenant boundaries are enforced at the database query level. Cross-tenant data leakage is mathematically impossible.*
>
> *To summarize what we've seen today:*
> 1. *We replaced superficial course completion with deterministic Bayesian mastery modeling.*
> 2. *We provided transparent, explainable adaptation with 'Why am I seeing this?'.*
> 3. *We enabled multi-signal early warning detection to catch at-risk learners weeks before they drop out.*
> 4. *And we built an evidence-first reporting AI with 100% verifiable citations and zero tolerance for hallucination.*
>
> *Thank you for watching the demo. The full codebase, automated test suite, and architectural documentation are ready for your inspection."*

---

## 5-Minute "Executive Cut" (Alternative Short Script)

If you only have 5 minutes to record, follow this condensed flow:

| Timestamp | Screen | Action | Key Talking Point |
| :--- | :--- | :--- | :--- |
| **0:00 – 0:45** | `/login` ➔ Bob | Sign in as Bob (`bob.learner@acme.com`) | "Completion is not comprehension. Bob completed 100% of his course but has critical skill gaps." |
| **0:45 – 1:45** | `/learner/competencies` | Open Bob's Competencies ➔ Click **"Why 29%?"** | Show the Evidence Chain Drawer and the green **"Verified & Recomputed"** BKT badge. |
| **1:45 – 2:45** | `/learner/learning` | Switch to Carol ➔ Learning Player | Show **"Why am I seeing this?"** in the adaptive recommendation card, then complete a step to show in-session adaptation. |
| **2:45 – 3:45** | `/manager/dashboard` & `/manager/insights` | Switch to Marcus Manager | Show Early Warning Risk Alerts (Dan inactive, Carol declining) and AI Team Insights with clickable `[E-#]` evidence pills. |
| **3:45 – 4:45** | `/admin/content` & `/admin/skill-graph` | Switch to Arthur Admin | Show multi-modal document ingestion, question drafting with source citations, and the Skill Graph DAG. |
| **4:45 – 5:00** | `/login` ➔ TechNova | Switch to TechNova | Multi-tenant isolation at the query level. Wrap up. |

---

## Troubleshooting & Demo Fallback Plan

- **If Ollama or LLM API is slow or offline:**
  - Launch the mock LLM server in a separate terminal:
    ```powershell
    python scripts/e2e/fake_llm_server.py 8199
    ```
  - Or let the reporting engine fall back to its offline deterministic generator—all evidence tables, BKT calculations, and recommendations remain 100% functional.
- **If Check-in takes more than 3 seconds:**
  - The UI has built-in polling and skeleton loaders. You can also click **"Skip for now"** to jump straight to the dashboard.
- **If you need to reset all demo data to pristine state:**
  ```powershell
  python scripts/seed.py
  python scripts/generate_demo_data.py
  ```
