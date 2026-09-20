# Demo: the whole loop in about eight minutes

Prepare once (PowerShell, repository root; see README for the first-time setup):

```powershell
python -m alembic -c database/alembic.ini upgrade head
python scripts\seed.py
python scripts\generate_demo_data.py      # synthetic learner history, run through the real engine
```

Start the API, the frontend, the storage service and a model (Ollama, or `python scripts\e2e\fake_llm_server.py 8199` for a stand-in). Every account uses the password `Password123!`.

The loop being shown: **real content -> learner interaction -> events -> evidence -> competency change -> adaptive next step -> a report in which every claim opens its evidence.**

---

## 1. Real content (2 min) — `admin@acme.com`

1. **Content -> Add Content.** Drop a real document (PDF, DOCX, TXT) or paste a YouTube link. Watch the processing steps: read, split, analyse, draft questions, index. Nothing is faked: if the model is unavailable the step says so.
2. Review the drafted questions. Each quotes the passage it came from; edit one, reject one, approve the rest. **Write a question** and choose *Short written answer*: give it an expected answer, a rubric and a competency.
3. **Publish.** The content, its competency and a quiz now exist for learners.

## 2. A learner learns; the platform records it (2 min) — `carol.learner@acme.com`

1. Open the Data Engineering course. The player shows a **Recommended** step. Open **Why am I seeing this?**: her stored answers (how many of her last answers were incorrect, which kind of mistake, her estimated mastery) are the reason. Nothing in that text is hard-coded.
2. Complete the recommended lesson. The recommendation **changes** (it now asks her to be assessed, because she completed material since her last answer). That is adaptation inside one session.
3. Take the quiz, including a written answer. The written answer is graded against the rubric; if the model is not sure, it waits for a reviewer and does **not** count.
4. **Competencies.** Each figure has **Why 29%?**: the chain of graded answers, previous and new mastery at every step, and a badge saying the chain was recomputed and matches. Watching or reading never moves mastery.

## 3. Evidence becomes explanation (2 min)

1. Still as Carol: **AI Learning Insights.** Every finding has an **Evidence N** button. Open one: the stored records it cites, with previous and new mastery.
2. Switch the model off (or untick *Use AI interpretation*): the report keeps its findings and says the interpretation is missing. A model that invents a number, an id, or a cause has that statement refused, and the refusal is listed with its reason.
3. As `marcus.manager@acme.com`: **AI Team Insights** — "N of M assessed learners are below 85%", who is stuck, who is at risk, each with evidence. No raw activity. As `admin@acme.com`: **Learning Intelligence** (content followed by better mastery, worded as an association, never as proof of cause) and **Capability Intelligence** (strengths, gaps, coverage, where risk concentrates). Four audiences, four different reports.
4. **Reports & Digests:** generate a weekly digest (stored in the app; no email is sent) and create an **embed snippet**: paste it into any page and the same skill gaps render from a scoped, expiring token.

## What to point out

- The loop is closed with real records: an event exists for every step, the mastery figure is one deterministic function of graded evidence, and the model only ever produces a *signal* or an *interpretation* that is then checked.
- Bob completed his course and is still weak; the platform says so and explains why (completion is not comprehension).
- Try to break it: ask as one learner about another (`404`), open another tenant's report (`404`), use an embed token as a login (`401`).

## Things this demo does not show (and why)

- The demo learners' history is **synthetic** (labelled `seed_history`); it goes through the real engine but is not real behaviour.
- With a real model, grading and report wording will differ from the stand-in; its quality has not been measured here.
- YouTube playback needs internet; digests are not emailed.
