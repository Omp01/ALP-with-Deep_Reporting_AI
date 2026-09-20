# Reporting AI

Reports that explain what happened, to whom, in which competency, on what evidence, and what to consider next: for four different audiences. Every claim is traceable to stored evidence, and a claim that cannot be traced is not shown.

Code: `services/api/app/reporting/` (`package.py` evidence package, `builders.py` the four builders and their findings, `agent.py` the model, `validator.py` citation validation, `service.py` orchestration, `scheduler.py`), API `services/api/app/api/v1/reports.py`, `embed.py`, `analytics.py`. Table `reports` (migration `008_reports`). Frontend `components/reports/report-view.tsx` and four pages.

---

## 1. The pipeline

```
stored evidence (answers, updates, states, decisions, sessions, risk, content progress)
        |   queries and arithmetic only
   EVIDENCE PACKAGE  { records (each with an id), metrics (with definitions), patterns (findings with sentences), notes }
        |
   deterministic claims  (every finding, with its numbers and evidence ids)         <- always present
        |
   REPORTING AGENT (optional)  reads the compact package, returns structured claims + a summary
        |
   CITATION VALIDATION  every claim, every number, every id
        |
   stored report  (package + accepted claims + refused claims and why)
```

The model never receives a database dump. It receives the package: findings, the metrics behind them and the records they cite. It is asked to interpret and prioritise, not to compute. **A model outage costs only the interpretation**: the deterministic findings are complete on their own, and the report says so.

Cost control: no model call when the package has no findings; an identical package (same hash) for the same requester within `REPORTING_CACHE_MINUTES` reuses the stored report; the compact package is trimmed to what the findings cite; nothing is asked of the model that a query can answer (it is never asked for a mastery figure).

---

## 2. The evidence package

Every record has an id of the form `type_uuid`: `state_`, `evidence_` (a graded answer), `update_` (a mastery update with previous and new value), `decision_` (an adaptive decision), `session_`, `risk_`, `content_`, `question_`, `coverage_`; metrics are `metric_<key>`. Records carry their tenant, the learner they concern and when they apply. The whole package is stored with the report, so a citation can be opened later exactly as it was.

Metrics carry a name, value, unit, a plain-language **definition** and the records they derive from. Findings ("patterns") carry a sentence whose numbers are the metric values, a claim type, a priority, and an evidence-volume confidence.

**Confidence** on a claim is `n / (n + 3)` for `n` cited records: how much evidence stands behind it. It is not the probability that the claim is true.

### What each audience gets

| Audience | Questions it answers | Findings | What it deliberately leaves out |
|---|---|---|---|
| **Learner** | What am I good at? Where am I weak? Why? What next? How has it changed? | improved / declined / weak / strong competencies with the answers behind them, repeated typed errors, the latest adaptive recommendation, inactivity | Nothing about other learners |
| **Manager** (team) | Which skills are weak across my team? Who is stuck? Who is improving? Who is at risk? | "N of M assessed learners are below X%" per competency, declining and improving counts, learners stuck below 50% with at least four answers and no improvement, unresolved high or critical risk alerts | No event lists, no session times: no raw personal activity. Only learners in the manager's teams |
| **L&D / admin** | Which content is followed by better mastery? Which appears ineffective? Where do learners get stuck? Which competencies lack content? Which assessments give useful evidence? | Content effectiveness, questions with a high wrong-answer rate, competencies with no lesson or no assessment question | Individual learners |
| **Organization** | Which competencies are strong or weak org-wide? Where are the gaps? Which skills lack coverage? Where does risk concentrate? | Capability gaps and strengths by competency, coverage gaps, risk by team and course | Individual learners |

### Content effectiveness

For a lesson mapped to a competency, with at least `REPORTING_MIN_LEARNERS_FOR_CONTENT` (3) learners: for each completer with graded answers on both sides of the completion, the change from their mastery at completion to their mastery after their latest answer; the average is reported with the number of learners measured. It is always a `CORRELATION`, worded "showed higher subsequent mastery", followed by "This is an observed association and does not establish that the content caused it." With fewer learners it reports exposure and completion only and says it is too little to say anything about effect. It does not control for who chooses to complete content or for other learning in the period.

---

## 3. Citation validation

Every claim (ours and the model's) is checked before it is shown:

1. it cites at least one evidence id and has a valid type;
2. every cited id exists in **this report's** package (an invented id is refused);
3. every cited record's organization equals the report's (a record from another tenant is refused even if it were in the package);
4. a learner report cannot cite another learner's records, and time-bound records must fall inside the period;
5. every number in the claim text equals a value in the cited metrics or records (as itself, as a percentage, or rounded), including thresholds stated in a metric's definition; otherwise refused;
6. no causation: `CAUSAL_CLAIM` is refused (the platform never has causal evidence), and causal wording (caused, led to, resulted in, because of, due to...) in an observation or association is refused, except in a sentence saying causation is **not** established.

A model summary is held to the same numbers and wording; if it fails it is replaced by a deterministic summary and the report says so. Refused claims are stored and shown to the user with their reasons: nothing is hidden, and it is visible when a model tries to overclaim.

Claim types: `OBSERVATION`, `CORRELATION`, `PLAUSIBLE_EXPLANATION` (also used for recommendations, worded as a possibility), `CAUSAL_CLAIM`.

---

## 4. Prompt injection

The evidence package can contain learner-written text (an answer quote) and administrator-written text (question text, content titles). The package is fenced with a per-request marker and defanged, the system prompt says it is untrusted data, and the output is validated: a model that follows an injected instruction still cannot produce a claim that cites nonexistent evidence, states a number the evidence does not contain, or asserts causation. It could still choose which true findings to emphasise; that residual risk is why the deterministic findings are always shown alongside.

---

## 5. Scoping and RBAC

| Report | Who may ask | About whom |
|---|---|---|
| learner | the learner; a manager for a team member; L&D and org admins for anyone in the tenant | one learner |
| team | managers (their own teams); L&D and org admins (any team, or everyone) | members of the team |
| ld, organization | L&D and org admins | the tenant |

A stored report is readable by its requester and by anyone whose remit would have let them ask for it; otherwise `404`. All reports are tenant-scoped in the query, and evidence is opened only through its report (`/reports/{id}/evidence/{evidence_id}`), where it is checked against the report's tenant again.

---

## 6. API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/reports/generate` | `{audience, scope_id?, days?, use_ai?, force?}` returns the report: summary, accepted claims, refused claims, metrics, counts, `generated_by`, `ai_status` (`ok`, `unavailable`, `invalid`, `skipped`) |
| GET | `/api/v1/reports`, `/reports/{id}` | Your reports; one report |
| GET | `/api/v1/reports/{id}/evidence/{evidence_id}` | The evidence drawer: the cited record as stored, and which claims cite it |
| GET | `/api/v1/reports/learner`, `/team`, `/ld`, `/organization` | The evidence package as JSON, no model (for BI tools); same scoping |
| GET | `/api/v1/reports/skill-gaps`, `/risks`, `/evidence?ids=` | Structured JSON, scoped |
| GET | `/api/v1/analytics/learner/{id}`, `/team/{id}`, `/organization`, `/events`, `/competencies` | Deterministic figures; null when nothing stands behind them |
| POST/GET | `/api/v1/reports/schedules`, `/schedules/{id}/run`, `/schedules/run-due`, `/digests`, `/digest/generate`, `/digest/latest` | Scheduled digests |
| POST/GET | `/api/v1/embed/tokens`, `/embed/data`, `/embed/adaptive-reporting.js` | The embeddable widget |

---

## 7. Scheduled digests

A schedule (weekly or monthly) belongs to the person who created it and names an audience and optional scope; it can only be created for something that person may ask for, and it runs with that person's permissions at run time (an inactive owner disables it). Running it generates a report over the period and stores a digest: the summary and the accepted findings with the number of evidence records each cites. Digests are stored and shown in the app (`/manager/reports`). **No email is sent**: no mail server is configured, and the page says so. Run due schedules with `POST /reports/schedules/run-due` or set `REPORT_SCHEDULER_ENABLED=true` to run them in the API process.

---

## 8. The embeddable widget

```html
<script src="https://HOST/api/v1/embed/adaptive-reporting.js"></script>
<adaptive-report api="https://HOST/api/v1" token="..." report="skill-gaps"></adaptive-report>
```

A manager or admin mints a token (`POST /embed/tokens`) for one report (`skill-gaps`, `risks`, `summary`) and one scope (team, organization, learner). The token is a signed, expiring credential that **works only on `/embed/data`**: it is refused as a login and as a refresh token, and every request re-checks that its issuer still exists, is active and may still see that scope. The widget calls the same reporting backend as the app. Cross-origin use needs the host in `CORS_ORIGINS`. The earlier `/embed/report` took a learner id and an organization id from the URL with no authentication and returned that learner's competencies; it has been removed.

---

## 9. Limits

- **A real language model has not been run here.** Tests use a scripted model that reads the prompt the product sends; what a real model adds (or gets wrong) is unmeasured. Findings are complete without it.
- Content effectiveness is an association over completers and is confounded by who chooses to complete; the report says so and makes no causal claim. There is no experimental design.
- Numbers in a claim are validated against the cited evidence, but the validator cannot tell whether a true number is used to support a misleading emphasis.
- "Stuck", "improving" and the other patterns are documented thresholds (`builders.py`), not learned.
- Digests are not emailed.
- The package is capped in what it sends to the model; very large tenants get the highest-priority findings.
