/**
 * End-to-end check of the competency engine and written-answer grading in a real browser (Phase 5).
 *
 * Runs against servers you start yourself (see docs/TESTING.md):
 *   API_URL  default http://localhost:8100
 *   WEB_URL  default http://localhost:3100
 *   LLM_URL  default http://localhost:8199   (scripts/e2e/fake_llm_server.py: extractive analysis + the overlap grader; also used to simulate an outage)
 *   SCREENSHOTS  directory for PNGs (default ./e2e-screenshots)
 *
 * Use a freshly migrated and seeded database, with `python scripts/generate_demo_data.py` run once (it adds synthetic history
 * through the real engine). The journey adds content to the Python course.
 *
 * Journey
 *   an admin adds material, writes a short-answer question with a rubric in the review screen, and publishes
 *   -> a learner answers the quiz (multiple choice and written): the written answer is graded by the grading agent,
 *      the learner sees the grade and feedback, the answer becomes evidence
 *   -> the learner's Competencies page shows the mastery, and "Why?" opens the evidence chain, which verifies
 *   -> the grading model goes down: a second learner's written answer waits for a reviewer, is not evidence, and the
 *      attempt is not passed
 *   -> the admin grades it in "Answers to review": the attempt is finalised and the grade is evidence with full confidence
 *   -> the skill-gap and risk page states counts and reasons taken from stored evidence
 *   -> boundaries: a learner cannot open the review queue or cohort gaps; the expected answer never reaches a learner
 *
 * Every check reads what the server stored, not only what the page says.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { launchBrowser } from "./cdp.mjs";

const API = process.env.API_URL ?? "http://localhost:8100";
const WEB = process.env.WEB_URL ?? "http://localhost:3100";
const LLM = process.env.LLM_URL ?? "http://localhost:8199";
const SHOTS = process.env.SCREENSHOTS ?? "./e2e-screenshots";

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
}

const RUN = Math.random().toString(36).slice(2, 10);
const PROSE = [
  "A relational database stores data in tables that are linked by keys.",
  "An INNER JOIN returns only the rows that have matching values in both tables being combined.",
  "A LEFT JOIN returns every row from the left table and the matching rows from the right table, and it fills the columns of unmatched rows with NULL values.",
  "Choosing the wrong kind of join is the most common reason a query silently drops or duplicates rows.",
  "The join condition states which columns must match, and it is usually written with the ON keyword.",
  "A query planner may use an index on the joined columns to avoid scanning every row of both tables.",
  `The reference code of this run is ${RUN} and it appears nowhere else in the handbook.`,
].join(" ");
const QUESTION = "Explain in your own words what an inner join returns and why it can drop rows.";
const EXPECTED = "An inner join returns only the rows that have matching values in both tables, so rows without a match are dropped.";
const GOOD_ANSWER = "An inner join returns only the rows that have matching values in both tables, so any row without a match is dropped from the result.";

async function login(email) {
  const response = await fetch(`${API}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: "Password123!" }),
  });
  if (!response.ok) throw new Error(`login failed for ${email}: ${response.status}`);
  return response.json();
}

async function signInBrowser(browser, email) {
  const session = await login(email);
  await browser.goto(`${WEB}/login`);
  await browser.evaluate(
    `localStorage.setItem('access_token', ${JSON.stringify(session.access_token)}); localStorage.setItem('user', ${JSON.stringify(JSON.stringify(session.user))}); true`
  );
  return session;
}

const call = async (session, path, init = {}) => {
  const response = await fetch(`${API}/api/v1${path}`, { ...init, headers: { Authorization: `Bearer ${session.access_token}`, ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(init.headers ?? {}) } });
  let body = null;
  try { body = await response.json(); } catch { /* no body */ }
  return { status: response.status, body };
};
const api = async (session, path, init) => (await call(session, path, init)).body;

const selectValue = (browser, selector, value) =>
  browser.evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, ${JSON.stringify(value)});
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return el.value === ${JSON.stringify(value)};
  })()`);

const clickInDialog = (browser, text) =>
  browser.waitFor(`(() => {
    const dialog = document.querySelector('[role=dialog]');
    const button = dialog && [...dialog.querySelectorAll('button')].find(b => (b.innerText || '').trim() === ${JSON.stringify(text)} && !b.disabled);
    if (!button) return false; button.click(); return true;
  })()`, { label: `dialog button ${text}` });

async function until(fn, ok, timeout = 20000) {
  const start = Date.now();
  let value;
  while (Date.now() - start < timeout) {
    value = await fn();
    if (ok(value)) return value;
    await sleep(500);
  }
  return value;
}

/** Work through the quiz on screen: pick the first option of each multiple-choice question, write `answer` into written ones, submit. */
async function takeQuiz(browser, answer) {
  await browser.clickText("button", "Begin Assessment");
  await browser.waitFor(`!!document.querySelector('input[type=radio]') || !!document.querySelector('textarea[aria-label="Your answer"]')`, { label: "questions shown" });
  const total = await browser.evaluate(`Number((document.body.innerText.match(/Question\\s+\\d+\\s+of\\s+(\\d+)/i)||[])[1] || 0)`);
  for (let i = 0; i < Math.max(total, 1); i++) {
    await browser.sleep(300);
    if (await browser.evaluate(`!!document.querySelector('textarea[aria-label="Your answer"]')`)) {
      if (answer !== null) await browser.type('textarea[aria-label="Your answer"]', answer);
    } else if (answer !== null) {
      await browser.evaluate(`document.querySelector('input[type=radio]').closest('label').click(); true`);
    }
    if (await browser.evaluate(`[...document.querySelectorAll('button')].some(b => b.innerText.includes('Finish'))`)) break;
    await browser.clickText("button", "Next");
  }
  await browser.clickText("button", "Finish");
  if (answer === null) await browser.clickText("button", "Submit anyway");
  return total;
}

const browser = await launchBrowser({ userDataDir: mkdtempSync(join(tmpdir(), "alms-e2e-competency-")), port: 9666 });
try {
  const admin = await signInBrowser(browser, "admin@acme.com");
  const courses = await api(admin, "/courses");
  const python = courses.find((c) => c.code === "PY-FUND-101");
  const outline = await api(admin, `/courses/${python.id}`);
  const moduleId = (outline.modules ?? [])[0]?.id ?? (await api(admin, `/learning/courses/${python.id}`)).modules[0].id;

  // ------------------------------------------------------------------ the demo history came through the engine
  const bob = await login("bob.learner@acme.com");
  const bobStates = (await api(bob, "/mastery/me")).competencies;
  const bobFunctions = bobStates.find((c) => c.code === "python.functions");
  check("Seeded history is evidence-based: Bob's weak competency has a chain behind it", Boolean(bobFunctions) && bobFunctions.evidence_count >= 5, bobFunctions ? `${bobFunctions.mastery} from ${bobFunctions.evidence_count} answers` : "no state");
  if (bobFunctions) {
    const explained = await api(bob, `/mastery/learners/${bob.user.id}/competencies/${bobFunctions.competency_id}/explain`);
    check("...and it recomputes from that evidence", explained.verified === true && explained.chain.length === bobFunctions.evidence_count && explained.chain.every((s) => s.source_type === "seed_history"));
    check("...and is honest that it is synthetic: no real event stands behind it", explained.chain.every((s) => s.source_event_id === null));
  }
  check("Bob completed the course content yet is weak: completion is not mastery", Boolean(bobFunctions) && bobFunctions.mastery < 0.6, String(bobFunctions?.mastery));
  const alice = await login("alice.learner@acme.com");
  const aliceStates = (await api(alice, "/mastery/me")).competencies;
  check("Alice's high mastery comes from correct answers, with an improving trend from history", aliceStates.some((c) => c.mastery > 0.85 && c.trend === "improving"), aliceStates.map((c) => `${c.code} ${c.mastery} ${c.trend}`).join("; "));

  // ------------------------------------------------------------------ the admin adds material and writes a written question
  await browser.goto(`${WEB}/admin/content`);
  const form = new FormData();
  form.append("file", new Blob([PROSE], { type: "text/plain" }), `SQL Joins ${RUN}.txt`);
  form.append("module_id", moduleId);
  const ingest = await call(admin, "/admin/content/ingest/file", { method: "POST", body: form });
  check("Material is added for analysis", ingest.status === 202, `${ingest.status}`);
  const contentId = ingest.body.content_id;
  const detail = await until(() => api(admin, `/admin/content/${contentId}`), (d) => (d.candidates?.length ?? 0) >= 3 && d.job?.status !== "processing", 60000);
  check("Generated questions wait for review", detail.candidates.length >= 3 && detail.candidates.every((c) => c.status === "pending"));
  await api(admin, `/admin/content/${contentId}/candidates/status`, { method: "POST", body: JSON.stringify({ ids: detail.candidates.map((c) => c.id), status: "approved" }) });

  await browser.goto(`${WEB}/admin/content/${contentId}`);
  await browser.waitFor(`T('Processing steps')`, { label: "content page loads" });
  await browser.clickText("button[role=tab]", "Questions");
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]').length >= 3`, { label: "questions listed" });
  await browser.clickText("button", "Write a question");
  await browser.waitFor(`!!document.querySelector('#q-kind')`, { label: "editor opens with a kind selector" });
  check("The question editor offers written questions", await browser.evaluate(`[...document.querySelectorAll('#q-kind option')].some(o => o.value === 'short_answer')`));
  await selectValue(browser, "#q-kind", "short_answer");
  await browser.waitFor(`!!document.querySelector('#q-expected')`, { label: "expected answer field" });
  check("Choosing a written kind replaces the options with an answer key and rubric", await browser.evaluate(`!document.querySelector('input[aria-label="Option 1"]') && !!document.querySelector('input[aria-label="Criterion 1"]')`));
  check("It cannot be saved without a competency", await browser.evaluate(`[...document.querySelectorAll('[role=dialog] button')].find(b => b.innerText.trim() === 'Save question').disabled`)
    && (await browser.text()).includes("Choose the competency"));
  await browser.type("#q-text", QUESTION);
  await browser.type("#q-expected", EXPECTED);
  await browser.type('input[aria-label="Criterion 1"]', "Matching rows only");
  await browser.type('input[aria-label="Criterion 1 description"]', "States that only rows with a match in both tables are kept");
  const competencyOptions = await browser.evaluate(`[...document.querySelectorAll('#q-competency option')].map(o => o.value).filter(Boolean)`);
  check("The competency choices come from the analysis", competencyOptions.length > 0, competencyOptions.join(", "));
  await selectValue(browser, "#q-competency", competencyOptions[0]);
  await browser.screenshot(`${SHOTS}/comp-01-written-editor.png`);
  await clickInDialog(browser, "Save question");
  await browser.waitFor(`[...document.querySelectorAll('li[data-question-status]')].some(li => li.innerText.includes('Expected answer'))`, { label: "written question added" });
  const written = (await api(admin, `/admin/content/${contentId}`)).candidates.find((c) => c.question_type === "short_answer");
  check("The server stored it with its answer key and rubric, approved", written?.status === "approved" && written.expected_answer === EXPECTED && written.rubric?.[0]?.criterion === "Matching rows only");

  const publish = await call(admin, `/admin/content/${contentId}/publish`, { method: "POST" });
  check("Publishing turns it into a quiz question without options", publish.status === 200 && publish.body.questions_published >= 4, JSON.stringify(publish.body));

  // ------------------------------------------------------------------ a learner answers it; the grading agent grades it
  const carol = await signInBrowser(browser, "carol.learner@acme.com");
  const overview = await api(carol, `/learning/courses/${python.id}`);
  const quizItem = overview.modules.flatMap((m) => m.items).find((i) => i.title.startsWith("Check your understanding: SQL Joins") && i.title.includes(RUN));
  check("The learner sees the new quiz", Boolean(quizItem), quizItem?.title);
  const quizId = quizItem.quiz_id ?? (await api(carol, `/learning/content/${quizItem.id}`)).item?.quiz_id;
  const shownQuestions = await api(carol, `/quizzes/${quizId}/questions`);
  const shownWritten = shownQuestions.find((q) => q.question_type === "short_answer");
  check("The learner is shown the rubric but never the expected answer", Boolean(shownWritten?.rubric?.length) && !JSON.stringify(shownQuestions).includes("An inner join returns only the rows that have matching values in both tables, so rows without"));
  const carolBefore = (await api(carol, "/mastery/me")).competencies.find((c) => c.competency_id === shownWritten.competency_id)?.evidence_count ?? 0;   // a repeat run starts from what earlier runs left

  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${quizItem.id}&via=outline`);
  await browser.waitFor(`T('Begin Assessment')`, { timeout: 25000, label: "quiz intro" });
  const total = await takeQuiz(browser, GOOD_ANSWER);
  await browser.waitFor(`T('Score:')`, { label: "attempt graded" });
  const pageText = await browser.text();
  check("The learner sees the written answer graded, by AI, with feedback", pageText.includes("graded by AI") && pageText.includes("Feedback on your answer"), "");
  await browser.screenshot(`${SHOTS}/comp-02-graded.png`);

  const carolStates = (await api(carol, "/mastery/me")).competencies;
  const competency = carolStates.find((c) => c.competency_id === shownWritten.competency_id);
  check("The answers became competency evidence", Boolean(competency) && competency.evidence_count - carolBefore === total, `${competency?.name}: ${competency?.evidence_count} (was ${carolBefore}) for ${total} answers`);
  const explained = await api(carol, `/mastery/learners/${carol.user.id}/competencies/${competency.competency_id}/explain`);
  const newest = explained.chain.slice(-total);
  const graded = newest.find((s) => s.source_type === "answer_graded");
  check("The written answer's evidence carries the grader's confidence and a quote from the answer", Boolean(graded) && graded.confidence === 0.9 && GOOD_ANSWER.includes(graded.evidence_quote), graded?.evidence_quote);
  check("The multiple-choice answers are exact evidence", newest.filter((s) => s.source_type === "question_answered").every((s) => s.confidence === 1));
  check("The chain recomputes from the evidence", explained.verified === true && explained.chain.length === competency.evidence_count);

  // ------------------------------------------------------------------ the learner's Competencies page explains it
  await browser.goto(`${WEB}/learner/competencies`);
  await browser.waitFor(`!!document.querySelector('tr[data-competency]')`, { timeout: 25000, label: "competencies listed" });
  check("The Competencies page lists what the server holds", (await browser.evaluate(`document.querySelectorAll('tr[data-competency]').length`)) === carolStates.length, `${carolStates.length}`);
  const rowText = await browser.evaluate(`[...document.querySelectorAll('tr[data-competency]')].find(r => r.innerText.includes(${JSON.stringify(competency.name)})).innerText`);
  check("The row shows mastery, confidence and the amount of evidence", rowText.includes(`${Math.round(competency.mastery * 100)}%`) && rowText.includes(`${competency.evidence_count} answers`), rowText.replace(/\s+/g, " "));
  await browser.evaluate(`[...document.querySelectorAll('tr[data-competency]')].find(r => r.innerText.includes(${JSON.stringify(competency.name)})).querySelector('button').click(); true`);
  await browser.waitFor(`!!document.querySelector('[data-testid=evidence-chain]') && document.querySelectorAll('[data-step]').length > 0`, { label: "evidence chain opens" });
  check("'Why?' lists every step of the chain", (await browser.evaluate(`document.querySelectorAll('[data-step]').length`)) === competency.evidence_count);
  check("It says the chain was recomputed and matches", await browser.evaluate(`!!document.querySelector('[data-testid=chain-verified]') && T('matches')`));
  check("The written answer's quote is shown", (await browser.text()).includes(graded.evidence_quote));
  await browser.screenshot(`${SHOTS}/comp-03-why.png`);

  // ------------------------------------------------------------------ the grading model goes down: the answer waits for a person
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: true }) });
  const dan = await signInBrowser(browser, "dan.learner@acme.com");
  const gradedSteps = async () => ((await api(dan, `/mastery/learners/${dan.user.id}/competencies/${competency.competency_id}/explain`))?.chain ?? []).filter((s) => s.source_type === "answer_graded");
  const gradedBefore = (await gradedSteps()).length;
  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${quizItem.id}&via=outline`);
  await browser.waitFor(`T('Begin Assessment')`, { timeout: 25000, label: "quiz intro (Dan)" });
  await takeQuiz(browser, GOOD_ANSWER);
  await browser.waitFor(`T('Waiting for a reviewer')`, { timeout: 90000, label: "attempt waits for a reviewer" });
  check("The learner is told the answer is waiting for a reviewer, with a provisional score", (await browser.text()).includes("Provisional score"));
  await browser.screenshot(`${SHOTS}/comp-04-waiting.png`);
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: false }) });

  const danAttempts = await api(dan, `/quizzes/${quizId}/attempts`);
  const waiting = danAttempts[0];
  check("The attempt is needs_review and not passed", waiting.grading_status === "needs_review" && waiting.passed === false);
  const danAfter = (await api(dan, "/mastery/me")).competencies;
  const waitingWritten = waiting.responses.find((r) => r.grading_status === "needs_review");
  check("Nothing about the waiting answer reached mastery", Boolean(waitingWritten) && waitingWritten.score_fraction === null);
  check("...no graded-answer evidence was invented for it", (await gradedSteps()).length === gradedBefore, `${danAfter.length} competencies`);

  // ------------------------------------------------------------------ the admin grades it
  await signInBrowser(browser, "admin@acme.com");
  await browser.goto(`${WEB}/admin/grading`);
  await browser.waitFor(`document.querySelectorAll('[data-review-item]').length > 0`, { timeout: 25000, label: "review queue lists the answer" });
  const queueApi = (await api(admin, "/grading/queue")).items;
  check("The review queue shows what the server holds", (await browser.evaluate(`document.querySelectorAll('[data-review-item]').length`)) === queueApi.length, `${queueApi.length}`);
  check("It says why the answer is held", (await browser.text()).toLowerCase().includes("held because"));
  await browser.evaluate(`document.querySelector('[data-review-item] button').click(); true`);
  await browser.waitFor(`!!document.querySelector('[data-testid=review-form]')`, { label: "review form" });
  const formText = await browser.text();
  check("The reviewer sees the answer, what to look for, and that the AI gave no grade", formText.includes(GOOD_ANSWER) && formText.includes("Matching rows only") && formText.includes("It gave no grade"));
  check("A grade is required before saving", await browser.evaluate(`document.querySelector('[data-testid=save-review]').disabled`));
  await selectValue(browser, "#review-signal", "0.75");
  await browser.type("#review-feedback", "Correct: you also said why rows disappear.");
  await browser.screenshot(`${SHOTS}/comp-05-review.png`);
  await browser.evaluate(`document.querySelector('[data-testid=save-review]').click(); true`);
  await browser.waitFor(`T('Answer graded')`, { label: "review saved" });

  const finished = (await api(dan, `/quizzes/${quizId}/attempts`))[0];
  check("The attempt is now final", finished.grading_status === "graded" && finished.responses.every((r) => r.grading_status === "graded"), `${finished.score}% passed=${finished.passed}`);
  const humanEvidence = (await gradedSteps()).at(-1);
  check("The reviewer's grade is evidence with full confidence", humanEvidence?.signal === 0.75 && humanEvidence?.confidence === 1, JSON.stringify({ s: humanEvidence?.signal, c: humanEvidence?.confidence }));
  check("The learner sees the reviewer's feedback", (await api(dan, `/quizzes/${quizId}/attempts`))[0].responses.some((r) => r.feedback === "Correct: you also said why rows disappear." && r.graded_by === "human"));
  const second = await call(admin, `/grading/responses/${waitingWritten ? queueApi[0].response_id : ""}/review`, { method: "POST", body: JSON.stringify({ signal: 0.1 }) });
  check("It cannot be graded a second time", second.status === 409, `${second.status}`);

  // ------------------------------------------------------------------ skill gaps and risk
  await browser.goto(`${WEB}/admin/skill-gaps`);
  await browser.waitFor(`document.querySelectorAll('[data-gap-competency]').length > 0`, { timeout: 25000, label: "cohort gaps listed" });
  const cohort = await api(admin, "/mastery/cohort-gaps");
  check("The gaps page shows what the server computed", (await browser.evaluate(`document.querySelectorAll('[data-gap-competency]').length`)) === cohort.competencies.length, `${cohort.competencies.length} competencies`);
  const counted = await browser.evaluate(`[...document.querySelectorAll('[data-testid=gap-count]')].map(e => e.innerText)`);
  check("Each competency states 'N of M assessed learners are below X%'", counted.length > 0 && counted.every((t) => /\d+ of \d+ assessed learners? (is|are) below \d+%/.test(t)), counted[0]);
  await browser.clickText("button", "Run risk scan");
  await browser.waitFor(`T('Risk scan finished')`, { timeout: 30000, label: "scan finished" });
  await browser.clickText("button[role=tab]", "At-risk learners");
  await browser.waitFor(`document.querySelectorAll('[data-risk-learner]').length > 0`, { timeout: 15000, label: "at-risk learners listed" });
  const riskCards = await browser.evaluate(`[...document.querySelectorAll('[data-risk-learner]')].map(li => li.innerText)`);
  check("Every risk shows reasons that contain real figures", riskCards.length > 0 && riskCards.every((t) => /\d/.test(t)), riskCards[0]?.replace(/\s+/g, " ").slice(0, 160));
  const bobRisk = (await api(admin, "/risks")).find((r) => r.user_id === bob.user.id);
  check("Bob (course completed, mastery weak) is at risk because of his evidence, not his completion", Boolean(bobRisk) && bobRisk.risk_details.some((d) => d.code === "persistent_low_mastery") && bobRisk.risk_details.some((d) => d.evidence_ids.length > 0), JSON.stringify(bobRisk?.risk_details?.map((d) => d.code)));
  await browser.screenshot(`${SHOTS}/comp-06-gaps-risk.png`);

  // ------------------------------------------------------------------ boundaries
  const carolSession = await login("carol.learner@acme.com");
  check("A learner cannot open the review queue through the API", (await call(carolSession, "/grading/queue")).status === 403);
  check("...nor the cohort gaps", (await call(carolSession, "/mastery/cohort-gaps")).status === 403);
  check("...nor another learner's mastery", (await call(carolSession, `/mastery/learners/${bob.user.id}`)).status === 404);
  await signInBrowser(browser, "carol.learner@acme.com");
  await browser.goto(`${WEB}/admin/grading`);
  await sleep(2500);
  check("...and is not given the review screen", !(await browser.text()).includes("Answers to review"));
  const marcus = await login("marcus.manager@acme.com");
  check("A manager can see their team's gaps", (await call(marcus, "/mastery/cohort-gaps")).status === 200);
  check("...but cannot grade answers", (await call(marcus, "/grading/queue")).status === 403);
} catch (error) {
  check(`Journey completed (${error.message})`, false);
  await browser.screenshot(`${SHOTS}/comp-FAILED.png`).catch(() => {});
} finally {
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: false }) }).catch(() => {});
  const noisy = browser.consoleErrors.filter((e) => e && !/favicon|Failed to load resource|youtube|net::ERR|DevTools/i.test(e));
  check("No unexpected browser console errors", noisy.length === 0, noisy.slice(0, 3).join(" | "));
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
