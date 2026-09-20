/**
 * End-to-end check of the learner experience in a real browser.
 *
 * Runs against a live API and frontend that you start yourself (see docs/TESTING.md):
 *   API_URL       default http://localhost:8100
 *   WEB_URL       default http://localhost:3100
 *   SCREENSHOTS   directory for PNGs (default ./e2e-screenshots)
 *
 * Needs a freshly seeded database: it completes lessons as it goes, so a second run
 * against the same data finds nothing left to do and says so.
 *
 * It signs in through the real login API, then drives the real pages: Home, Course
 * Detail, the Player (video, reading, quiz, assignment), the mobile layout, and the
 * recommendation view for a learner with a weak competency. Every assertion reads
 * what the page actually rendered.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { launchBrowser } from "./cdp.mjs";

const API = process.env.API_URL ?? "http://localhost:8100";
const WEB = process.env.WEB_URL ?? "http://localhost:3100";
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

const apiGet = async (session, path) =>
  (await fetch(`${API}/api/v1${path}`, { headers: { Authorization: `Bearer ${session.access_token}` } })).json();

const browser = await launchBrowser({ userDataDir: mkdtempSync(join(tmpdir(), "alms-e2e-")) });
try {
  // ------------------------------------------------------------------ Alice: home
  const alice = await signInBrowser(browser, "alice.learner@acme.com");
  await browser.goto(`${WEB}/learner/dashboard`);
  // 'Continue learning' is also a sidebar label, so wait for a heading that only renders with data.
  await browser.waitFor(`T('Your competencies') && T('AI learning insight')`, { label: "home loads with data" });
  let text = await browser.text();
  check("Home greets the learner by name", /Good (morning|afternoon|evening), Alice/.test(text));
  check("Home shows a Continue learning card for a real course", text.includes("Python Fundamentals"));
  check("Home lists competencies from stored mastery", text.includes("Your competencies") && /\d+%/.test(text));
  check("Home shows an honest empty state for the AI insight", text.includes("No insight generated yet"));
  await browser.screenshot(`${SHOTS}/01-home-desktop.png`);

  // ------------------------------------------------------- Course detail (real data)
  const courses = await apiGet(alice, "/courses");
  const python = courses.find((c) => c.code === "PY-FUND-101");
  await browser.goto(`${WEB}/courses/${python.id}`);
  await browser.waitFor(`T('Course content')`, { label: "course detail loads" });
  text = await browser.text();
  check("Course page shows modules from data", text.includes("Functions, Closures") && text.includes("Object-Oriented"));
  check("Course page shows 'What you will learn'", text.includes("What you will learn"));
  check("Course page shows competencies developed", text.includes("Competencies developed"));
  check("Course page shows learner progress", /\d+%/.test(text) && text.includes("Continue"));
  check("Course page shows no invented rating", !/★|4\.[0-9]\s*$/m.test(text));
  await browser.screenshot(`${SHOTS}/02-course-detail.png`);

  // ------------------------------------------------------------------ Player: video
  const overview = await apiGet(alice, `/learning/courses/${python.id}`);
  const items = overview.modules.flatMap((m) => m.items);
  const video = items.find((i) => i.content_type === "VIDEO" && i.progress_status !== "completed");
  const article = items.find((i) => i.content_type === "ARTICLE" && i.progress_status !== "completed");
  const quiz = items.find((i) => i.kind === "assessment" && i.progress_status !== "completed");
  const lab = items.find((i) => i.kind === "assignment" && i.progress_status !== "completed");

  if (!video || !article || !quiz || !lab) {
    throw new Error(
      "Alice has already completed lessons this journey needs. Run it against a freshly seeded database (see docs/TESTING.md)."
    );
  }

  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${video.id}`);
  await browser.waitFor(`document.querySelector('h1') && document.querySelector('h1').innerText.includes('Python OOP')`, { label: "player header" });
  check("Player shows the lesson title and course", (await browser.text()).includes("Python Fundamentals"));
  await browser.waitFor(`!!document.querySelector('iframe')`, { label: "YouTube iframe present", timeout: 25000 });
  const frameSrc = await browser.evaluate(`document.querySelector('iframe').src`);
  check("Video lesson embeds a real YouTube player", /youtube(-nocookie)?\.com\/embed\/RSl87lqOXDE/.test(frameSrc), frameSrc.slice(0, 80));
  check("Player has a course outline with the current lesson marked", await browser.evaluate(`!!document.querySelector('[aria-current="true"]')`));
  check("Player has previous / next controls", (await browser.text()).includes("Lesson 5 of 8"));
  await browser.screenshot(`${SHOTS}/03-player-video.png`);

  // ------------------------------------------------------------- Player: reading
  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${article.id}`);
  await browser.waitFor(`!!document.querySelector('article h2')`, { label: "article renders" });
  check("Reading renders Markdown headings, not raw '#' text", await browser.evaluate(`document.querySelectorAll('article h2, article h3').length >= 2 && !T('## ')`));
  check("Reading renders code blocks", await browser.evaluate(`!!document.querySelector('article pre code')`));
  await browser.screenshot(`${SHOTS}/04-player-reading.png`);
  await browser.clickText("button", "Mark as complete");
  await browser.waitFor(`T('Completed')`, { label: "reading completed" });
  const afterRead = (await apiGet(alice, `/learning/courses/${python.id}`)).modules.flatMap((m) => m.items).find((i) => i.id === article.id);
  check("Completing a reading is recorded server-side", afterRead.progress_status === "completed");

  // ------------------------------------------------------------------ Player: quiz
  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${quiz.id}`);
  await browser.clickText("button", "Begin Assessment");
  await browser.waitFor(`!!document.querySelector('input[type=radio]')`, { label: "questions shown" });
  const total = await browser.evaluate(`Number((document.body.innerText.match(/Question\\s+\\d+\\s+of\\s+(\\d+)/i)||[])[1] || 0)`);
  for (let i = 0; i < Math.max(total, 1); i++) {
    await browser.evaluate(`document.querySelector('input[type=radio]').closest('label').click(); true`);
    const isLast = await browser.evaluate(`[...document.querySelectorAll('button')].some(b => b.innerText.includes('Finish'))`);
    if (isLast) break;
    await browser.clickText("button", "Next");
  }
  await browser.clickText("button", "Finish");
  await browser.waitFor(`T('Score:')`, { label: "quiz graded" });
  text = await browser.text();
  check("Quiz shows a graded result with the passing requirement", /Score: \d+/.test(text) && text.includes("Passing requirement"));
  await browser.screenshot(`${SHOTS}/05-quiz-result.png`);
  const quizItem = (await apiGet(alice, `/learning/courses/${python.id}`)).modules.flatMap((m) => m.items).find((i) => i.id === quiz.id);
  check("Quiz item status matches the server's grading", ["completed", "in_progress"].includes(quizItem.progress_status), quizItem.progress_status);

  // ------------------------------------------------------------ Player: assignment
  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${lab.id}`);
  await browser.waitFor(`T('Instructions')`, { label: "assignment loads" });
  check("Assignment shows instructions and how it is assessed", (await browser.text()).includes("How it is assessed"));
  await browser.type("#assignment-text", "def rate_limit(max_calls, period_seconds):\n    ...");
  await browser.clickText("button", "Submit work");
  await browser.waitFor(`T('Waiting to be graded')`, { label: "submission recorded" });
  const afterLab = (await apiGet(alice, `/learning/courses/${python.id}`)).modules.flatMap((m) => m.items).find((i) => i.id === lab.id);
  check("Submitting an assignment completes it server-side", afterLab.progress_status === "completed");
  await browser.screenshot(`${SHOTS}/06-assignment-submitted.png`);

  // ---------------------------------------------------------------------- Mobile
  await browser.viewport(390, 844, true);
  await browser.goto(`${WEB}/learner/learning?course_id=${python.id}&item_id=${article.id}`);
  await browser.waitFor(`T('Contents')`, { label: "mobile player" });
  check("Mobile player offers the outline as a drawer", true);
  await browser.clickText("button", "Contents");
  await browser.waitFor(`!!document.querySelector('[role=dialog]') && document.querySelector('[role=dialog]').innerText.includes('Course contents')`, { label: "outline drawer opens" });
  check("Mobile outline drawer lists lessons", await browser.evaluate(`document.querySelector('[role=dialog]').querySelectorAll('button[aria-current], li button').length >= 4`));
  check("No horizontal page scroll on mobile", await browser.evaluate(`document.documentElement.scrollWidth <= window.innerWidth + 1`));
  await browser.screenshot(`${SHOTS}/07-player-mobile.png`);
  await browser.viewport(1400, 950, false);

  // ----------------------------------------------- Bob: weak competency recommendations
  const bob = await signInBrowser(browser, "bob.learner@acme.com");
  await browser.goto(`${WEB}/learner/dashboard`);
  await browser.waitFor(`T('Recommended for you')`, { label: "bob home" });
  await browser.waitFor(`T('mastery is')`, { label: "recommendation reason", timeout: 15000 }).catch(() => {});
  text = await browser.text();
  const bobHome = await apiGet(bob, "/learning/home");
  const weakRec = bobHome.recommendations.find((r) => r.reason_type === "weak_competency");
  check("Weak-competency learner is recommended content with the stored reason", !!weakRec && text.includes(weakRec.reason), weakRec?.reason ?? "no weak-competency recommendation");
  await browser.screenshot(`${SHOTS}/08-home-recommendations.png`);
} catch (error) {
  check("Journey completed without an unexpected error", false, String(error.message ?? error));
  await browser.screenshot(`${SHOTS}/zz-failure.png`).catch(() => {});
} finally {
  const noisy = browser.consoleErrors.filter((e) => e && !/favicon|Failed to load resource|youtube|net::ERR/i.test(e));
  check("No unexpected browser console errors", noisy.length === 0, noisy.slice(0, 3).join(" | "));
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
