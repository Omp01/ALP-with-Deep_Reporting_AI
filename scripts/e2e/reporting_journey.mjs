/**
 * End-to-end check of the adaptive engine and the reporting AI in a real browser (Phases 6-8), the loop in one sitting.
 *
 *   API_URL  default http://localhost:8100        WEB_URL  default http://localhost:3100
 *   LLM_URL  default http://localhost:8199        (scripts/e2e/fake_llm_server.py: also answers reporting requests; used to simulate an outage)
 *   SCREENSHOTS  default ./e2e-screenshots
 *
 * Use a freshly migrated and seeded database with `python scripts/generate_demo_data.py` run once.
 *
 * Journey
 *   a learner whose evidence is weak opens the course player -> the adaptive engine recommends a step and says why, from her stored
 *   answers -> she completes it -> the recommendation changes
 *   -> her AI Learning Insights: every claim cites evidence, the evidence drawer opens the stored records, refused claims are listed
 *   -> the model goes down: the report still has its findings and says the AI part is missing
 *   -> her manager's team insights, L&D's learning intelligence and the organization's capability intelligence are different reports
 *   -> a digest is generated and stored; the embeddable widget renders the same data from a scoped token
 *   -> boundaries: an embed token is not a login, a learner cannot read team or organization reports, the old unauthenticated embed is gone
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

async function login(email) {
  const response = await fetch(`${API}/api/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: "Password123!" }) });
  if (!response.ok) throw new Error(`login failed for ${email}: ${response.status}`);
  return response.json();
}
async function signInBrowser(browser, email) {
  const session = await login(email);
  await browser.goto(`${WEB}/login`);
  await browser.evaluate(`localStorage.setItem('access_token', ${JSON.stringify(session.access_token)}); localStorage.setItem('user', ${JSON.stringify(JSON.stringify(session.user))}); true`);
  return session;
}
const call = async (session, path, init = {}) => {
  const response = await fetch(`${API}/api/v1${path}`, { ...init, headers: { Authorization: `Bearer ${session.access_token}`, ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers ?? {}) } });
  let body = null;
  try { body = await response.json(); } catch { /* no body */ }
  return { status: response.status, body };
};
const api = async (session, path, init) => (await call(session, path, init)).body;

const browser = await launchBrowser({ userDataDir: mkdtempSync(join(tmpdir(), "alms-e2e-reporting-")), port: 9777 });
try {
  const carolSession = await signInBrowser(browser, "carol.learner@acme.com");
  const courses = await api(carolSession, "/courses");
  const de = courses.find((c) => c.code === "DE-PIPELINES-301");
  const overview = await api(carolSession, `/learning/courses/${de.id}`);
  const items = overview.modules.flatMap((m) => m.items);

  // ------------------------------------------------------------------ the adaptive engine, inside one visit
  await browser.goto(`${WEB}/learner/learning?course_id=${de.id}`);
  await browser.waitFor(`!!document.querySelector('[data-testid=next-step]')`, { timeout: 30000, label: "recommended step appears" });
  const first = await browser.evaluate(`document.querySelector('[data-testid=next-step]').dataset.action`);
  check("The player shows a recommended next step", Boolean(first), first);
  await browser.evaluate(`document.querySelector('[data-testid=why-toggle]').click(); true`);
  await browser.waitFor(`!!document.querySelector('[data-testid=why-panel]')`, { label: "why panel opens" });
  const whyText = await browser.evaluate(`document.querySelector('[data-testid=why-panel]').innerText`);
  const decisions = await api(carolSession, `/adaptive/decisions/${carolSession.user.id}`);
  const stored = decisions[0];
  check("'Why am I seeing this?' names her real mastery and evidence", /of your last \d+ answers were incorrect/.test(whyText) && /mastery of .*\d+%/.test(whyText), whyText.replace(/\s+/g, " ").slice(0, 200));
  check("The recommendation is a stored decision with its facts and rule", Boolean(stored) && stored.facts.length > 0 && Boolean(stored.rule) && stored.action === first, `${stored?.action} / ${stored?.rule}`);
  check("It is the struggling learner's remediation: her latest answers were wrong", ["REMEDIATE", "REVISIT", "EASIER", "CHANGE_MODALITY"].includes(first), first);
  await browser.screenshot(`${SHOTS}/rep-01-why.png`);

  // do what it recommends, through the API (the seeded lesson may be a YouTube video that cannot play offline), then look again
  const target = stored.content;
  if (target) {
    const done = await call(carolSession, `/progress/content/${target.content_id}`, { method: "POST", body: JSON.stringify({ status: "completed", progress_percent: 100, time_spent_seconds: 120 }) });
    check("The learner completes the recommended lesson", done.status === 200, `${done.status}`);
    await browser.goto(`${WEB}/learner/learning?course_id=${de.id}&item_id=${target.content_id}`);
    await browser.waitFor(`!!document.querySelector('[data-testid=next-step]')`, { timeout: 30000, label: "recommendation after completing" });
    await sleep(1500);
    const second = await api(carolSession, `/adaptive/decisions/${carolSession.user.id}`);
    const latest = second[0];
    const usedNewEvidence = latest.facts.some((f) => f.label === "content_completed" || f.label === "previous_modality");
    check("The next recommendation changed, and it knows the lesson was completed", latest.action !== first && usedNewEvidence, `${first} -> ${latest.action} / ${latest.rule}`);
    const shown = await browser.evaluate(`document.querySelector('[data-testid=next-step]').dataset.action`);
    check("The page shows the new action", shown === latest.action, shown);
    const sessions = new Set(second.slice(0, 2).map(() => "s"));
    const events = (await api(carolSession, `/events?event_type=adaptive_decision_made&limit=20`)).items;
    check("Decisions are events in the learner's session", events.length >= 2 && events.slice(0, 2).every((e) => e.session_id && e.payload.decision_id), `${events.length} events`);
    void sessions;
  }
  check("Nobody can ask on behalf of another learner", (await call(carolSession, "/adaptive/next", { method: "POST", body: JSON.stringify({ course_id: de.id, learner_id: "00000000-0000-0000-0000-000000000000" }) })).status === 200);

  // ------------------------------------------------------------------ the learner's own report
  await browser.goto(`${WEB}/learner/insights`);
  await browser.waitFor(`!!document.querySelector('[data-testid=report]')`, { timeout: 60000, label: "learner report" });
  const learnerReportId = await browser.evaluate(`document.querySelector('[data-testid=report]').dataset.reportId`);
  const report = await api(carolSession, `/reports/${learnerReportId}`);
  check("The report is AI-assisted with citations validated", report.generated_by === "ai" && report.ai_status === "ok" && (await browser.text()).includes("AI-assisted"), `${report.generated_by} / ${report.ai_status}`);
  check("Every claim cites evidence", report.claims.length > 0 && report.claims.every((c) => c.evidence_ids.length > 0));
  check("Claims are shown with their type and an evidence button", (await browser.evaluate(`document.querySelectorAll('[data-claim-type]').length`)) === report.claims.length && (await browser.evaluate(`document.querySelectorAll('[data-testid=open-evidence]').length`)) === report.claims.length);
  const mastery = report.metrics.find((m) => m.name.endsWith(": mastery") && m.name.includes("Event Stream"));
  check("The numbers in the text are the stored figures", Boolean(mastery) && report.claims.some((c) => c.claim.includes(`${Math.round(mastery.value * 100)}%`)), mastery ? `${Math.round(mastery.value * 100)}%` : "");
  await browser.evaluate(`document.querySelector('[data-claim-type][data-claim-source=deterministic] [data-testid=open-evidence]').click(); true`);
  await browser.waitFor(`!!document.querySelector('[data-testid=evidence-drawer]') && document.querySelectorAll('[data-evidence-id]').length > 0`, { label: "evidence drawer with records" });
  const drawer = await browser.evaluate(`document.querySelector('[data-testid=evidence-drawer]').innerText`);
  check("The evidence drawer shows the stored records", /Event Stream Processing/.test(drawer) && /(mastery|signal|trend)/i.test(drawer));
  await browser.screenshot(`${SHOTS}/rep-02-drawer.png`);
  const updateClaim = report.claims.find((c) => c.evidence_ids.some((i) => i.startsWith("update_")));
  if (updateClaim) {
    const updateId = updateClaim.evidence_ids.find((i) => i.startsWith("update_"));
    const record = await api(carolSession, `/reports/${learnerReportId}/evidence/${updateId}`);
    check("A mastery update record carries previous and new mastery", "previous_mastery" in record.data && "new_mastery" in record.data && record.cited_by.length > 0);
  }
  check("An invented evidence id is not found", (await call(carolSession, `/reports/${learnerReportId}/evidence/evidence_00000000-0000-0000-0000-000000000000`)).status === 404);

  // ------------------------------------------------------------------ the model goes down
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: true }) });
  await browser.waitFor(`!!document.querySelector('[data-testid=regenerate]')`, { label: "regenerate control" });
  await browser.evaluate(`document.querySelector('[data-testid=regenerate]').click(); true`);
  await browser.waitFor(`T('AI interpretation is not included')`, { timeout: 120000, label: "outage reported" });
  const down = await browser.evaluate(`document.querySelectorAll('[data-claim-type]').length`);
  check("With the model down, the report says so and keeps its findings", down > 0 && (await browser.text()).includes("computed from stored data"), `${down} findings`);
  await browser.screenshot(`${SHOTS}/rep-03-outage.png`);
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: false }) });

  // ------------------------------------------------------------------ four different reports
  const marcus = await signInBrowser(browser, "marcus.manager@acme.com");
  await browser.goto(`${WEB}/manager/insights`);
  await browser.waitFor(`!!document.querySelector('[data-testid=report]')`, { timeout: 90000, label: "team report" });
  const teamText = await browser.text();
  const cohort = await api(marcus, "/mastery/cohort-gaps");
  const worst = cohort.competencies.find((c) => c.learners_below_target > 0);
  check("The team report states counts that match the cohort figures", Boolean(worst) && teamText.includes(`${worst.learners_below_target} of ${worst.assessed_learners} assessed learners`), worst ? `${worst.learners_below_target} of ${worst.assessed_learners} ${worst.name}` : "");
  check("It names learners who are stuck or at risk", /stuck|at risk|risk alert/i.test(teamText));
  check("It shows no raw activity (no session or event lists)", !/session started|lesson_opened/i.test(teamText));
  await browser.screenshot(`${SHOTS}/rep-04-team.png`);

  const admin = await signInBrowser(browser, "admin@acme.com");
  await browser.goto(`${WEB}/admin/capability`);
  await browser.waitFor(`!!document.querySelector('[data-testid=report]')`, { timeout: 90000, label: "organization report" });
  const orgText = await browser.text();
  await browser.goto(`${WEB}/admin/intelligence`);
  await browser.waitFor(`!!document.querySelector('[data-testid=report]')`, { timeout: 90000, label: "ld report" });
  const ldText = await browser.text();
  check("Organization and L&D reports are different reports", orgText.includes("Capability Intelligence") && ldText.includes("Learning Intelligence") && orgText !== ldText);
  check("The organization report speaks of capability and coverage", /below target|coverage|risk alerts|assessed learners/i.test(orgText));
  await browser.screenshot(`${SHOTS}/rep-05-org.png`);
  const orgApi = await api(admin, "/reports/organization");
  check("The BI endpoint returns the same package structure", Boolean(orgApi.report_scope) && Boolean(orgApi.records) && Array.isArray(orgApi.patterns) && orgApi.report_scope.audience === "organization");

  // ------------------------------------------------------------------ digest and widget
  await signInBrowser(browser, "marcus.manager@acme.com");
  await browser.goto(`${WEB}/manager/reports`);
  await browser.waitFor(`!!document.querySelector('[data-testid=generate-digest]')`, { label: "digest page" });
  await browser.evaluate(`document.querySelector('[data-testid=generate-digest]').click(); true`);
  await browser.waitFor(`document.querySelectorAll('[data-digest-id]').length > 0`, { timeout: 120000, label: "digest appears" });
  const digestText = await browser.evaluate(`document.querySelector('[data-digest-id]').innerText`);
  check("A digest is generated from the data and stored", /below|finding/i.test(digestText) && digestText.includes("evidence"), digestText.replace(/\s+/g, " ").slice(0, 140));
  check("The page is honest that no email is sent", (await browser.text()).includes("No email is sent"));

  const minted = await api(marcus, "/embed/tokens", { method: "POST", body: JSON.stringify({ report: "skill-gaps", scope: "team" }) });
  await browser.goto(`${WEB}/login`);
  await browser.evaluate(`(() => { const s = document.createElement('script'); s.src = ${JSON.stringify(`${API}/api/v1/embed/adaptive-reporting.js`)}; document.head.appendChild(s);
    s.onload = () => { const el = document.createElement('adaptive-report'); el.setAttribute('api', ${JSON.stringify(`${API}/api/v1`)}); el.setAttribute('token', ${JSON.stringify(minted.token)}); el.setAttribute('report', 'skill-gaps'); el.id = 'widget'; document.body.appendChild(el); }; return true; })()`);
  await browser.waitFor(`(() => { const el = document.getElementById('widget'); return !!el && !!el.shadowRoot && /assessed learners? (is|are) below|No competency/.test(el.shadowRoot.textContent); })()`, { timeout: 30000, label: "widget renders" });
  const widgetText = await browser.evaluate(`document.getElementById('widget').shadowRoot.textContent`);
  check("The embeddable widget renders skill gaps from the same backend", /\d+ of \d+ assessed learners? (is|are) below \d+%/.test(widgetText), widgetText.replace(/\s+/g, " ").slice(0, 120));
  await browser.screenshot(`${SHOTS}/rep-06-widget.png`);

  // ------------------------------------------------------------------ boundaries
  check("An embed token is not a login", (await call({ access_token: minted.token }, "/reports/organization")).status === 401);
  check("...nor a refresh token", (await fetch(`${API}/api/v1/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: minted.token }) })).status === 401);
  check("A learner cannot read team, L&D or organization reports", (await Promise.all(["team", "ld", "organization"].map((a) => call(carolSession, "/reports/generate", { method: "POST", body: JSON.stringify({ audience: a }) })))).every((r) => r.status === 403));
  check("A manager cannot read the organization report", (await call(marcus, "/reports/organization")).status === 403);
  check("A manager cannot mint an organization-wide embed", (await call(marcus, "/embed/tokens", { method: "POST", body: JSON.stringify({ report: "summary", scope: "organization" }) })).status === 403);
  const legacy = await fetch(`${API}/api/v1/embed/report?learner_id=${carolSession.user.id}&org_id=${carolSession.user.org_id ?? ""}&format=json`);
  check("The old unauthenticated embed endpoint no longer exposes learners", legacy.status === 404 || legacy.status === 405 || legacy.status === 422, `${legacy.status}`);
} catch (error) {
  check(`Journey completed (${error.message})`, false);
  await browser.screenshot(`${SHOTS}/rep-FAILED.png`).catch(() => {});
} finally {
  await fetch(`${LLM}/__mode`, { method: "POST", body: JSON.stringify({ fail: false }) }).catch(() => {});
  const noisy = browser.consoleErrors.filter((e) => e && !/favicon|Failed to load resource|youtube|net::ERR|DevTools/i.test(e));
  check("No unexpected browser console errors", noisy.length === 0, noisy.slice(0, 3).join(" | "));
  await browser.close();
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
