/**
 * Checks the demo helper page (frontend/public/embed-demo.html): a snippet minted by a manager, pasted into a page served from the
 * allowed origin, renders the team's skill gaps. Needs the running app (API :8000, web :3000) and demo data.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { launchBrowser } from "./cdp.mjs";

const API = process.env.API_URL ?? "http://localhost:8000";
const WEB = process.env.WEB_URL ?? "http://localhost:3000";

const login = await (await fetch(`${API}/api/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "marcus.manager@acme.com", password: "Password123!" }) })).json();
const minted = await (await fetch(`${API}/api/v1/embed/tokens`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${login.access_token}` }, body: JSON.stringify({ report: "skill-gaps", scope: "team" }) })).json();

const browser = await launchBrowser({ userDataDir: mkdtempSync(join(tmpdir(), "alms-embed-")), port: 9779 });
let ok = false;
try {
  await browser.goto(`${WEB}/embed-demo.html`);
  await browser.evaluate(`document.getElementById('snippet').value = ${JSON.stringify(minted.snippet)}; document.getElementById('render').click(); true`);
  await browser.waitFor(`(() => { const el = document.querySelector('adaptive-report'); return !!el && !!el.shadowRoot && /assessed learners? (is|are) below|No competency/.test(el.shadowRoot.textContent); })()`, { timeout: 20000, label: "widget renders" });
  console.log("widget text:", (await browser.evaluate(`document.querySelector('adaptive-report').shadowRoot.textContent.replace(/\\s+/g, ' ').slice(0, 220)`)));
  ok = true;
} finally {
  await browser.close();
}
console.log(ok ? "PASS  the embed demo page renders the widget" : "FAIL");
process.exit(ok ? 0 : 1);
