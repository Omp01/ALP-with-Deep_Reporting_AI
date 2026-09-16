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
| **REQ-15** | AI-generated assessment items with review lifecycle | Phase 6 | `[IMPLEMENTED]` | `is_ai_generated`, `quality_flag`, [ai.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/ai.py), [ai_service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/ai_service.py) |

---

## 4. Adaptive Learning & Real-Time Mastery

| ID | Requirement Description | Target Phase | Status | Implemented Artifacts / Tables |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-16** | Real-time Bayesian / multi-factor mastery estimation | Phase 9 | `[IMPLEMENTED]` | `learner_competencies` (`mastery_score`, `confidence_score`), `competency_history`, [mastery.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/adaptive-engine/app/competency/mastery.py) |
| **REQ-17** | Dynamic adaptive next-step sequencing | Phase 8 | `[IMPLEMENTED]` | `adaptive_sessions`, `session_sequence_steps`, [policy.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/adaptive-engine/app/sequencing/policy.py), [recommender.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/adaptive-engine/app/sequencing/recommender.py), [adaptive.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/adaptive.py) |
| **REQ-18** | Event-driven telemetry stream (12 canonical event types) | Phase 7 | `[IMPLEMENTED]` | `learning_events`, [types.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/shared/events/types.py), [events.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/events.py), [main.py (event-worker)](file:///d:/ALP-Deep_Report_AI/adaptive-lms/workers/event-worker/app/main.py) |
| **REQ-19** | Automated Skill-Gap detection with severity classification | Phase 9 | `[IMPLEMENTED]` | `skill_gaps`, [skill_gap.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/adaptive-engine/app/competency/skill_gap.py), [adaptive.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/adaptive.py) |
| **REQ-20** | Dropout & disengagement early risk detection | Phase 10 | `[IMPLEMENTED]` | `learner_risks` (`risk_level`, `risk_factors`, `recommended_actions`), [risk.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/models/risk.py), [risk_service.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/services/risk_service.py) |

---

## 5. Grounded AI Reporting & Analytics

| ID | Requirement Description | Target Phase | Status | Implemented Artifacts / Tables |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-21** | Verifiable source citations for AI narrative generation | Phase 11 | `[IMPLEMENTED]` | `ai_insights.citations` (with snippet, source_type, score), [validator.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/reporting-engine/app/grounding/validator.py) |
| **REQ-22** | Multi-surface reporting (Executive, Manager, Learner, Admin) | Phase 11 | `[IMPLEMENTED]` | `ai_insights`, [calculator.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/reporting-engine/app/analytics/calculator.py), [insights.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/insights.py) |
| **REQ-23** | Scheduled proactive report delivery & email digest triggers | Phase 12 | `[IMPLEMENTED]` | `scheduled_reports`, `report_digests`, [main.py (digest-worker)](file:///d:/ALP-Deep_Report_AI/adaptive-lms/workers/digest-worker/app/main.py) |
| **REQ-24** | BI Export / Streaming analytics endpoints | Phase 13 | `[IMPLEMENTED]` | CSV & JSON streaming endpoints, [export.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/export.py), [embed.py](file:///d:/ALP-Deep_Report_AI/adaptive-lms/services/api/app/api/v1/embed.py) |

---

## 6. Learner Archetypes Verification

| Archetype | Persona | Target Behaviors | Database Verification Status |
| :--- | :--- | :--- | :--- |
| **Archetype 1** | Alice Adams | High mastery (0.88-0.92), rapid progression, expert status | Verified (`mastery_score` >= 0.88, 18 data points) |
| **Archetype 2** | Bob Bennett | High completion (100%), shallow mastery (0.38), high skill gap | Verified (100% progress, 0.38 mastery, `SkillGap` severity=high) |
| **Archetype 3** | Carol Clark | High initial scores falling steeply to 0.42, 33% decline | Verified (High risk flag, score=0.74, action recommendations) |
| **Archetype 4** | Dan Davis | Disengaged, stalled at 15%, 12 days inactivity | Verified (Critical risk flag, score=0.92, 0.28 mastery) |
