/**
 * End-to-end check of the login check-in in a real browser: sign in as a learner and get an AI-written quiz on the course material
 * plus a self-report, answer them, and read the scored report.
 *
 *   API_URL  default http://localhost:8000   WEB_URL  default http://localhost:3000   (the login page always talks to :8000)
 *   SCREENSHOTS  default ./e2e-screenshots
 *
 * Needs a seeded database and a working AI provider (this journey uses the real one configured in .env: 3 model calls per check-in).
 *
 * Journey
 *   sign in as a learner -> the app opens a check-in and a model writes it from the course -> quiz (verified questions, no answers
 *   shown) -> self-report -> report with score, coaching note, review with source passages and the self-report -> continue to the dashboard
 *   -> sign in again -> a NEW check-in with different questions -> skip it
 *   -> boundaries: a manager cannot open the learner's check-in; a manager's login does not start one
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { launchBrowser } from "./cdp.mjs";

const API = process.env.API_URL ?? "http://localhost:8000";
const WEB = process.env.WEB_URL ?? "http://localhost:3000";
const SHOTS = process.env.SCREENSHOTS ?? "./e2e-screenshots";

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
}

async function apiLogin(email) {
  const response = await fetch(`${API}/api/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: "Password123!" }) });
  if (!response.ok) throw new Error(`login failed for ${email}: ${response.status}`);
  return response.json();
}
const call = async (session, path, init = {}) => {
  const response = await fetch(`${API}/api/v1${path}`, { ...init, headers: { Authorization: `Bearer ${session.access_token}`, ...(init.body ? { "Content-Type": "application/json" } : {}) } });
  let body = null;
  try { body = await response.json(); } catch { /* no body */ }
  return { status: response.status, body };
};

const browser = await launchBrowser({ userDataDir: mkdtempSync(join(tmpdir(), "alms-e2e-checkin-")), port: 9778 });

async function signIn(email, firstName) {
  await browser.goto(`${WEB}/login`);
  await browser.evaluate(`localStorage.clear(); sessionStorage.clear(); true`);
  await browser.goto(`${WEB}/login`);
  // The persona buttons are visible before React has taken the page over, and a click before that does nothing: click until it works.
  for (let attempt = 0; attempt < 12; attempt++) {
    await browser.clickText("button", `Sign in as ${firstName}`).catch(() => {});
    await browser.sleep(1500);
    if ((await browser.evaluate(`location.pathname`)) !== "/login") return;
  }
  throw new Error(`could not sign in as ${email}`);
}
const path = () => browser.evaluate(`location.pathname`);
const currentId = () => browser.evaluate(`sessionStorage.getItem('checkin_current')`);

try {
  const carol = await apiLogin("carol.learner@acme.com");
  const manager = await apiLogin("marcus.manager@acme.com");

  // ------------------------------------------------------------------ the first login
  await signIn("carol.learner@acme.com", "Carol");
  await browser.waitFor(`location.pathname === '/learner/checkin'`, { timeout: 30000, label: "learner lands on the check-in" });
  check("A learner's login opens the check-in", (await path()) === "/learner/checkin");
  await browser.waitFor(`!!document.querySelector('[data-testid=checkin-generating]') || !!document.querySelector('[data-testid=checkin-take]')`, { timeout: 30000, label: "generating or ready" });
  await browser.screenshot(`${SHOTS}/checkin-01-generating.png`);
  await browser.waitFor(`!!document.querySelector('[data-testid=checkin-take]')`, { timeout: 150000, label: "check-in written by the model" });
  const firstId = await currentId();
  const text = await browser.text();
  const groups = await browser.evaluate(`document.querySelectorAll('[data-testid=checkin-take] [role=radiogroup]').length`);
  check("The model wrote a quiz on the course (at least 3 questions, each with options)", groups >= 3, `${groups} questions`);
  check("The correct answers are not on the page", !/correct answer/i.test(text) && !/explanation/i.test(text));
  const firstQuestions = await browser.evaluate(`[...document.querySelectorAll('[data-testid=checkin-take] [role=radiogroup]')].map(g => g.getAttribute('aria-label'))`);
  await browser.screenshot(`${SHOTS}/checkin-02-quiz.png`);

  await browser.evaluate(`document.querySelectorAll('[data-testid=checkin-take] [role=radiogroup]').forEach(g => g.querySelector('label').click()); true`);
  await browser.clickText("button", "Next");
  await browser.waitFor(`document.body.innerText.includes('reflection aid')`, { label: "self-report step" });
  const statements = await browser.evaluate(`document.querySelectorAll('[data-testid=checkin-take] [role=radiogroup]').length`);
  check("The self-report has twelve statements and says it is not a psychological test", statements === 12 && (await browser.text()).includes("not a psychological test"), `${statements} statements`);
  await browser.evaluate(`document.querySelectorAll('[data-testid=checkin-take] [role=radiogroup]').forEach(g => { const l = [...g.querySelectorAll('label')].find(x => x.innerText.trim() === 'Agree'); if (l) l.click(); }); true`);
  await browser.screenshot(`${SHOTS}/checkin-03-self-report.png`);
  await browser.clickText("button", "See my report");
  await browser.waitFor(`!!document.querySelector('[data-testid=checkin-report]')`, { timeout: 120000, label: "report" });
  await browser.screenshot(`${SHOTS}/checkin-04-report.png`);

  // ------------------------------------------------------------------ the report is the stored, scored one
  const stored = (await call(carol, `/checkins/${firstId}`)).body;
  const report = stored.report;
  const shown = await browser.evaluate(`document.querySelector('[data-testid=quiz-score]').innerText.replace(/\\s+/g, ' ')`);
  check("The score on the page is the stored score", stored.status === "completed" && shown.includes(`${report.quiz.correct} of ${report.quiz.total}`), shown);
  check("The four self-report scales are scored", (await browser.evaluate(`document.querySelectorAll('[data-testid^=construct-]').length`)) === 4 && Object.values(report.self_report).every((c) => c.scored));
  const reverseFlipped = Object.values(report.self_report).every((c) => c.score >= 0 && c.score <= 100);
  check("Scores are on a 0-100 scale", reverseFlipped);
  check("There is a coaching note, or an honest reason it is missing", (await browser.evaluate(`!!document.querySelector('[data-testid=coaching-note]')`)) || /not available|discarded/.test(await browser.text()), report.coaching_note.status);
  const review = await browser.evaluate(`document.querySelectorAll('[data-testid=checkin-report] details').length`);
  check("Every question is reviewable with its correct answer, explanation and source passage", review === report.quiz.total && report.quiz.review.every((r) => r.source_quote && r.correct_answer), `${review} reviews`);
  check("A check-in is scored once", (await call(carol, `/checkins/${firstId}/submit`, { method: "POST", body: JSON.stringify({ quiz: {}, self_report: {} }) })).status === 409);

  // ------------------------------------------------------------------ nobody else can read it
  check("A manager cannot open the learner's check-in", (await call(manager, `/checkins/${firstId}`)).status === 404);
  check("The self-report is not in the event stream", !JSON.stringify((await call(carol, `/events?event_type=checkin_completed&limit=5`)).body).includes("self_efficacy"));

  await browser.clickText("button", "Continue to my learning");
  await browser.waitFor(`location.pathname === '/learner/dashboard'`, { label: "dashboard" });
  check("Continue leads to the dashboard", (await path()) === "/learner/dashboard");

  // ------------------------------------------------------------------ the next login: a different check-in
  await signIn("carol.learner@acme.com", "Carol");
  await browser.waitFor(`location.pathname === '/learner/checkin'`, { timeout: 30000, label: "check-in again" });
  await browser.waitFor(`!!document.querySelector('[data-testid=checkin-take]')`, { timeout: 150000, label: "second check-in written" });
  const secondId = await currentId();
  const secondQuestions = await browser.evaluate(`[...document.querySelectorAll('[data-testid=checkin-take] [role=radiogroup]')].map(g => g.getAttribute('aria-label'))`);
  check("The next login gets a new check-in", secondId && secondId !== firstId);
  const repeated = secondQuestions.filter((q) => firstQuestions.includes(q));
  check("Its questions are not the ones seen before", repeated.length === 0, `${repeated.length} repeated of ${secondQuestions.length}`);
  await browser.clickText("button", "Skip for now");
  await browser.waitFor(`location.pathname === '/learner/dashboard'`, { label: "dashboard after skip" });
  const skipped = (await call(carol, `/checkins/${secondId}`)).body;
  check("Skipping is recorded, and needs no answers", skipped.status === "skipped");

  // ------------------------------------------------------------------ a manager's login is not interrupted
  await signIn("marcus.manager@acme.com", "Marcus");
  await browser.waitFor(`location.pathname === '/manager/dashboard'`, { timeout: 30000, label: "manager dashboard" });
  check("A manager's login goes to their dashboard, not a check-in", (await path()) === "/manager/dashboard");
} catch (error) {
  check(`Journey completed (${error.message})`, false);
  await browser.screenshot(`${SHOTS}/checkin-FAILED.png`).catch(() => {});
} finally {
  const noisy = browser.consoleErrors.filter((e) => e && !/favicon|Failed to load resource|youtube|net::ERR|DevTools/i.test(e));
  check("No unexpected browser console errors", noisy.length === 0, noisy.slice(0, 3).join(" | "));
  await browser.close();
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
