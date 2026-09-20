/**
 * A tiny Chrome DevTools Protocol client with no dependencies.
 *
 * Node 22+ ships a global WebSocket, and Chrome ships the protocol, so a real
 * browser can be driven without installing Playwright. This is deliberately small:
 * launch, navigate, evaluate, wait, click, type, screenshot, viewport.
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);

export async function launchBrowser({ port = 9333, userDataDir, width = 1400, height = 950 }) {
  const executable = CHROME_CANDIDATES.find((p) => existsSync(p));
  if (!executable) throw new Error("No Chrome or Edge found. Set CHROME_PATH.");

  const child = spawn(
    executable,
    [
      "--headless=new",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      `--window-size=${width},${height}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-gpu",
      "about:blank",
    ],
    { stdio: "ignore" }
  );

  let version;
  for (let i = 0; i < 60; i++) {
    try {
      version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
      break;
    } catch {
      await sleep(250);
    }
  }
  if (!version) {
    child.kill();
    throw new Error("Chrome did not start");
  }

  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = targets.find((t) => t.type === "page");
  const socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });

  let nextId = 1;
  const pending = new Map();
  const listeners = new Map();
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(message.error.message)) : resolve(message.result);
    } else if (message.method) {
      for (const fn of listeners.get(message.method) ?? []) fn(message.params);
    }
  };

  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params }));
    });
  const on = (method, fn) => listeners.set(method, [...(listeners.get(method) ?? []), fn]);

  const consoleErrors = [];
  on("Runtime.exceptionThrown", (p) => consoleErrors.push(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text));
  on("Runtime.consoleAPICalled", (p) => {
    if (p.type === "error") consoleErrors.push(p.args.map((a) => a.value ?? a.description).join(" "));
  });

  await send("Page.enable");
  await send("Runtime.enable");
  // Visible text is often CSS-transformed (uppercase headings), so tests match case-insensitively.
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: "window.T = (s) => document.body && document.body.innerText.toLowerCase().includes(String(s).toLowerCase());",
  });

  const evaluate = async (expression) => {
    const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? "evaluate failed");
    return result.result.value;
  };

  const api = {
    consoleErrors,
    evaluate,
    async goto(url) {
      const loaded = new Promise((resolve) => on("Page.loadEventFired", resolve));
      await send("Page.navigate", { url });
      await Promise.race([loaded, sleep(20000)]);
    },
    async waitFor(expression, { timeout = 20000, label = expression } = {}) {
      const start = Date.now();
      while (Date.now() - start < timeout) {
        try {
          if (await evaluate(expression)) return true;
        } catch {
          /* page may be mid-navigation */
        }
        await sleep(250);
      }
      throw new Error(`Timed out waiting for: ${label}`);
    },
    text: () => evaluate("document.body.innerText"),
    async clickText(selector, text, { timeout = 15000 } = {}) {
      const expr = `(() => { const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.innerText && e.innerText.replace(/\\s+/g,' ').includes(${JSON.stringify(text)}) && !e.disabled); if (!el) return false; el.click(); return true; })()`;
      await api.waitFor(expr, { timeout, label: `click ${selector} with text "${text}"` });
    },
    async type(selector, value) {
      await evaluate(`(() => {
        const el = document.querySelector(${JSON.stringify(selector)});
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(value)});
        el.dispatchEvent(new Event('input', { bubbles: true }));
      })()`);
    },
    async viewport(width, height, mobile = false) {
      await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });
    },
    sleep: (ms) => sleep(ms),
    async screenshot(path) {
      await sleep(500); // let transitions settle
      const { data } = await send("Page.captureScreenshot", { format: "png" });
      mkdirSync(path.replace(/[\\/][^\\/]+$/, ""), { recursive: true });
      writeFileSync(path, Buffer.from(data, "base64"));
    },
    async close() {
      socket.close();
      child.kill();
    },
  };
  return api;
}
