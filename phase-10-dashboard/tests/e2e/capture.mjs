// node tests/e2e/capture.mjs [shots|rendered|hosted]   (headless Google Chrome over CDP; local service on :8010)
// shots: full-page desktop (1440) and mobile (375) captures into screenshots/after/.
// rendered: visible text of every page into tests/fixtures/rendered/<page>.txt for the honesty test.
//   One block per element; an insight or finding card is one block, because it is read as one unit on screen.
// hosted: serve public/ on 127.0.0.1:8011 first (python3 -m http.server 8011 -d public); maps kiln.github.io
// there so snapshot mode runs, then prints the read-only controls and their stated reasons.
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const OUT = new URL("../../screenshots/after/", import.meta.url).pathname;
const PAGES = {
  overview: "/", "historical-risk": "/history", "abnormal-periods": "/abnormal-periods/P6-025",
  "plant-events": "/events", "plant-events-new": "/events/new", validation: "/validation",
  "data-quality": "/data-quality", methodology: "/methodology",
};
const mode = process.argv[2] || "shots";

const chrome = spawn("google-chrome", ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
  "--user-data-dir=/tmp/shots-profile", "--remote-debugging-port=9333",
  "--host-resolver-rules=MAP kiln.github.io 127.0.0.1:8011", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) {
  await sleep(200);
  try { target = (await (await fetch("http://127.0.0.1:9333/json")).json()).find((t) => t.type === "page"); } catch {}
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (m) => {
  const msg = JSON.parse(m.data);
  if (pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
const cdp = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); })
  .then((m) => { if (m.error) throw new Error(method + ": " + m.error.message); return m.result; });
const evalJs = async (expression) => (await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result.value;
const settle = () => evalJs(`(async () => { for (let i = 0; i < 100; i++) { await new Promise(r => setTimeout(r, 100));
  if (document.querySelector('#page-title') && !document.querySelector('.state-loading')) break; }
  await new Promise(r => setTimeout(r, 400)); return document.documentElement.scrollHeight; })()`);

async function capture(url, file, width, mobile) {
  await cdp("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile });
  await cdp("Page.navigate", { url });
  const height = await settle();
  const overflow = await evalJs("document.documentElement.scrollWidth - document.documentElement.clientWidth");
  await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });
  await sleep(300);
  const { data } = await cdp("Page.captureScreenshot", { format: "png" });
  writeFileSync(OUT + file, Buffer.from(data, "base64"));
  console.log(file, width, height, "overflow", overflow);
}

await cdp("Page.enable");
await cdp("Network.enable");
await cdp("Network.setCacheDisabled", { cacheDisabled: true });
if (mode === "shots") {
  for (const [name, path] of Object.entries(PAGES)) {
    await capture("http://127.0.0.1:8010" + path, name + ".png", 1440, false);
    await capture("http://127.0.0.1:8010" + path, "mobile-" + name + ".png", 375, true);
  }
} else if (mode === "rendered") {
  const pages = [["overview", "/"], ["history", "/history"], ["periods", "/abnormal-periods/P6-025"], ["events", "/events"],
    ["events-new", "/events/new?start=2025-06-15T17:30:00&end=2025-06-16T00:20:00&ref=P6-025"], ["validation", "/validation"],
    ["quality", "/data-quality"], ["methodology", "/methodology"]];
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  for (const [name, path] of pages) {
    await cdp("Page.navigate", { url: "http://127.0.0.1:8010" + path });
    await settle();
    const text = await evalJs(`(() => {
      document.querySelectorAll("details").forEach((d) => { d.open = true; });
      const unit = ".insight, .finding";
      const sel = "header p, .disclaimer, .ro-banner, h1, h2, h3, p, li, dt, dd, td, th, caption, figcaption, summary, legend, label, a.btn, button, .kpi, .chip, svg title, svg text";
      const blocks = [];
      const push = (el) => { const t = (el.textContent || "").replace(/\\s+/g, " ").trim(); if (t) blocks.push(t); };
      document.querySelectorAll(unit).forEach(push);
      document.querySelectorAll(sel).forEach((el) => { if (!el.closest(unit)) push(el); });
      document.querySelectorAll("[aria-label], [title]").forEach((el) => { for (const a of ["aria-label", "title"]) { const v = el.getAttribute(a); if (v) blocks.push(v); } });
      return blocks.join("\\n\\n");
    })()`);
    writeFileSync(new URL(`../fixtures/rendered/${name}.txt`, import.meta.url), text + "\n");
    console.log(name, text.length);
  }
} else {
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  for (const hash of ["#/events/new", "#/events", "#/"]) {
    await cdp("Page.navigate", { url: "http://kiln.github.io/" + hash });
    await settle();
    console.log(hash, await evalJs(`JSON.stringify({
      hosted: /read-only/i.test(document.body.innerText),
      ro: [...document.querySelectorAll('[aria-disabled="true"]')].map(b => [b.textContent.trim(), document.getElementById((b.getAttribute('aria-describedby')||'').split(' ')[0])?.textContent.trim().slice(0, 60)]),
      enabledSubmit: document.querySelectorAll('button[type=submit]:not([aria-disabled="true"])').length,
    })`));
  }
}
ws.close();
chrome.kill();
