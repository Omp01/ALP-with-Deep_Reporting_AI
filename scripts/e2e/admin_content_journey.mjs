/**
 * End-to-end check of the administrator's content journey in a real browser.
 *
 * Runs against servers you start yourself (see docs/TESTING.md):
 *   API_URL   default http://localhost:8100
 *   WEB_URL   default http://localhost:3100
 *   LLM_URL   default http://localhost:8199   (scripts/e2e/fake_llm_server.py; only used to simulate an outage)
 *   SCREENSHOTS  directory for PNGs (default ./e2e-screenshots)
 *
 * The AI behind the API must be a model server that answers the OpenAI-compatible protocol. Here that is the
 * extractive stand-in in fake_llm_server.py; the platform's own extraction, verification, review and publishing
 * code all run for real. Use a freshly seeded database (it adds content to the first course).
 *
 * Journey: add a document -> watch it process -> review generated questions (approve, reject, edit, write one)
 * -> edit the analysis -> publish -> a learner sees it -> unpublish -> an AI outage is reported and retried ->
 * bad input is refused -> a learner cannot open the admin screens -> the mobile layout holds.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
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

// Unique per run so a second run against the same database is not flagged as a duplicate of the first.
const RUN = Math.random().toString(36).slice(2, 10);
const PROSE_A = [
  "A relational database stores data in tables that are linked by keys.",
  "An INNER JOIN returns only the rows that have matching values in both tables being combined.",
  "A LEFT JOIN returns every row from the left table and the matching rows from the right table, and it fills the columns of unmatched rows with NULL values.",
  "Choosing the wrong kind of join is the most common reason a query silently drops or duplicates rows.",
  "The join condition states which columns must match, and it is usually written with the ON keyword.",
  "A query planner may use an index on the joined columns to avoid scanning every row of both tables.",
  `The reference code of this run is ${RUN} and it appears nowhere else in the handbook.`,
].join(" ");

const PROSE_B = [
  "A transaction groups several database operations so that they succeed or fail together as one unit.",
  "Atomicity guarantees that a transaction is applied completely or not at all when something goes wrong midway.",
  "Isolation levels decide how much one running transaction may see of the uncommitted work of another transaction.",
  "A deadlock happens when two transactions each wait for a lock the other one is holding, so neither can continue.",
  "Durability means that once a transaction has committed its changes survive a crash of the database server.",
  "Long running transactions hold locks for a long time and therefore reduce how many users can work at once.",
  `The reference code of this run is ${RUN} and it appears nowhere else in the handbook.`,
].join(" ");

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

const browser = await launchBrowser({ userDataDir: mkdtempSync(join(tmpdir(), "alms-e2e-admin-")), port: 9444 });

/** Choose a file in the (visually hidden) file input the way a browser would after the picker closes. */
const chooseFile = (name, content, type = "text/plain") =>
  browser.evaluate(`(() => {
    const input = document.querySelector('[data-testid=content-file]');
    const dt = new DataTransfer();
    dt.items.add(new File([${JSON.stringify(content)}], ${JSON.stringify(name)}, { type: ${JSON.stringify(type)} }));
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);

const selectValue = (selector, value) =>
  browser.evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, ${JSON.stringify(value)});
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return el.value === ${JSON.stringify(value)};
  })()`);

/** Click the first enabled button with this text inside the Nth question card. */
const clickInCard = (index, text) =>
  browser.waitFor(`(() => {
    const card = document.querySelectorAll('li[data-question-status]')[${index}];
    const button = card && [...card.querySelectorAll('button')].find(b => (b.innerText || '').trim().startsWith(${JSON.stringify(text)}) && !b.disabled);
    if (!button) return false; button.click(); return true;
  })()`, { label: `card ${index}: ${text}` });

const clickInDialog = (text) =>
  browser.waitFor(`(() => {
    const dialog = document.querySelector('[role=dialog]');
    const button = dialog && [...dialog.querySelectorAll('button')].find(b => (b.innerText || '').trim() === ${JSON.stringify(text)} && !b.disabled);
    if (!button) return false; button.click(); return true;
  })()`, { label: `dialog button ${text}` });

const cardCount = () => browser.evaluate(`document.querySelectorAll('li[data-question-status]').length`);
const cardStatuses = () => browser.evaluate(`[...document.querySelectorAll('li[data-question-status]')].map(c => c.dataset.questionStatus)`);
const onContentPage = `/^\\/admin\\/content\\/[0-9a-f-]{36}$/.test(location.pathname)`;

async function pickPlacement(courseId) {
  await browser.waitFor(`!!document.querySelector('#course') && document.querySelector('#course').options.length > 2`, { label: "courses load" });
  await selectValue("#course", courseId);
  await browser.waitFor(`!!document.querySelector('#module') && document.querySelectorAll('#module option').length > 2`, { label: "modules load" });
  const first = await browser.evaluate(`[...document.querySelectorAll('#module option')].find(o => o.value && o.value !== '__new__')?.value`);
  await selectValue("#module", first);
}

let admin, python;
try {
  admin = await signInBrowser(browser, "admin@acme.com");
  const courses = await apiGet(admin, "/courses");
  python = courses.find((c) => c.code === "PY-FUND-101");

  // ------------------------------------------------------------------ Content Library
  await browser.goto(`${WEB}/admin/content`);
  await browser.waitFor(`T('Content Library') && T('Add Content')`, { label: "library loads" });
  let text = await browser.text();
  check("Library lists existing content with type and status", text.includes("Python") || /video|article|quiz/i.test(text));
  check("Library has search, type, status, source and course filters",
    await browser.evaluate(`['Search content','Type','Status','Source','Course'].every(l => document.querySelector('[aria-label="'+l+'"]'))`));
  check("Sidebar links to the Content Library for admins", await browser.evaluate(`!!document.querySelector('a[href="/admin/content"]')`));
  await browser.screenshot(`${SHOTS}/admin-01-library.png`);

  // ------------------------------------------------------------------ Add content (file)
  await browser.clickText("a", "Add Content");
  await browser.waitFor(`T('Choose the source')`, { label: "wizard" });
  await browser.waitFor(`T('up to')`, { label: "capabilities load" });
  text = await browser.text();
  check("Wizard shows supported file types and the size limit", /TXT/.test(text) && /up to \d+ MB/.test(text));
  check("Wizard shows no 'AI not configured' warning when a model is configured", !text.includes("No AI provider is configured"));
  check("'Add and analyse' is disabled until a file and a place are chosen",
    await browser.evaluate(`[...document.querySelectorAll('button')].find(b => b.innerText.includes('Add and analyse')).disabled`));

  await chooseFile("SQL Joins Explained.txt", PROSE_A);
  await browser.waitFor(`T('SQL Joins Explained.txt')`, { label: "file chosen" });
  await pickPlacement(python.id);
  await browser.screenshot(`${SHOTS}/admin-02-wizard.png`);
  await browser.clickText("button", "Add and analyse");
  await browser.waitFor(onContentPage, { label: "redirect to the content page" });
  const contentId = await browser.evaluate(`location.pathname.split('/').pop()`);
  check("Submitting takes the admin to the new content's page", true, contentId);

  // ------------------------------------------------------------------ Processing -> review
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]').length >= 3`, { timeout: 60000, label: "generated questions appear" });
  text = await browser.text();
  check("The processing steps are listed with real outcomes", text.includes("Read the file") && text.includes("Draft and verify questions"));
  check("Drafted questions each quote the passage they came from",
    await browser.evaluate(`[...document.querySelectorAll('li[data-question-status]')].every(li => li.querySelector('blockquote'))`));
  check("Every drafted question is waiting for review (none pre-approved)",
    (await cardStatuses()).every((s) => s === "pending"));
  check("Publishing is offered with what it will do", await browser.evaluate(`!!document.querySelector('[data-testid=publish-panel]')`));
  await browser.screenshot(`${SHOTS}/admin-03-review-questions.png`);

  // Learners see nothing yet.
  const alice = await login("alice.learner@acme.com");
  const before = await apiGet(alice, `/learning/courses/${python.id}`);
  const titlesBefore = before.modules.flatMap((m) => m.items.map((i) => i.title));
  check("Nothing generated is visible to learners before publishing", !titlesBefore.includes("SQL Joins Explained"));

  // ------------------------------------------------------------------ Review decisions
  const total = await cardCount();
  await clickInCard(0, "Approve");
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]')[0].dataset.questionStatus === 'approved'`, { label: "first approved" });
  await clickInCard(1, "Reject");
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]')[1].dataset.questionStatus === 'rejected'`, { label: "second rejected" });
  const statuses = await cardStatuses();
  check("Approve and reject change one question each", statuses[0] === "approved" && statuses[1] === "rejected" && statuses.slice(2).every((s) => s === "pending"), statuses.join(","));

  await clickInCard(2, "Edit");
  await browser.waitFor(`!!document.querySelector('#q-text')`, { label: "edit dialog" });
  await browser.type("#q-text", "Which kind of join returns only rows with matching values in both tables?");
  await clickInDialog("Save question");
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]')[2].innerText.includes('AI draft, edited')`, { label: "edit saved" });
  check("An edited question keeps its place and is marked as edited",
    (await browser.evaluate(`document.querySelectorAll('li[data-question-status]')[2].innerText`)).includes("Which kind of join returns only rows"));

  // Invalid edit is explained before saving.
  await clickInCard(3 < total ? 3 : 2, "Edit");
  await browser.waitFor(`!!document.querySelector('#q-text')`, { label: "edit dialog 2" });
  await browser.type('input[aria-label="Option 1"]', "");
  text = await browser.text();
  check("An incomplete question cannot be saved and says why",
    text.includes("Remove or fill in empty options") &&
      (await browser.evaluate(`[...document.querySelectorAll('[role=dialog] button')].find(b => b.innerText.trim() === 'Save question').disabled`)));
  await clickInDialog("Cancel");
  await browser.waitFor(`!document.querySelector('[role=dialog]')`, { label: "dialog closed" });

  // Write a question by hand.
  const beforeWrite = await cardCount();
  await browser.clickText("button", "Write a question");
  await browser.waitFor(`!!document.querySelector('#q-text')`, { label: "write dialog" });
  await browser.type("#q-text", "What does the ON keyword introduce in a join?");
  await browser.type('input[aria-label="Option 1"]', "The join condition");
  await browser.type('input[aria-label="Option 2"]', "The sort order of the result");
  await browser.type('input[aria-label="Option 3"]', "The number of rows to return");
  await clickInDialog("Save question");
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]').length === ${beforeWrite + 1}`, { label: "manual question added" });
  const cards = await browser.evaluate(`[...document.querySelectorAll('li[data-question-status]')].map(c => ({s: c.dataset.questionStatus, t: c.innerText}))`);
  check("A question written by the admin is added, approved, and labelled as theirs",
    cards.some((c) => c.s === "approved" && c.t.includes("Written by you") && c.t.includes("What does the ON keyword")));

  // ------------------------------------------------------------------ Analysis
  await browser.clickText('button[role=tab]', "Analysis");
  await browser.waitFor(`!!document.querySelector('input[aria-label="Objective 1"]')`, { label: "analysis tab" });
  text = await browser.text();
  check("The analysis shows objectives and a competency decision to review", text.includes("Learning objectives") && text.includes("Competencies") && /Create a new competency|Use an existing competency/.test(text));
  await browser.type('input[aria-label="Objective 1"]', "Choose the correct join for a given query");
  await browser.clickText("button", "Save analysis");
  await browser.waitFor(`T('Analysis saved')`, { label: "analysis saved toast" });
  check("Edited objectives are saved and marked as edited", (await browser.text()).includes("edited by you"));
  await browser.screenshot(`${SHOTS}/admin-04-analysis.png`);

  // ------------------------------------------------------------------ Publish
  const beforePublish = await apiGet(admin, `/admin/content/${contentId}`);
  const approvedBefore = beforePublish.candidates.filter((c) => c.status === "approved").length;
  await browser.clickText("[data-testid=publish-panel] button", "Publish");
  await browser.waitFor(`T('Publish to learners?')`, { label: "publish confirmation" });
  check("Publishing asks for confirmation and states what it will do", (await browser.text()).includes("create") && (await browser.text()).includes("quiz question"));
  await browser.screenshot(`${SHOTS}/admin-05-publish-confirm.png`);
  await clickInDialog("Publish");
  await browser.waitFor(`T('Live for learners')`, { label: "published" });
  const published = await apiGet(admin, `/admin/content/${contentId}`);
  check("The server agrees the content is published", published.status === "published");
  check("Only approved questions were published", published.candidates.filter((c) => c.status === "published").length === approvedBefore && published.candidates.some((c) => c.status === "rejected"),
    `${approvedBefore} approved`);
  await browser.screenshot(`${SHOTS}/admin-06-published.png`);

  // ------------------------------------------------------------------ The learner
  const after = await apiGet(alice, `/learning/courses/${python.id}`);
  const itemsAfter = after.modules.flatMap((m) => m.items);
  const lesson = itemsAfter.find((i) => i.title === "SQL Joins Explained");
  const quiz = itemsAfter.find((i) => i.title === "Check your understanding: SQL Joins Explained");
  check("A learner now sees the lesson and its quiz in the course", Boolean(lesson) && Boolean(quiz) && quiz.kind === "assessment");
  await signInBrowser(browser, "alice.learner@acme.com");
  await browser.goto(`${WEB}/courses/${python.id}`);
  await browser.waitFor(`T('SQL Joins Explained')`, { label: "learner sees the new lesson" });
  await browser.screenshot(`${SHOTS}/admin-07-learner-view.png`);
  check("The course page shows the new lesson to the learner", (await browser.text()).includes("Check your understanding: SQL Joins Explained"));

  // A learner cannot use the admin screens.
  await browser.goto(`${WEB}/admin/content`);
  await browser.sleep(2500);
  text = await browser.text();
  check("A learner does not get the Content Library", !text.includes("Add Content") && !text.includes("Content Library"));
  check("The API refuses a learner too", (await fetch(`${API}/api/v1/admin/content`, { headers: { Authorization: `Bearer ${alice.access_token}` } })).status === 403);

  // ------------------------------------------------------------------ Unpublish
  await signInBrowser(browser, "admin@acme.com");
  await browser.goto(`${WEB}/admin/content/${contentId}`);
  await browser.waitFor(`T('Live for learners')`, { label: "admin content page" });
  await browser.clickText("[data-testid=publish-panel] button", "Unpublish");
  await browser.waitFor(`T('Removed from learners')`, { label: "unpublished toast" });
  const hidden = await apiGet(alice, `/learning/courses/${python.id}`);
  check("Unpublishing hides the lesson from learners again", !hidden.modules.flatMap((m) => m.items.map((i) => i.title)).includes("SQL Joins Explained"));

  // ------------------------------------------------------------------ Duplicates and bad input
  await browser.goto(`${WEB}/admin/content/new`);
  await browser.waitFor(`T('Choose the source')`, { label: "wizard again" });
  await chooseFile("Copy of joins.txt", PROSE_A);
  await pickPlacement(python.id);
  await browser.clickText("button", "Add and analyse");
  await browser.waitFor(`T('This looks like something you already added')`, { label: "duplicate warning" });
  check("Adding the same material again is flagged, with a way to open the original", (await browser.text()).includes("Open existing") && (await browser.text()).includes("Add anyway"));
  await browser.screenshot(`${SHOTS}/admin-08-duplicate.png`);

  await browser.goto(`${WEB}/admin/content/new`);
  await browser.waitFor(`T('Choose the source')`, { label: "wizard for bad file" });
  await chooseFile("installer.exe", "MZ binary");
  await browser.waitFor(`T('not supported')`, { label: "unsupported file message" });
  check("An unsupported file is refused before upload", await browser.evaluate(`[...document.querySelectorAll('button')].find(b => b.innerText.includes('Add and analyse')).disabled`));
  await chooseFile("legacy.doc", "old word");
  await browser.waitFor(`T('.docx')`, { label: "legacy format message" });
  check("A legacy .doc file gets an actionable message", (await browser.text()).includes("Save the file as .docx"));

  await browser.goto(`${WEB}/admin/content/new`);
  await browser.waitFor(`T('Choose the source')`, { label: "wizard for youtube" });
  await browser.clickText("button[role=tab]", "YouTube link");
  await browser.waitFor(`!!document.querySelector('#youtube-url')`, { label: "youtube field" });
  await browser.type("#youtube-url", "https://vimeo.com/12345");
  await pickPlacement(python.id);
  await browser.clickText("button", "Add and analyse");
  await browser.waitFor(`!!document.querySelector('[role=alert]')`, { label: "invalid link message" });
  const linkError = await browser.evaluate(`document.querySelector('[role=alert]')?.innerText ?? ''`);
  check("A non-YouTube link is rejected with a clear message", linkError.length > 0, linkError.replace(/\s+/g, " ").slice(0, 100));

  // ------------------------------------------------------------------ AI outage, then retry
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: true }) });
  await browser.goto(`${WEB}/admin/content/new`);
  await browser.waitFor(`T('Choose the source')`, { label: "wizard for outage" });
  await chooseFile(`Transactions ${RUN}.txt`, PROSE_B);
  await pickPlacement(python.id);
  await browser.clickText("button", "Add and analyse");
  await browser.waitFor(onContentPage, { label: "outage content page" });
  const outageId = await browser.evaluate(`location.pathname.split('/').pop()`);
  await browser.waitFor(`T('Processing did not finish')`, { timeout: 60000, label: "outage reported" });
  text = await browser.text();
  check("An AI outage is reported with its reason, not hidden", text.includes("AI provider failed") || text.includes("could not be reached") || text.includes("AI"), "");
  check("No questions were invented while the AI was down", (await cardCount()) === 0);
  check("The extracted text is still kept", (await apiGet(admin, `/admin/content/${outageId}`)).text_length > 100);
  await browser.screenshot(`${SHOTS}/admin-09-ai-outage.png`);

  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: false }) });
  await browser.clickText("button", "Retry");
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]').length >= 3`, { timeout: 60000, label: "questions after retry" });
  check("Retrying after the AI recovers completes the analysis", (await browser.text()).includes("Attempt 2"));
  await browser.screenshot(`${SHOTS}/admin-10-after-retry.png`);

  // ------------------------------------------------------------------ Library reflects it
  await browser.goto(`${WEB}/admin/content`);
  await browser.waitFor(`T(${JSON.stringify(RUN)})`, { label: "library shows new items" });
  await browser.type(`[aria-label="Search content"]`, RUN);
  await browser.waitFor(`document.querySelectorAll('tbody tr').length === 1`, { label: "search narrows the list" });
  text = await browser.text();
  check("Search narrows the library, and unreviewed questions are counted", text.includes(RUN) && /\d+ questions? to review/.test(text));

  // ------------------------------------------------------------------ Mobile
  await browser.viewport(390, 800, true);
  await browser.goto(`${WEB}/admin/content/${outageId}`);
  await browser.waitFor(`document.querySelectorAll('li[data-question-status]').length >= 3`, { label: "mobile review" });
  const overflow = await browser.evaluate(`document.documentElement.scrollWidth - window.innerWidth`);
  check("The review page does not scroll sideways on a phone", overflow <= 1, `overflow ${overflow}px`);
  await browser.screenshot(`${SHOTS}/admin-11-mobile.png`);
  await browser.viewport(1400, 950, false);

  const errors = browser.consoleErrors.filter((e) => !/favicon|Failed to load resource|DevTools/i.test(e ?? ""));
  check("No unexpected browser console errors", errors.length === 0, errors.slice(0, 2).join(" | ").slice(0, 200));
} catch (error) {
  check(`Journey completed (${error.message})`, false);
  await browser.screenshot(`${SHOTS}/admin-FAILED.png`).catch(() => {});
  console.log((await browser.text().catch(() => "")).slice(0, 1500));
} finally {
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: false }) }).catch(() => {});
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
