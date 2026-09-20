# The competency engine

How the platform decides what a learner knows, why it says so, and what it refuses to say.

Code: `services/api/app/competency/` (`bkt.py` the formula, `service.py` the writer, `gaps.py` and `risk.py` the rules, `insight.py` the data gathering), `services/api/app/services/assessment.py` (turns graded answers into evidence), `services/api/app/api/v1/mastery.py` (API). Migration `007_competency_engine`.

---

## 1. The loop

```
learner answers  ->  event  ->  evidence  ->  deterministic update  ->  competency state
 (graded MC, graded written,        (one row per answer,      (one function,            (mastery, confidence,
  graded assignment)                 immutable)                parameters stored)         trend, counts)
```

Three rules hold the design together:

1. **Mastery is calculated in exactly one place**: `bkt.update`. A language model may produce a *signal* for a written answer (`docs/GRADING_AGENT.md`); it never produces, adjusts or overrides a mastery figure.
2. **Every figure has a chain.** Each update stores the previous value, the new value, the evidence, the weight and the parameters used. `GET /mastery/learners/{id}/competencies/{cid}/explain` returns that chain in order; `.../verify` recomputes it from the stored evidence and compares.
3. **Evidence is immutable.** `evidence_records`, `competency_state_updates` and `grading_results` are append-only, enforced by a database trigger (`alms_append_only`), like `learning_events`.

---

## 2. What is evidence, and what is not

| Source | Evidence? | Signal | Source confidence |
|---|---|---|---|
| Multiple-choice answer (graded on submission) | yes | 1 or 0 | 1.0 |
| Written answer graded by the grading agent and accepted | yes | the grader's 0..1 | the grader's confidence (at least 0.60 to be accepted) |
| Written answer graded by a person | yes | the reviewer's 0..1 | 1.0 |
| Assignment grade | yes | score / max score | 1.0 human, 0.8 when the grade is marked machine-produced |
| A blank answer (multiple choice left empty, written answer empty) | **no** | | A blank written answer is scored 0 for the attempt, but says nothing about the skill |
| Watching a video, reading an article, marking a lesson complete | **no** | | Consumption feeds `time_on_task_seconds` only |
| A written answer waiting for review | **no** | | Nothing is applied until a person grades it |
| Numbers written by the earlier engine | **no** | | Kept in the table as `basis = 'legacy_unverified'`, never shown, replaced by the first real evidence (with a note in the chain) |

A learner with no evidence for a competency has **no mastery figure** for it. The API returns nothing rather than a default; the UI says "no evidence yet".

---

## 3. The update: Bayesian Knowledge Tracing with soft evidence (`bkt_soft_v1`)

Let `L` be the current mastery (or the prior when there is no state yet).

1. **Slip and guess are adjusted for the question**
   - `guess = clamp(g × (1.5 − d), 0.01, 0.50)`, where `g` is the platform guess (0.20) or, for multiple choice, `1 / number of options`; `d` is the difficulty in 0..1 (unknown = 0.5, no adjustment).
   - `slip = clamp(s × (0.5 + d), 0.01, 0.40)`.
   A correct answer to a hard question therefore raises mastery more (guessing it is unlikely); a wrong answer to an easy one lowers it more.
2. **Posteriors** for a correct and an incorrect observation:
   - `P(known | correct) = L(1−slip) / (L(1−slip) + (1−L)·guess)`
   - `P(known | incorrect) = L·slip / (L·slip + (1−L)(1−guess))`
3. **Soft evidence**: with signal `y` in 0..1 (0.5 = half right), `posterior = y·P(known|correct) + (1−y)·P(known|incorrect)`. A binary answer is the case `y ∈ {0, 1}`.
4. **Weight** `w = source_confidence × retry_weight^(attempt − 1)`: an unsure grader moves mastery less, and a second try at the same questions (the learner has seen them) moves it less again.
5. **Blend** `L' = w·posterior + (1−w)·L`.
6. **Learning transition** `L'' = L' + (1 − L')·learn·w`. The chance of learning at this opportunity is scaled by the same weight `w`, so evidence that carries no weight (an unsure grader, a discounted retry) cannot raise mastery just by happening. (An earlier version applied the full learning step to every answer; a run of wrong retries then climbed, which the integration tests caught.) Mastery is clamped to [0.001, 0.999].

`confidence = n_eff / (n_eff + K)` with `n_eff` the sum of weights. Confidence is **how much evidence stands behind the estimate**, not how high the estimate is: five wrong answers give a low mastery and a moderate confidence.

### Parameters (`app/core/config.py`, published at `GET /mastery/parameters`, stored with every update)

| Parameter | Default | Meaning |
|---|---|---|
| `mastery_prior` | 0.20 | Chance the skill is known before any evidence |
| `mastery_learn` | 0.15 | Chance of learning at each opportunity |
| `mastery_slip` | 0.10 | Wrong although known (before adjustment) |
| `mastery_guess` | 0.20 | Right although not known (before adjustment; multiple choice uses 1/options) |
| `mastery_retry_weight` | 0.60 | Multiplier per earlier attempt (attempt 2: ×0.6, attempt 3: ×0.36) |
| `mastery_confidence_k` | 3.0 | Evidence weight at which confidence is 0.5 |
| `mastery_trend_window` | 5 | Updates back to compare for the trend |
| `mastery_trend_min_updates` | 3 | Fewer updates: trend is `insufficient_data` |
| `mastery_trend_threshold` | 0.05 | Change needed to call the trend improving or declining |

These are defaults from the literature and common practice, **not fitted to this platform's data**. They should be revisited when there is enough real evidence to fit them; until then the honest description is "a transparent, standard model with documented parameters".

Consequence worth knowing: with a learning transition, mastery after a long run of wrong first-attempt answers levels off at a small positive figure (about 0.15) rather than reaching zero, because BKT assumes some learning happens at every opportunity. Discounted retries add almost nothing either way.

### Derived fields

- **status**: novice < 0.30 ≤ developing < 0.60 ≤ competent < 0.80 ≤ proficient < 0.90 ≤ expert. Display only; nothing is decided from it.
- **trend**: the latest mastery compared with the one `trend_window` updates earlier, from the *stored update history*. The earlier engine derived "improving" from a level (≥ 0.75) even for a learner who had not moved; the new one needs at least three updates and reports `insufficient_data` before that.
- **recent_accuracy**: weighted mean signal over the last ten pieces of evidence.
- **error_distribution**: counts by error type across wrong answers. `unknown` is a real value (objective wrong answers do not say why they are wrong).
- **time_on_task_seconds**: sum of the learner's time on content mapped to the competency (from progress, not from mastery).

---

## 4. The audit trail

For each update (`competency_state_updates`): `sequence`, `previous_mastery`, `new_mastery`, `previous_confidence`, `new_confidence`, `signal`, `weight`, `method`, `params` (all parameters plus the adjusted slip/guess and the posterior), the `evidence_id`, and a `note` (for example when an unverified figure was replaced).

For each piece of evidence (`evidence_records`): learner, competency, `source_type` (`question_answered`, `answer_graded`, `assignment_graded`, `seed_history`), the `source_event_id` into `learning_events`, the answer or submission, signal, confidence, error type, the evidence quote (written answers), difficulty, attempt number, response time, guess floor, when it happened. A composite foreign key ties the competency to the same tenant.

`explain` returns, per step, a sentence built from the stored rows (`Answer to "…": signal 1.00, difficulty 0.30. Mastery 0.20 → 0.63.`), the quote, the error type and any note. `verify` recomputes the chain from the evidence with the stored parameters and reports mismatches; a mismatch would mean a number was written outside the engine.

**Idempotence and concurrency**: the state row is locked (`FOR UPDATE`) while an update is applied, so concurrent answers for the same learner and competency form one ordered chain. Evidence for a given `source_event_id` and competency is applied once (also enforced by a partial unique index).

---

## 5. Skill gaps (`gaps.py`)

A **gap** is a competency where the learner's evidenced mastery is below the course's target (`course_competencies.target_mastery`; default 0.70 when none is set), with at least **two** pieces of evidence. With fewer, the API reports "not enough evidence" and does not call it a gap.

For a gap the engine adds explaining signals, each with the real figures:

| Signal | Rule | Points |
|---|---|---|
| Low mastery | below target; shortfall ≥ 0.40 / ≥ 0.20 / less | 3 / 2 / 1 |
| Low confidence | confidence < 0.40 | 1 |
| Negative trend | trend `declining` | 2 |
| Repeated errors | ≥ 3 incorrect answers (names the most frequent typed error if it occurs at least twice) | 2 |
| High retry rate | ≥ 40% of ≥ 3 answers were retries | 1 |
| Long time on task | more than 2× the duration of the mapped published content | 1 |
| Prerequisite blocked | a prerequisite is below the mastery the skill graph requires | 2 each |

Severity is the point total: ≥ 7 critical, ≥ 5 high, ≥ 3 medium, otherwise low. It is not "100 minus completion". Other signals alone do not make a gap: a learner above target with a declining trend is not reported as a gap.

**Cohort gaps** (`GET /mastery/cohort-gaps`) report counts per competency: "3 of 12 assessed learners are below 70%", the number declining, the lowest and the median. Never a single average that hides who is behind. Learners with too little evidence are not counted as assessed. Scope: an admin sees the organisation, a manager only the teams they manage.

---

## 6. Risk (`risk.py`)

Risk is explained, not scored by a model. Each rule that fires adds points and a sentence with the figures; the total maps to a level (≥ 8 critical, ≥ 5 high, ≥ 3 medium, otherwise low). The 0..1 `risk_score` is `points / 10` capped, kept for sorting; the reasons are the substance (`learner_risks.risk_details`, with the evidence ids behind each).

| Factor | Rule | Points |
|---|---|---|
| Persistent low mastery | competencies below 0.50 with ≥ 3 evidence and confidence ≥ 0.40 | 2 (3 for two or more) |
| Negative trend | one or more declining competencies | 2 (3 for two or more) |
| Repeated failed attempts | ≥ 2 failed, fully graded attempts at the same assessment | 1 (2 for ≥ 3) |
| High retries | ≥ 40% of ≥ 5 answers were second or later attempts | 1 |
| Long time on task | more than 2× the expected duration | 1 |
| Inactive learning | no learning event for ≥ 7 days (or since enrolment when there is none) | 2 (3 from 14 days) |
| Prerequisite gaps | a competency whose prerequisite is below the required mastery | 2 |

Inactivity uses the real timestamps of learner activity events (`lesson_opened`, `content_*`, `video_*`, `question_*`, and so on), not events the platform recorded about the learner. A learner with no evidence and no activity yet is reported with a note that most factors cannot be assessed, not as risky. Each factor maps to a recommended action (`risk.ACTIONS`).

The earlier risk code read event fields that did not exist and wrote "nominal engagement" when nothing fired. That is gone.

---

## 7. Visibility

| Role | Sees |
|---|---|
| Learner | their own states, gaps, evidence and explanations |
| Manager | themselves and the members of teams they manage (states, gaps, evidence, risk, cohort gaps) |
| L&D admin / org admin | everyone in the organisation |
| Any role in another tenant | nothing (`404`) |

Rule: `app/events/queries.py::visible_user_ids`, shared with events and sessions.

---

## 8. API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/mastery/parameters` | Method and parameters |
| GET | `/api/v1/mastery/me`, `/me/gaps` | Own states and gaps (`?course_id=`) |
| GET | `/api/v1/mastery/learners/{id}`, `.../gaps` | Visibility-scoped |
| GET | `/api/v1/mastery/learners/{id}/competencies/{cid}/explain` | The chain; `404` when there is no evidence |
| GET | `/api/v1/mastery/learners/{id}/competencies/{cid}/verify` | Recompute and compare |
| GET | `/api/v1/mastery/cohort-gaps` | Manager, L&D, org admin; `?team_id=&course_id=` |
| GET | `/api/v1/mastery/evidence/{id}` | One piece of evidence with its source (what reports will cite) |
| GET | `/api/v1/adaptive/competencies/{id}`, `/skill-gaps/{id}`, `/cohort-gaps/{team}` | Kept for existing clients; now served from the same engine |
| GET | `/api/v1/risks`, `/risks/{learner}`; POST `/risks/scan`; PUT `/risks/{id}/resolve` | Scoped by responsibility; `risk_details` carry the reasons |

---

## 9. What this does not do (yet)

- The adaptive engine's `/next` recommendation still reads competency state through its own path and its own policy; it now ignores unverified rows, but the sequencing rules are rebuilt in Phase 6.
- Mastery parameters are not fitted to data; there is no per-competency or per-learner parameter learning.
- A written answer that was accepted is not regraded if the model or rubric later changes (the grading result is immutable; a person can add a review only while the answer is waiting).
- The engine measures competency from graded interaction. It does not infer skill from time spent or completion.
- Demo/seed mastery is synthetic: it is produced by running synthetic evidence (`source_type = seed_history`) through this same engine, so it has a chain, but it is not real learner behaviour.
