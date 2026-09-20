/**
 * End-to-end check that real learning in a real browser is recorded as events in one session,
 * and that the recorded evidence can be seen.
 *
 * Runs against servers you start yourself (see docs/TESTING.md):
 *   API_URL  default http://localhost:8100
 *   WEB_URL  default http://localhost:3100
 *   LEARNER  default dan.learner@acme.com  (must be able to see the "Python Fundamentals" course)
 *   SCREENSHOTS  directory for PNGs (default ./e2e-screenshots)
 *
 * A learner opens a lesson, reads an article to completion, takes a quiz, hands in an assignment,
 * and leaves. Every check reads what the server stored, not what the page says. Then a learner
 * tries to forge an evidence event, and an administrator looks at the activity in the UI.
 *
 * Not covered here: video playback events. The seeded videos are YouTube embeds, which cannot play
 * without internet access; those events are covered by the API tests.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { launchBrowser } from "./cdp.mjs";

const API = process.env.API_URL ?? "http://localhost:8100";
const WEB = process.env.WEB_URL ?? "http://localhost:3100";
const LEARNER = process.env.LEARNER ?? "dan.learner@acme.com";
const SHOTS = process.env.SCREENSHOTS ?? "./e2e-screenshots";

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
}

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

const api = async (session, path, init = {}) =>
  (await fetch(`${API}/api/v1${path}`, { ...init, headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json", ...(init.headers ?? {}) } })).json();

/** Poll the server until the learner's events for this filter satisfy `done` (the browser sends in batches). */
async function eventsWhen(session, query, done, timeout = 15000) {
  const start = Date.now();
  let items = [];
  while (Date.now() - start < timeout) {
    items = (await api(session, `/events?${query}&order=asc&limit=200`)).items ?? [];
    if (done(items)) return items;
    await sleep(500);
  }
  return items;
}
const kinds = (items) => items.map((e) => e.event_type);
const count = (items, kind) => items.filter((e) => e.event_type === kind).length;

/** Open a lesson from the course outline. This is client-side navigation: the player, and its session, stay alive. */
const openViaOutline = (browser, title) =>
  browser.waitFor(`(() => {
    const button = [...document.querySelectorAll('aside[aria-label="Course contents"] button')]
      .find(b => b.innerText.split('\\n')[0].trim() === ${JSON.stringify(title)});
    if (!button) return false; button.click(); return true;
  })()`, { label: `outline: ${title}` });

const browser = await launchBrowser({ userDataDir: mkdtempSync(join(tmpdir(), "alms-e2e-events-")), port: 9555 });
try {
  const learner = await signInBrowser(browser, LEARNER);
  const courses = await api(learner, "/courses");
  const python = courses.find((c) => c.code === "PY-FUND-101");
  await api(learner, `/courses/${python.id}/enroll`, { method: "POST" }).catch(() => {});
  const overview = await api(learner, `/learning/courses/${python.id}`);
  const items = overview.modules.flatMap((m) => m.items);
  const open = (i) => i.progress_status !== "completed";
  const video = items.find((i) => i.content_type === "VIDEO" && open(i));
  const article = items.find((i) => i.content_type === "ARTICLE" && open(i));
  const quiz = items.find((i) => i.kind === "assessment" && open(i));
  const lab = items.find((i) => i.kind === "assignment" && open(i));
  if (!video || !article || !quiz || !lab) {
    throw new Error(`${LEARNER} has already completed lessons this journey needs. Use a freshly seeded database or set LEARNER.`);
  }
  const beforeAll = await api(learner, `/events?limit=200`);
  const knownIds = new Set(beforeAll.items.map((e) => e.id));

  // ------------------------------------------------------------------ open a lesson
  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${video.id}&via=outline`);
  await browser.waitFor(`!!document.querySelector('iframe')`, { timeout: 25000, label: "video lesson shown" });
  let videoEvents = await eventsWhen(learner, `content_id=${video.id}`, (e) => count(e, "lesson_opened") >= 1);
  const opened = videoEvents.find((e) => e.event_type === "lesson_opened");
  check("Opening a lesson is recorded as lesson_opened", Boolean(opened));
  check("It says how the learner got there", opened?.payload?.source === "outline", JSON.stringify(opened?.payload));
  check("The server derived the course and module itself", opened?.course_id === python.id && Boolean(opened?.module_id));

  const active = await api(learner, "/learning/sessions/active");
  const sessionId = active.session?.session_id;
  check("A learning session is open", active.active === true && Boolean(sessionId));
  check("It began in the player", active.session?.context?.source === "player");
  check("The lesson event belongs to that session", opened?.session_id === sessionId);
  await browser.screenshot(`${SHOTS}/events-01-lesson.png`);

  // ------------------------------------------------------------------ read an article to the end
  await openViaOutline(browser, article.title);
  await browser.waitFor(`!!document.querySelector('article h2')`, { label: "article renders" });
  await browser.clickText("button", "Mark as complete");
  await browser.waitFor(`T('Completed')`, { label: "reading completed" });
  const articleEvents = await eventsWhen(learner, `content_id=${article.id}`, (e) => count(e, "article_completed") >= 1 && count(e, "article_opened") >= 1 && count(e, "lesson_opened") >= 1);
  check("Opening an article is recorded", count(articleEvents, "article_opened") === 1 && count(articleEvents, "lesson_opened") === 1, kinds(articleEvents).join(", "));
  const completed = articleEvents.find((e) => e.event_type === "content_completed");
  const typed = articleEvents.find((e) => e.event_type === "article_completed");
  check("Finishing it is recorded by the server: started, completed, and its article view", count(articleEvents, "content_started") === 1 && Boolean(completed) && Boolean(typed));
  check("The article view points at the completion it refines", typed?.payload?.derived_from === completed?.id);
  check("Moving to another lesson stays in the same session", articleEvents.every((e) => e.session_id === sessionId));
  check("...and says how it got there", articleEvents.find((e) => e.event_type === "lesson_opened")?.payload?.source === "outline");

  // ------------------------------------------------------------------ take the quiz
  await openViaOutline(browser, quiz.title);
  await browser.clickText("button", "Begin Assessment");
  await browser.waitFor(`!!document.querySelector('input[type=radio]')`, { label: "questions shown" });
  const total = await browser.evaluate(`Number((document.body.innerText.match(/Question\\s+\\d+\\s+of\\s+(\\d+)/i)||[])[1] || 0)`);
  for (let i = 0; i < Math.max(total, 1); i++) {
    await browser.sleep(400); // a moment on the question, so the recorded time is not zero
    await browser.evaluate(`document.querySelector('input[type=radio]').closest('label').click(); true`);
    if (await browser.evaluate(`[...document.querySelectorAll('button')].some(b => b.innerText.includes('Finish'))`)) break;
    await browser.clickText("button", "Next");
  }
  await browser.clickText("button", "Finish");
  await browser.waitFor(`T('Score:')`, { label: "quiz graded" });

  const quizEvents = await eventsWhen(learner, `session_id=${sessionId}`, (e) => count(e, "assessment_completed") >= 1 && count(e, "question_shown") >= total);
  const answered = quizEvents.filter((e) => e.event_type === "question_answered");
  const shown = quizEvents.filter((e) => e.event_type === "question_shown");
  check("Starting the assessment is recorded", count(quizEvents, "assessment_started") === 1);
  check("Each question shown is recorded by the browser", shown.length >= total && total > 0, `${shown.length} shown, ${total} questions`);
  check("Each answer is recorded by the server as evidence", answered.length === total, `${answered.length} answered`);
  check("Every answer carries the spec's fields",
    answered.every((e) => e.question_id && e.assessment_id && "is_correct" in e.payload && e.payload.attempt_number === 1 && "difficulty" in e.payload && "error_type" in e.payload));
  check("The time on each question was measured", answered.every((e) => typeof e.payload.response_time_ms === "number" && e.payload.response_time_ms > 0),
    answered.map((e) => e.payload.response_time_ms).join(", "));
  check("A wrong answer is honestly 'unknown', a right one has no error type",
    answered.every((e) => (e.payload.is_correct ? e.payload.error_type === null : e.payload.error_type === "unknown")));
  check("The assessment completion carries the result", quizEvents.find((e) => e.event_type === "assessment_completed")?.payload?.score !== undefined);
  const order = kinds(quizEvents);
  check("They happened in order: started, shown, answered, completed",
    order.indexOf("assessment_started") < order.indexOf("question_shown") && order.indexOf("question_shown") < order.indexOf("question_answered") &&
      order.lastIndexOf("question_answered") < order.indexOf("assessment_completed"));
  await browser.screenshot(`${SHOTS}/events-02-quiz.png`);

  // ------------------------------------------------------------------ hand in the assignment
  await openViaOutline(browser, lab.title);
  await browser.waitFor(`T('Instructions')`, { label: "assignment loads" });
  await browser.type("#assignment-text", "def rate_limit(max_calls, period_seconds):\n    ...");
  await browser.clickText("button", "Submit work");
  await browser.waitFor(`T('Waiting to be graded')`, { label: "submission recorded" });
  const labEvents = await eventsWhen(learner, `session_id=${sessionId}`, (e) => count(e, "assignment_submitted") >= 1 && count(e, "assignment_opened") >= 1);
  check("Opening and handing in an assignment are both recorded", count(labEvents, "assignment_opened") >= 1 && count(labEvents, "assignment_submitted") === 1);

  // ------------------------------------------------------------------ the whole session, counted
  const detail = await api(learner, `/learning/sessions/${sessionId}`);
  check("The session summary is counted from its events", detail.summary.questions_answered === total && detail.summary.events >= 12,
    JSON.stringify(detail.summary.by_type));
  check("Exactly one session covers the whole visit", (await api(learner, `/learning/sessions?course_id=${python.id}&limit=50`)).items.filter((s) => s.started_at >= active.session.started_at).length === 1);

  // ------------------------------------------------------------------ leaving ends the session
  await browser.goto(`${WEB}/learner/dashboard`);
  await sleep(2500);
  const ended = await api(learner, `/learning/sessions/${sessionId}`);
  check("Leaving the player ends the session, and says so", ended.state === "ended" && ended.end_reason === "explicit", `${ended.state} / ${ended.end_reason}`);
  const finalEvents = (await api(learner, `/events?session_id=${sessionId}&order=asc&limit=200`)).items;
  check("Ending it is an event, last in the session", kinds(finalEvents).at(-1) === "session_completed");

  // ------------------------------------------------------------------ a learner cannot forge evidence
  const forged = await browser.evaluate(`(async () => {
    const r = await fetch(${JSON.stringify(API)} + '/api/v1/events', { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('access_token') },
      body: JSON.stringify({ event_type: 'question_answered', question_id: ${JSON.stringify(answered[0].question_id)}, payload: { is_correct: true } }) });
    return { status: r.status, body: await r.json() };
  })()`);
  check("The browser cannot claim a graded answer", forged.status === 403 && forged.body.detail.code === "server_only_event", `${forged.status}`);
  const after = (await api(learner, `/events?event_type=question_answered&limit=200`)).items;
  check("...and nothing was stored", after.filter((e) => !knownIds.has(e.id)).length === total);

  // ------------------------------------------------------------------ an administrator sees it
  await signInBrowser(browser, "admin@acme.com");
  await browser.goto(`${WEB}/admin/activity`);
  await browser.waitFor(`T('Learning Activity') && document.querySelectorAll('tbody tr').length > 0`, { label: "activity page with events", timeout: 25000 });
  check("The activity page lists recorded events", (await browser.evaluate(`document.querySelectorAll('[data-event-type]').length`)) > 0);
  check("It shows headline counts from the server", await browser.evaluate(`/Events[\\s\\S]*\\d/.test(document.body.innerText) && !T('Events —')`));
  await browser.screenshot(`${SHOTS}/events-03-activity.png`);
  await browser.clickText("button[role=tab]", "Sessions");
  await browser.waitFor(`document.querySelectorAll('tbody tr').length > 0`, { label: "sessions listed" });
  await browser.evaluate(`document.querySelector('tbody tr').click(); true`);
  await browser.waitFor(`!!document.querySelector('[data-testid=session-detail]')`, { label: "session drawer opens" });
  await browser.waitFor(`document.querySelectorAll('[data-testid=session-detail] li[data-event-type]').length > 0`, { label: "timeline loads" });
  check("Opening a session shows its timeline", await browser.evaluate(`document.querySelectorAll('[data-testid=session-detail] li[data-event-type]').length`) > 0);
  await browser.screenshot(`${SHOTS}/events-04-session.png`);

  // a learner has no window onto other people's activity
  await signInBrowser(browser, LEARNER);
  await browser.goto(`${WEB}/admin/activity`);
  await sleep(2500);
  check("A learner is not given the activity page", !(await browser.text()).includes("Learning Activity"));
  const learnerStats = await fetch(`${API}/api/v1/events/stats`, { headers: { Authorization: `Bearer ${learner.access_token}` } });
  check("...and the API refuses them the statistics", learnerStats.status === 403);
} catch (error) {
  check(`Journey completed (${error.message})`, false);
  await browser.screenshot(`${SHOTS}/events-FAILED.png`).catch(() => {});
} finally {
  const noisy = browser.consoleErrors.filter((e) => e && !/favicon|Failed to load resource|youtube|net::ERR|DevTools/i.test(e));
  check("No unexpected browser console errors", noisy.length === 0, noisy.slice(0, 3).join(" | "));
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
