# Learning Analytics & Psychometric Assessment Methodology

**Platform**: Adaptive AI Learning Platform (Adaptive LMS)  
**Methodology Version**: `1.0.0`  
**Effective Date**: September 2026  
**Document ID**: `LAM-SPEC-V1.0`  
**Status**: Formal Version-Controlled Technical Specification  

---

## 1. Purpose & Educational Scope

This document specifies the operational definitions, mathematical formulations, measurement constructs, data normalization techniques, and longitudinal evaluation algorithms governing the **Psychometric Learning Assessment and Reporting Framework** in the Adaptive LMS.

### 1.1 Non-Diagnostic & Ethical Boundary Statement
> [!IMPORTANT]
> **Strict Non-Clinical & Educational Boundary**  
> All psychometric items and self-reported measures collected within this platform are evaluated **strictly as learning-related metacognitive signals**. They are designed exclusively to:
> 1. Enhance learner self-awareness and metacognitive calibration.
> 2. Guide personalized revision and spaced retrieval scheduling.
> 3. Provide instructors and learning designers with aggregated content friction analytics.
>
> **Psychometric signals are NEVER treated as medical, psychiatric, personality, or psychological diagnoses.** The platform strictly prohibits diagnostic labels, personality categorizations, or clinical inferences. All reports and insights use growth-oriented, neutral educational terminology.

---

## 2. Operational Definition of "Learning"

Within this platform, **Learning** is defined as an active, multidimensional, and longitudinal progression characterized by:
1. **Knowledge Acquisition**: Demonstrated conceptual grasp measured via objective quizzes and knowledge checks.
2. **Active Comprehension**: Immediate retrieval and active recall under progressive attempt-decay constraints (AI Flashcards).
3. **Procedural & Authentic Application**: Execution of domain tasks, problem sets, and projects evaluated via structured rubrics.
4. **Knowledge Retention**: Durability of learned material measured across temporal intervals (spaced daily check-ins).
5. **Metacognitive Calibration**: The alignment between subjective confidence/perceived understanding and actual objective performance.

---

## 3. Psychometric Constructs Specification

The platform defines **10 primary learning constructs**. Unrelated constructs are never pooled without documented methodological justification.

| Construct ID | Construct Name | Construct Definition | Scale Type | Scoring Direction |
|---|---|---|---|---|
| `CONFIDENCE` | Self-Efficacy & Confidence | Learner's perceived capability to understand and execute tasks in this domain. | 5-point Likert | Higher is Favorable |
| `PERCEIVED_UNDERSTANDING` | Conceptual Clarity | Subjective appraisal of how clearly the concept was explained and understood. | 5-point Likert | Higher is Favorable |
| `COGNITIVE_EFFORT` | Cognitive Load & Effort | Mental strain or difficulty experienced in processing the instructional material. | 5-point Likert | Reverse-Keyed (Lower strain = Favorable) |
| `LEARNING_DIFFICULTY` | Perceived Complexity | The perceived difficulty of the subject matter or exercise. | 5-point Likert | Reverse-Keyed (Lower difficulty = Favorable) |
| `APPLICATION_READINESS` | Transfer & Application | Self-assessed readiness to apply the knowledge in real-world or workplace situations. | 5-point Likert | Higher is Favorable |
| `RETENTION_CONFIDENCE` | Retention Perception | Learner's confidence that they will retain and recall the concept over time. | 5-point Likert | Higher is Favorable |
| `ENGAGEMENT` | Task Engagement | Active interest, curiosity, and focus during the lesson. | 5-point Likert | Higher is Favorable |
| `SELF_ASSESSED_MASTERY` | Perceived Competence | Overall self-evaluation of topic proficiency following instruction. | 5-point Likert | Higher is Favorable |
| `REFLECTION` | Metacognitive Reflection | Evaluation of study strategies and adjustments made when encountering hurdles. | 5-point Likert | Higher is Favorable |
| `MOTIVATION` | Value & Motivation | Perceived utility, interest, and drive to master the subject matter. | 5-point Likert | Higher is Favorable |

---

## 4. Question & Scale Design

### 4.1 Response Scales
The primary instrument utilizes a calibrated 5-point Likert scale with standardized anchors:
- `1`: Strongly Disagree / Not Confident / Very Difficult / Very Low
- `2`: Disagree / Slightly Confident / Difficult / Low
- `3`: Neutral / Moderately Confident / Moderate / Moderate
- `4`: Agree / Confident / Easy / High
- `5`: Strongly Agree / Very Confident / Very Easy / Very High

### 4.2 Raw Storage & Mathematical Normalization
To prevent data distortion, the system **always stores both the raw response and the normalized derived value**. The raw response is immutable.

#### Standard Normalization (Higher Rating = Favorable)
For constructs where higher responses reflect positive learning capability (`CONFIDENCE`, `PERCEIVED_UNDERSTANDING`, `APPLICATION_READINESS`, `RETENTION_CONFIDENCE`, `ENGAGEMENT`, `SELF_ASSESSED_MASTERY`, `MOTIVATION`):
$$S_{\text{norm}} = \left( \frac{R - R_{\min}}{R_{\max} - R_{\min}} \right) \times 100$$
*Example*: A rating of $4$ on a 1–5 scale yields:
$$S_{\text{norm}} = \left( \frac{4 - 1}{5 - 1} \right) \times 100 = \frac{3}{4} \times 100 = 75.0\%$$

#### Reverse-Keyed Normalization (Lower Friction = Favorable)
For constructs where higher responses reflect cognitive strain, difficulty, or anxiety (`COGNITIVE_EFFORT`, `LEARNING_DIFFICULTY`):
$$S_{\text{norm}} = 100 - \left( \frac{R - R_{\min}}{R_{\max} - R_{\min}} \right) \times 100$$
*Example*: A rating of $4$ (High Effort / Strained) on a 1–5 scale yields:
$$S_{\text{norm}} = 100 - 75.0 = 25.0\%$$
*(Indicates higher learning friction requiring review or paced explanation).*

---

## 5. In-Course Touchpoints & Intelligent Cadence

To ensure high data quality without triggering survey fatigue, micro-prompts appear only at 7 defined educational milestones:

| Stage ID | Learning Journey Milestone | Primary Construct | Trigger Context |
|---|---|---|---|
| `before_course` | Pre-Course Readiness | `CONFIDENCE` / `MOTIVATION` | Triggered upon course enrollment or initial launch. |
| `during_course` | In-Flight Concept Check | `PERCEIVED_UNDERSTANDING` | Contextual check after major milestones. |
| `after_topic` | Key Topic Transition | `COGNITIVE_EFFORT` | Triggered at the boundary of a dense topic. |
| `after_video` | Video Lesson Completion | `PERCEIVED_UNDERSTANDING` | Triggered when video reaches 100% completion. |
| `after_assessment` | Post-Quiz / Flashcards | `CONFIDENCE` | Triggered immediately after receiving test marks. |
| `end_of_module` | Module Synthesis | `SELF_ASSESSED_MASTERY` | Triggered before advancing to the next module. |
| `end_of_course` | Course Completion | `APPLICATION_READINESS` & `RETENTION_CONFIDENCE` | Capstone reflection prior to credential issuance. |

### Throttling & Fatigue Prevention
- **Maximum Frequency**: At most 1 micro-prompt per completed lesson item.
- **Minimum Cooldown**: At least 8 minutes of active learning between consecutive prompts within the same session.
- **Dismissability**: Prompts can be answered in under 4 seconds or dismissed without penalty.

---

## 6. Objective Learning Metrics Integration

Psychometric signals are strictly paired with verified objective performance metrics:
1. **Quiz Score ($S_{\text{quiz}}$)**: Percentage score ($0 \dots 100$) on deterministic or rubric-graded assessments.
2. **Assignment Score ($S_{\text{assign}}$)**: Graded rubric evaluation ($0 \dots 100$) of authentic projects.
3. **Flashcard Attempt-Decay Marks ($S_{\text{flashcard}}$)**: Comprehension marks computed via:
   $$S_{\text{flashcard}} = \text{Max Marks} \times \left( \frac{1}{1 + 0.25 \times (A - 1)} \right) \times \text{Accuracy Factor}$$
4. **First-Attempt Accuracy ($FAA$)**: Percentage of items answered correctly on the very first try without prior failure:
   $$FAA = \frac{N_{\text{first-attempt correct}}}{N_{\text{total unique items}}} \times 100$$
5. **Retries per Item ($A$)**: Average attempt count across items.
6. **BKT Competency Mastery ($M$)**: Latent knowledge state estimated via Bayesian Knowledge Tracing ($0.0 \dots 1.0$).

---

## 7. Confidence vs. Performance Calibration

### 7.1 Confidence-Performance Gap ($\Delta_{CP}$)
The quantitative gap between subjective confidence and demonstrated performance:
$$\Delta_{CP} = S_{\text{confidence}} - S_{\text{performance}}$$
Where:
- $S_{\text{confidence}}$: Normalized self-reported confidence score ($0 \dots 100$).
- $S_{\text{performance}}$: Normalized objective performance score ($0 \dots 100$) for the corresponding topic.

### 7.2 Calibration Quadrants & Feedback Action Rules

```
                      100% High Confidence
                                |
          Quadrant II           |          Quadrant I
         (Blind Spot)           |      (Calibrated Mastery)
    High Conf / Low Perf        |      High Conf / High Perf
    Δ_CP > +20                  |      |Δ_CP| ≤ 15, Perf ≥ 75
                                |
Low Performance ----------------+----------------- High Performance
0%                              |                              100%
          Quadrant IV           |          Quadrant III
      (Accurate Struggle)       |    (Underestimated Competence)
     Low Conf / Low Perf        |       Low Conf / High Perf
     |Δ_CP| ≤ 15, Perf < 60     |       Δ_CP < -20, Perf ≥ 75
                                |
                       0% Low Confidence
```

| Quadrant | Criteria | Learning Signal Description | Automated Pedagogical Action |
|---|---|---|---|
| **I: Calibrated Mastery** | $S_{\text{perf}} \ge 75$, $\|\Delta_{CP}\| \le 15$ | Well-calibrated, robust competence. | Acknowledge mastery; recommend proceeding to advanced challenge or next module. |
| **II: Uncalibrated Confidence (Blind Spot)** | $S_{\text{perf}} < 70$, $\Delta_{CP} > +20$ | Disconnect: learner perceives mastery that objective checks do not yet substantiate. | Display neutral alert: *"Your confidence is higher than current performance on this topic. A quick review of the key video section is recommended."* Deep-link to video cue. |
| **III: Underestimated Competence** | $S_{\text{perf}} \ge 75$, $\Delta_{CP} < -20$ | Metacognitive hesitation: performance is strong, but self-efficacy is unexpectedly low. | Provide positive reinforcement: *"You demonstrated strong mastery on this topic—better than you felt! Trust your preparation."* |
| **IV: Accurate Struggle** | $S_{\text{perf}} < 60$, $\|\Delta_{CP}\| \le 15$ | High metacognitive awareness of genuine conceptual difficulty. | Provide structured remediation: break down topic into smaller foundational chunks and offer worked examples. |

---

## 8. Learning Evidence Index (LEI)

The **Learning Evidence Index (LEI)** provides a holistic, mathematically grounded measure of learning progression.

### 8.1 Mathematical Formula
$$\text{LEI} = w_1 \times S_{\text{knowledge}} + w_2 \times FAA + w_3 \times S_{\text{retention}} + w_4 \times S_{\text{application}} + w_5 \times C_{\text{alignment}}$$

Where:
- $S_{\text{knowledge}}$: Weighted objective performance across Quiz, Flashcards, and Assignments ($0 \dots 100$).
- $FAA$: First-Attempt Accuracy percentage ($0 \dots 100$).
- $S_{\text{retention}}$: Retention score measured on delayed spaced retrieval checks or daily check-ins ($0 \dots 100$).
- $S_{\text{application}}$: Score on scenario/project-based assignments ($0 \dots 100$).
- $C_{\text{alignment}}$: Metacognitive Calibration Index:
  $$C_{\text{alignment}} = \max\left(0, 100 - |\Delta_{CP}|\right)$$
- Base Weights:
  $$w_1 = 0.35, \quad w_2 = 0.25, \quad w_3 = 0.15, \quad w_4 = 0.15, \quad w_5 = 0.10$$
  $$\sum_{i=1}^5 w_i = 1.0$$

### 8.2 Dynamic Weight Rebalancing
If a curriculum does not contain assignments (e.g. video + quiz only), the weights dynamically rebalance over active components:
$$w_i^{\text{norm}} = \frac{w_i}{\sum_{j \in \text{active}} w_j}$$
Ensuring effective total weight is always exactly $100\%$ ($1.0$).

---

## 9. Longitudinal Learning Trajectory Tracking

The system records learner progression across 7 discrete stages:
$$\text{Baseline} \longrightarrow \text{Learning} \longrightarrow \text{Practice} \longrightarrow \text{Assessment} \longrightarrow \text{Revision} \longrightarrow \text{Reassessment} \longrightarrow \text{Retention}$$

Each progression event captures:
- `user_id`, `course_id`, `topic`
- `stage` (e.g. `practice`)
- `confidence_score` (normalized $0 \dots 100$)
- `performance_score` (normalized $0 \dots 100$)
- `first_attempt_acc` ($0 \dots 100$)
- `gap` ($\Delta_{CP}$)
- `alignment_quadrant` (`calibrated_mastery`, `blind_spot`, `underestimated_competence`, `accurate_struggle`)
- `timestamp`

---

## 10. Course Effectiveness Index (CFI) for Managers/Admins

To detect instructional content in need of improvement, the system computes the cohort-level **Content Friction Index (CFI)** per topic:
$$\text{CFI}_{\text{topic}} = \frac{\overline{\text{Difficulty}} + (100 - \overline{\text{Confidence}}) + (100 - \overline{\text{Performance}})}{3}$$

Where:
- $\overline{\text{Difficulty}}$: Mean learner-reported difficulty rating normalized ($0 \dots 100$, where 100 = very difficult).
- $\overline{\text{Confidence}}$: Mean learner-reported confidence ($0 \dots 100$).
- $\overline{\text{Performance}}$: Mean objective assessment score on this topic ($0 \dots 100$).

### Action Trigger
When:
$$\text{CFI}_{\text{topic}} > 70.0 \quad \text{AND} \quad N_{\text{cohort}} \ge 3$$
The topic is flagged in the Manager/Admin dashboard as:
> **"Potential Learning Content Improvement Area"**  
> *Observation*: High cognitive difficulty combined with low confidence and below-average objective performance across the team. Re-evaluating transcript clarity or adding worked practice examples is recommended.

---

## 11. Formula Versioning & Auditability

All derived calculations permanently record the methodology identifier and version:
- `LEI_FORMULA_ID = "lei_multimodal_v1"`
- `METHODOLOGY_VERSION = "1.0.0"`
- `GAP_CALCULATION_ID = "cp_gap_v1"`

### Immutability Guarantee
When a historical report is generated, it reconstructs the calculation strictly from stored parameters (`raw_response`, `normalized_score`, `formula_version`, `weights_snapshot`). If the methodology evolves to version `2.0.0`, past records retain their original version tag and calculation rationale without retroactive alteration.
