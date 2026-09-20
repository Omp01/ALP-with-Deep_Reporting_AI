# Login check-in: an AI-written quiz, a self-report, scores and a report

When a learner signs in, the app opens a **check-in**: a short quiz that a language model writes from **the learner's own course material**, and a short **self-report** (a psychometric-style questionnaire) that the model writes for the same course. Both are different every time. Submitting them produces scores and a report. The learner can skip.

Code: `services/api/app/checkin/` (`quiz.py`, `psychometric.py`, `report.py`, `service.py`), `app/api/v1/checkins.py`, `app/models/checkin.py`, migration `009_checkins.py`. Page: `frontend/app/learner/checkin/page.tsx`. Tests: `tests/foundation/unit/test_checkin_rules.py`, `tests/foundation/integration/test_checkin_api.py`, browser journey `scripts/e2e/checkin_journey.mjs`.

## The flow

1. **Login** (learners only) sets a flag and opens `/learner/checkin`, which calls `POST /checkins/start`. The call returns at once (`generating`); a background task asks the model, and the page polls `GET /checkins/{id}` (about 10 seconds with Gemini). A reload resumes the check-in in progress; a new login writes a new one and marks an abandoned one `skipped`.
2. **Which course**: the enrolled course the learner was checked in on least recently (ties at random). A learner with no enrolment is told so; a course with no published text is told so. Nothing is invented.
3. **Quiz**: a random sample of passages from the course's published lessons (their text, transcript or extracted document text), preferring passages earlier check-ins did not use, plus the earlier questions to avoid. The model writes questions **with the verbatim passage each is based on**; the ingestion validator drops any question whose quote is not actually in the material, that has duplicate options, "all of the above", and so on. Fewer than 3 surviving questions fails the check-in honestly (`ai_invalid`) instead of showing a thin quiz.
4. **Self-report**: 12 statements rated 1 to 5, three for each of four constructs the model writes about for the course subject: confidence in your ability (self-efficacy), motivation, planning and focus (self-regulation) and tension about learning. Each construct has at least one negatively worded statement.
5. **Submit**: the quiz is scored, the self-report is scored, and the report is built. The correct answers, explanations and source passages appear only now, never in the payload the learner takes the check-in from.
6. **Report**: the score with a breakdown by lesson, a review of every question (your answer, the correct one, why, the passage), the four self-report scores with a plain-language meaning and the change since the last check-in, observations, and an optional AI coaching note.

## What is computed, and what the model does

| Thing | Who does it |
|---|---|
| Quiz questions and self-report statements | The model, from the course material and the subject |
| Verification that a question's quote is in the material | Code (`ingestion/analysis.validate_questions`) |
| Quiz score, per-lesson breakdown | Code |
| Self-report scoring: reverse-keying, mean, 0-100 scale, band (low below 40, high above 70), change since last time | Code (`psychometric.py`) |
| Observations | Rules over the numbers, worded as associations ("does not establish a link") |
| Coaching note | The model, then checked: every number must exist in the scores, no causal wording, no diagnostic language (`diagnos*`, `disorder`, `therap*`, `medicat*`, ...), 20-1000 characters. One correction attempt, then it is discarded and the report says so. The scores never depend on it |

## Psychometrics: what this is and is not

It is a **reflection aid**. The four constructs are ones research on learning links to how people study, but the statements are written by a model and change every time, so this is **not a validated instrument**: it is not a diagnosis, not for selection, promotion or performance management, and a change in a score is only a rough signal (a change under `CHECKIN_CHANGE_THRESHOLD`, 10 points, is treated as ordinary variation). The page and the report say so. Nothing about health or mental health is asked; the model is told not to, and diagnostic words in its note are refused.

**Privacy: the self-report belongs to the learner.** Only the learner can read a check-in (`404` for everybody else, including their manager and administrators, and other tenants). The self-report scores are not in the `checkin_completed` event, in any team, learning-and-development or organization report, or in the embed and BI endpoints. This is tested.

## Does it change mastery?

**No.** Check-in questions are written by a model and not reviewed by a person, so they do not feed the competency engine, which only takes reviewed, graded evidence (see `COMPETENCY_ENGINE.md`). The check-in has its own score. Completing one records a `checkin_completed` event (course, correct, total, percent). Feeding a check-in into evidence, with a low weight, is a possible later decision.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `AI_MODEL_CHECKIN` | empty (provider default) | Model for the check-in. **Give it its own model when the provider limits requests per model** (see below) |
| `CHECKIN_QUESTION_COUNT` | 5 | Questions per check-in |
| `CHECKIN_MIN_QUESTIONS` | 3 | Fewer verified questions than this fails the check-in |
| `CHECKIN_ITEMS_PER_CONSTRUCT` | 3 | Statements per construct |
| `CHECKIN_MAX_PER_DAY` | 20 | Check-ins a learner may start per 24 hours (a cost guard) |
| `CHECKIN_HISTORY_AVOID` | 4 | Earlier check-ins whose questions and passages are avoided |
| `CHECKIN_GENERATION_TIMEOUT_SECONDS` | 150 | After this a generating check-in is failed |

**Cost.** One check-in is three model calls (quiz, self-report, coaching note; the note has one retry). Every learner login is a check-in, so a deployment of *n* learners logging in daily makes about 3*n* calls a day. Gemini's free tier allows about **20 requests per day per model**, which is roughly six check-ins a day for the whole deployment: enough to demonstrate, not to run. Use a billed key, a local model (`AI_PROVIDER=ollama`), or a provider with a larger allowance. A daily-quota error stops at once and says so in the check-in's failure message; it is not retried.

## API

All under `/api/v1/checkins`, all for the signed-in learner about themselves (there is no learner id anywhere):

| Method | Path | |
|---|---|---|
| `POST` | `/start` | `{fresh?: true, course_id?}` -> `202`, the check-in (`generating`, or `failed` with a reason). `fresh=false` resumes an unfinished one from the last 3 hours |
| `GET` | `/{id}` | `generating` -> `ready` (quiz options and statements, no answers) -> `completed` (report). `failed` and `skipped` carry `error.code` and `error.message` |
| `POST` | `/{id}/submit` | `{quiz: {question_id: option_id}, self_report: {statement_id: 1-5}, coaching_note?}` -> the completed check-in. `409` if already scored or not ready, `422` for ids or ratings that do not belong |
| `POST` | `/{id}/skip` | |
| `GET` | `` | Your check-ins, with quiz scores and self-report scores |

Failure codes: `no_course`, `no_material`, `ai_unavailable` (no provider, outage, quota), `ai_invalid` (the model's output did not pass verification), `timeout`, `error`, `rate_limited` (`429`).

## Not verified

- Quality of the questions and statements across models, courses and languages: verified only against Gemini (`gemini-3.1-flash-lite`) and a scripted double.
- The psychometric properties (reliability, validity) of model-written statements: none are claimed.
- Courses with very little text produce questions from the one or two passages there are; real ingested content has more.
- Video-only courses have no text until a transcript exists.
