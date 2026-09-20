# Requirements Traceability Matrix

> Comprehensive tracking of all 54 core assignment requirements across implementation phases, services, database tables, and verification tests.

---

## Status Legend
- `[IMPLEMENTED]` - Fully implemented, migrated, seeded, and verified in running containers.
- `[IN_PROGRESS]` - Currently being implemented in active phase.
- `[PLANNED]` - Scheduled in subsequent implementation phases.

---

## 1. Platform Foundation, Multi-Tenancy & Security

| ID | Requirement Description | Target Phase | Status | Implemented Artifacts / Tables |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-01** | Multi-tenant organization isolation | Phase 1 & 2 | `[IMPLEMENTED]` | `organizations`, `org_id` on all 25 tables, [organization.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/organization.py) |
| **REQ-02** | Role-Based Access Control (5 distinct roles) | Phase 2 & 3 | `[IMPLEMENTED]` | `UserRole` enum, `users.role`, [user.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/user.py), [seed.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/scripts/seed.py) |
| **REQ-03** | Secure JWT authentication & bcrypt hashing | Phase 2 & 3 | `[IMPLEMENTED]` | [security.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/core/security.py) (bcrypt 72-byte safe + python-jose JWT) |
| **REQ-04** | Team / Cohort organizational grouping | Phase 2 | `[IMPLEMENTED]` | `teams`, `user_teams`, [user.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/user.py) |
| **REQ-05** | Immutable compliance audit logging | Phase 2 | `[IMPLEMENTED]` | `audit_logs`, [organization.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/organization.py) |
| **REQ-06** | Vendor-agnostic AI provider abstraction | Phase 1 | `[IMPLEMENTED]` | [ai_provider.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/schemas/ai_provider.py) (`AIProvider` interface) |

---

## 2. Curriculum, Ingestion & Competency Framework

| ID | Requirement Description | Target Phase | Status | Implemented Artifacts / Tables |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-07** | Hierarchical Course and Module structures | Phase 2 | `[IMPLEMENTED]` | `courses`, `modules`, [course.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/course.py) |
| **REQ-08** | Multi-modal Content items (text, video, slide, audio) | Phase 2 | `[IMPLEMENTED]` | `content_items`, `content_chunks`, [course.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/course.py) |
| **REQ-09** | Vector chunking and semantic embeddings | Phase 2 | `[IMPLEMENTED]` | `content_chunks.embedding`, [course.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/course.py) |
| **REQ-10** | Asynchronous document ingestion pipeline | Phase 5 | `[IMPLEMENTED]` | `ingestion_jobs`, [ingestion.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/ingestion.py), [text_extractor.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/parsers/text_extractor.py) |
| **REQ-11** | Bloom's Taxonomy hierarchical competency framework | Phase 2 | `[IMPLEMENTED]` | `competencies`, `taxonomy_level`, [competency.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/competency.py) |
| **REQ-12** | Course and Module competency mappings | Phase 2 | `[IMPLEMENTED]` | `course_competencies`, `module_competencies` |

---

## 3. Assessment & Psychometrics

| ID | Requirement Description | Target Phase | Status | Implemented Artifacts / Tables |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-13** | Multi-format question bank (MCQ, multi-select, boolean) | Phase 2 | `[IMPLEMENTED]` | `assessment_items`, [assessment.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/assessment.py) |
| **REQ-14** | Item Response Theory (IRT) difficulty & discrimination parameters | Phase 2 | `[IMPLEMENTED]` | `difficulty_score`, `discrimination_index` in `assessment_items` |
| **REQ-15** | AI-generated assessment items with review lifecycle | Phase 3 | `[IMPLEMENTED]` (rebuilt) | Grounded `question_candidates` with `source_quote`, admin review and publish: [content_admin.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/content_admin.py), [analysis.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/analysis.py), [publish.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/ingestion/publish.py). Replaces the earlier `ai.py` / `ai_service.py`, which faked output |

---

## 4. Adaptive Learning & Real-Time Mastery

| ID | Requirement Description | Target Phase | Status | Implemented Artifacts / Tables |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-16** | Deterministic, explainable mastery estimation from graded evidence (soft-evidence BKT); LLM only produces a signal; every update has an audit chain | Phase 5 | `[IMPLEMENTED]` (rebuilt) | [bkt.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/bkt.py), [service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/service.py), `learner_competencies`, `evidence_records`, `competency_state_updates`, [COMPETENCY_ENGINE.md](COMPETENCY_ENGINE.md). Parameters are documented defaults, not fitted |
| **REQ-16a** | Written-answer grading agent (rubric, signal, confidence, quote, error type) with human review and prompt-injection defences | Phase 5 | `[IMPLEMENTED]` | [grader.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/grading/grader.py), [assessment.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/assessment.py), `grading_results`, [grading.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/grading.py), [GRADING_AGENT.md](GRADING_AGENT.md). Real-model quality unverified |
| **REQ-17** | Prerequisite-aware, evidence-based next-step sequencing with eight actions and "Why this?" from stored facts | Phase 6 | `[IMPLEMENTED]` (rebuilt) | [engine.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/adaptive/engine.py), [service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/adaptive/service.py), `adaptive_decisions`, [ADAPTIVE_ENGINE.md](ADAPTIVE_ENGINE.md). Rule thresholds are documented defaults |
| **REQ-18** | Append-only event store with the full event vocabulary; learning sessions; question-level evidence | Phase 4 | `[IMPLEMENTED]` (rebuilt) | `learning_events` (append-only), `learning_sessions`, [vocabulary.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/vocabulary.py), [store.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/events/store.py), [events.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/events.py), [EVENT_MODEL.md](EVENT_MODEL.md). Stream delivery: outbox + dispatcher; the legacy event-worker is unchanged |
| **REQ-19** | Skill-gap detection with reasons, severity from documented rules, cohort counts, and refusal on too little evidence | Phase 5 | `[IMPLEMENTED]` (rebuilt) | [gaps.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/gaps.py), [mastery.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/mastery.py) |
| **REQ-20** | Dropout & disengagement early risk detection with explained factors citing real figures | Phase 5 | `[IMPLEMENTED]` (rebuilt) | `learner_risks` (`risk_level`, `risk_details`, `recommended_actions`), [risk.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/competency/risk.py), [risk_service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/risk_service.py); scoped to the viewer's team |

---

## 5. Grounded AI Reporting & Analytics

| ID | Requirement Description | Target Phase | Status | Implemented Artifacts / Tables |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-21** | Citation validation of every claim (ids, tenant, scope, period, numbers, causation) before display | Phase 7 | `[IMPLEMENTED]` (rebuilt) | [validator.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/validator.py), `reports.claims`, `reports.rejected_claims`, [REPORTING_AI.md](REPORTING_AI.md) |
| **REQ-22** | Four distinct reporting agents and experiences (learner, manager, L&D, organization) over an evidence package with claim types and an evidence drawer | Phase 7-8 | `[IMPLEMENTED]` (rebuilt) | [builders.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/builders.py), [agent.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/agent.py), `reports`, [report-view.tsx](file:///d:/ALP-Deep_Report_AI/adaptive-lms/frontend/components/reports/report-view.tsx). Real-model quality unverified |
| **REQ-23** | Scheduled reports (weekly/monthly) generated from real data and stored as digests | Phase 8 | `[IMPLEMENTED]` (rebuilt; in-app only, **no email**) | `scheduled_reports`, `report_digests`, [reports.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/reports.py), [scheduler.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/reporting/scheduler.py) |
| **REQ-24** | BI touchpoints: structured report and analytics JSON, CSV/JSON exports, and an embeddable widget with scoped tokens | Phase 8 | `[IMPLEMENTED]` | [reports.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/reports.py), [analytics.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/analytics.py), [export.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/export.py), [embed.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/embed.py) |

---

## 6. Learner Archetypes Verification

| Archetype | Persona | Target Behaviors | Database Verification Status |
| :--- | :--- | :--- | :--- |
| **Archetype 1** | Alice Adams | High mastery (0.88-0.92), rapid progression, expert status | Verified (`mastery_score` >= 0.88, 18 data points) |
| **Archetype 2** | Bob Bennett | High completion (100%), shallow mastery (0.38), high skill gap | Verified (100% progress, 0.38 mastery, `SkillGap` severity=high) |
| **Archetype 3** | Carol Clark | High initial scores falling steeply to 0.42, 33% decline | Verified (High risk flag, score=0.74, action recommendations) |
| **Archetype 4** | Dan Davis | Disengaged, stalled at 15%, 12 days inactivity | Verified (Critical risk flag, score=0.92, 0.28 mastery) |

---

## Added requirement: login check-in (Phase 11)

| Requirement (from the product owner) | Status | Implementation | Verification |
|---|---|---|---|
| On every login a learner gets an AI-generated quiz on the content in their course | `[IMPLEMENTED]` | `app/checkin/quiz.py`, `service.py`, `api/v1/checkins.py`; login page opens `/learner/checkin`; questions verified against the material; different each time (unused passages first, earlier questions avoided) | `test_checkin_api.py`, `checkin_journey.mjs` (18/18, real Gemini) |
| A psychometric test | `[IMPLEMENTED]` (as a reflection aid, not a validated instrument) | `app/checkin/psychometric.py`: four constructs, model-written statements, reverse-keying, code scoring | `test_checkin_rules.py`, `test_checkin_api.py`; limits stated in `docs/CHECKIN.md` |
| Scores and a report based on it | `[IMPLEMENTED]` | `app/checkin/report.py`: score by lesson, review with source passages, self-report scores and change, observations, checked AI coaching note | `test_checkin_api.py`, `checkin_journey.mjs` |
| Use AI LLMs to generate it, keys from `.env` | `[IMPLEMENTED]` | `AIProvider` abstraction, task `checkin`, `AI_MODEL_CHECKIN`; Gemini key from `.env` | Live run against `gemini-3.1-flash-lite` |
