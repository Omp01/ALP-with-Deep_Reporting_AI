# Adaptive Engine: Competency Modelling, Adaptive Sequencing & Skill-Gap Analysis

## Architectural Overview

The **Adaptive Engine** (`services/adaptive-engine`) provides real-time learner competency state estimation and adaptive curriculum sequencing. Operating independently on port `8001`, it evaluates learner activity against pedagogical policies to personalize the learning path, prevent cognitive overload, and identify skill deficiencies.

```
                  +-------------------------------------------------+
                  |                 Learning Events                 |
                  +-------------------------------------------------+
                                           |
                                           v
                  +-------------------------------------------------+
                  |        Competency Mastery Model Engine          |
                  |  - Accuracy, Difficulty, Recency, Errors        |
                  |  - Confidence Calibration & Trend Classification|
                  +-------------------------------------------------+
                                           |
                                           v
+-----------------------------+   Pedagogical Policy   +-----------------------------+
|    Low Mastery (<0.45)      |       Evaluation       |    High Mastery (>=0.80)    |
|   -> Remediate / Step Down  | ---------------------> |    -> Advance / Step Up     |
+-----------------------------+                        +-----------------------------+
               |                                                      |
               +---------------------------+--------------------------+
                                           |
                                           v
                  +-------------------------------------------------+
                  |      Curriculum Content Recommender             |
                  |  - Selects Target Module & Matched Modality     |
                  |  - Records Decision in session_sequence_steps   |
                  +-------------------------------------------------+
```

---

## Competency Mastery Model

Mastery is computed using an evidence-based multi-factor weighted formula:

$$\text{Mastery} = \frac{w_{\text{correct}} \cdot S_{\text{acc}} + w_{\text{diff}} \cdot B_{\text{diff}} + w_{\text{recency}} \cdot R - w_{\text{error}} \cdot P_{\text{err}} + w_{\text{consist}} \cdot C_{\text{var}}}{\sum w}$$

### Hyperparameters (Configurable via Environment)
- $w_{\text{correct}} = 0.40$: Recent correctness score across attempts.
- $w_{\text{diff}} = 0.15$: Difficulty bonus ($0.8\times$ beginner, $1.0\times$ intermediate, $1.25\times$ advanced).
- $w_{\text{recency}} = 0.15$: Exponential recency factor: $e^{-\lambda \cdot \Delta t}$ with half-life $\approx 7\text{ days}$.
- $w_{\text{error}} = 0.15$: Misconception penalty for repeated identical error patterns.
- $w_{\text{consist}} = 0.15$: Consistency bonus rewards low performance variance ($1.0 - \sigma$).

### Confidence Calibration
$$\text{Confidence} = \min\left(1.0, \frac{\text{Evidence Count}}{\text{Required Evidence}}\right) \quad (\text{Default Required} = 10)$$

---

## Pedagogical Policy Engine

Decisions are deterministic and auditable:

1. **Change Modality (`change_modality`)**:
   Triggered when the learner encounters the same error category $\ge 3$ times. Re-routes content from text to video, or video to interactive practice.
2. **Acceleration (`skip`)**:
   Triggered when learner achieves $\ge 3$ consecutive correct answers with baseline mastery $\ge 0.75$.
3. **Remediation (`remediate`)**:
   Triggered when mastery $< 0.45$. Automatically steps down difficulty to `beginner` and delivers foundational review.
4. **Advancement (`advance`)**:
   Triggered when mastery $\ge 0.80$ AND confidence $\ge 0.70$. Promotes learner to the next module/competency.
5. **Revisit (`revisit`)**:
   Triggered when mastery is moderate ($0.45 \le M < 0.80$) but trajectory slope is `declining` ($<-0.05$).
6. **Standard Progression (`continue`)**:
   Steady state progress through existing sequence.

---

## Skill-Gap Detection

### Individual Learner Gaps
Evaluates all enrolled competencies:
- **Critical Deficiency**: Mastery $< 0.40$
- **High Deficiency**: Mastery $< 0.60$
- **Moderate Deficiency**: Mastery $< 0.65$ or Trend is `declining`

### Cohort & Team Systemic Analysis
Aggregates competencies across team rosters (`user_teams`):
- Computes mean mastery and confidence per competency across all learners in a cohort.
- Flags systemic gaps where average cohort mastery $< 0.70$.
- Calculates cohort coverage percentage to inform L&D interventions.

---

## REST Endpoints

| Method | Path | Auth / Role | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/adaptive/events` | Internal / Worker | **Retired in Phase 5**: acknowledges and ignores. Mastery is written only by the competency engine |
| `POST` | `/api/v1/adaptive/next` | Learner (self) / Admin | Calculate adaptive next step and log decision |
| `GET` | `/api/v1/adaptive/decisions/{learner_id}` | Learner (self) / Admin | Explainable decision log with reasons |
| `GET` | `/api/v1/adaptive/competencies/{learner_id}`| Learner (self) / Manager (team) / Admin | Served by the competency engine since Phase 5 |
| `GET` | `/api/v1/adaptive/skill-gaps/{learner_id}` | Learner (self) / Manager (team) / Admin | Served by the competency engine |
| `GET` | `/api/v1/adaptive/cohort-gaps/{team_id}` | Manager (team) / Admin | Served by the competency engine: counts per competency |

---

## Phase 6: the adaptive engine as it is now

Everything above this line describes the earlier engine (a separate service with an EMA, a multi-factor formula and a first-item recommender). It is **no longer used**. The current engine lives in the API service: `services/api/app/adaptive/` (`engine.py` the pure decision function, `service.py` gathering, storing and eventing), served at `POST /api/v1/adaptive/next` and `GET /api/v1/adaptive/decisions/{learner}`. Mastery, gaps and risk come from the competency engine (`docs/COMPETENCY_ENGINE.md`); the adaptive-engine container's `/next` is no longer called.

### Inputs (all stored, none invented)

Current mastery, confidence, trend and evidence count of the target competency (`learner_competencies`, evidence-based rows only); its recent graded answers (signal, error type, difficulty, time); the skill graph's prerequisites and their mastery; published content mapped to the competency (`content_competencies`, and the competencies of a quiz's questions) with the learner's completion and completion time; the type of the last lesson finished; assessment difficulty (the mean of its questions' difficulty) and lesson level from the ingestion analysis where one exists. The target competency is the one in the request, else the competency of the learner's latest evidence in the course, else the first one not yet assessed. **Unknown stays unknown**: an untested learner has no mastery (the old default of 0.50 is gone), and a missing difficulty is never assumed.

### Actions and rules

The first rule that applies wins; its id is stored with the decision.

| Rule | When | Action |
|---|---|---|
| `no_evidence_learn` | nothing assessed yet, and unstudied material exists | CONTINUE with it |
| `no_evidence_assess` | nothing assessed yet | ASSESS |
| `prerequisite_gap` | a prerequisite with a known mastery is below what the graph requires, and mastery is below target | REMEDIATE the prerequisite (an unassessed prerequisite does not block) |
| `repeated_error_type` | the same typed error at least 3 times in the last 6 wrong answers, and material in another format exists | CHANGE_MODALITY |
| `too_hard` | the last two answers were wrong on questions of difficulty 0.65 or more, mastery below 0.5 | EASIER (the lowest-difficulty unstudied lesson) |
| `struggling` | mastery below 0.5, latest answer wrong, no content finished since | REMEDIATE (REVISIT if everything was seen) |
| `reassess_after_content` | below target and content was completed after the last answer | ASSESS |
| `low_confidence` | confidence below 0.40 | ASSESS |
| `declining` | trend declining | REVISIT |
| `mastered_streak` | mastery 0.90 or more, confidence 0.60 or more, 3 correct in a row | SKIP ahead to material for another competency |
| `above_target` | at or above target, 80% recent accuracy, at least 3 answers | HARDER (an assessment at least as hard as the last question) |
| `default` | otherwise | CONTINUE (or says everything mapped is complete) |

Thresholds are named constants in `engine.py`. They are documented starting values, not tuned on data. A decision with no material to point at says so (`note`) instead of inventing an item.

### Why this?

Every decision returns `why`: the reason sentence, a list of evidence lines built only from the stored facts (`2 of your last 3 answers were incorrect`, `2 conceptual misunderstanding errors`, `Latest answer: ...`, `3 correct answers in a row`, the prerequisite and its mastery), the estimated mastery and confidence, the evidence ids, the rule, and what else was considered and why it did not apply. The player shows it under **Recommended** ("Why am I seeing this?"), refreshed after every completed lesson or graded quiz. Nothing in it is a template with a hard-coded fact.

### Storage and events

Each decision is a row in `adaptive_decisions` (rule, reason, and in `metadata` the facts with their evidence ids, the chosen content, what was considered, the learning session, `engine: adaptive_v1`) and an `adaptive_decision_made` event in the learner's session. You can only ask for yourself; a manager reads decisions of their team, admins of the tenant.

### Adaptation inside one session (tested)

`test_adaptive_api.py` runs it through the API: no evidence -> CONTINUE with the first lesson; lesson completed -> ASSESS; quiz answered wrongly -> REMEDIATE to a second lesson with the wrong answers as the reason; that lesson completed -> ASSESS again with "you completed ..." as the reason; correct answers -> mastery higher and the next step changes. All five decisions are stored and share one learning session.

### Limits

Content difficulty is known only for assessments (from their questions) and for ingested content with a level; hand-authored lessons have none, so EASIER and HARDER have less to choose from. There is no learning-to-rank: selection is by the rules and the course order. There are no per-question adaptive quizzes (a quiz is all or nothing). A learner who ignores a recommendation is not modelled.
