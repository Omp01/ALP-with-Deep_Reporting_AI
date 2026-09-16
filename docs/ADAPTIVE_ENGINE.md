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
| `POST` | `/api/v1/adaptive/events` | Internal / Worker | Process telemetry event and update competency state |
| `POST` | `/api/v1/adaptive/next` | Learner (self) / Admin | Calculate adaptive next step and log decision |
| `GET` | `/api/v1/adaptive/decisions/{learner_id}` | Learner (self) / Admin | Explainable decision log with reasons |
| `GET` | `/api/v1/adaptive/competencies/{learner_id}`| Learner (self) / Admin | Live competency mastery, status, and confidence |
| `GET` | `/api/v1/adaptive/skill-gaps/{learner_id}` | Learner (self) / Admin | Individual learner skill gaps |
| `GET` | `/api/v1/adaptive/cohort-gaps/{team_id}` | Manager / Admin | Systemic team/cohort skill gap analysis |
