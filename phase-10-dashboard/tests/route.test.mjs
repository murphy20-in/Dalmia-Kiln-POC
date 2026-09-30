import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { ACTIONS, NAV, PLAIN } from "../public/js/copy.js";
import { groupFindings, plain } from "../public/js/pure/present.js";
import { href, linkTarget, match, parseLocation } from "../public/js/pure/route.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const js = path.resolve(here, "../public/js");
const snapshot = path.resolve(here, "../public/snapshot");

async function sources() {
  const out = {};
  for (const dir of [js, path.join(js, "pages")]) {
    for (const name of await readdir(dir)) if (name.endsWith(".js")) out[path.join(dir, name)] = await readFile(path.join(dir, name), "utf8");
  }
  return out;
}

async function knownAnchors(src) {
  const ids = new Set(["detail"]);
  for (const text of Object.values(src)) {
    for (const m of text.matchAll(/\bid: "([\w-]+)"/g)) ids.add(m[1]);
    for (const m of text.matchAll(/section\([^()]*?,\s*"([\w-]+)"/g)) ids.add(m[1]);
  }
  const findings = JSON.parse(await readFile(path.join(snapshot, "findings.json"), "utf8")).data;
  for (const f of groupFindings(findings)) ids.add(f.finding_id);
  for (const l of JSON.parse(await readFile(path.join(snapshot, "limitations.json"), "utf8")).data.limitations) ids.add(l.id);
  for (const s of ["score", "periods", "validation", "o2", "annotations", "data"]) ids.add(s); // methodology sections
  return ids;
}

test("every in-app link in the source resolves to a real route and anchor (click map)", async () => {
  const src = await sources();
  const anchors = await knownAnchors(src);
  const bad = [];
  let count = 0;
  for (const [file, text] of Object.entries(src)) {
    for (const m of text.matchAll(/\bto\(\s*[`"](\/[^`"$]*)(?:\$\{[^}]+\})?[^`"]*[`"](?:\s*,\s*(\{[^()]*?\}|[\w.]+))?(?:\s*,\s*"([\w-]*)")?\s*\)/g)) {
      count += 1;
      const pathOnly = m[0].includes("${") ? m[1].replace(/\/$/, "") : m[1];
      const probe = m[0].includes("${") && /abnormal-periods\/?$/.test(m[1]) ? "/abnormal-periods/P6-020"
        : m[0].includes("${") && /events\/?$/.test(m[1]) ? "/events/2152bd9a-0fd0-4561-b281-a59ebf84dcbc" : pathOnly;
      if (!match(probe)) bad.push(`${path.basename(file)}: route ${m[1]}`);
      if (m[3] && !anchors.has(m[3])) bad.push(`${path.basename(file)}: anchor #${m[3]} on ${m[1]}`);
    }
    for (const m of text.matchAll(/writeLink\([^,]+,\s*"(\/[^"]+)"/g)) {
      count += 1;
      if (!match(m[1])) bad.push(`${path.basename(file)}: write route ${m[1]}`);
    }
  }
  for (const spec of Object.values(ACTIONS)) {
    for (const [, p, a] of [spec.primary, ...spec.secondary]) {
      count += 1;
      if (!match(p)) bad.push(`ACTIONS route ${p}`);
      if (typeof a === "string" && a && !anchors.has(a)) bad.push(`ACTIONS anchor #${a}`);
    }
  }
  for (const [p] of NAV) if (!match(p)) bad.push(`NAV ${p}`);
  assert.ok(count > 40, `expected many links, saw ${count}`);
  assert.deepEqual(bad, []);
});

test("deep links match and unknown paths fall back to the overview", () => {
  assert.deepEqual(match("/abnormal-periods/P6-025"), { page: "/abnormal-periods", id: "P6-025" });
  assert.deepEqual(match("/events/new"), { page: "/events", mode: "new" });
  assert.deepEqual(match("/events/2152bd9a-0fd0-4561-b281-a59ebf84dcbc/edit"), { page: "/events", id: "2152bd9a-0fd0-4561-b281-a59ebf84dcbc", mode: "edit" });
  assert.equal(match("/abnormal-periods/../etc"), null);
  const r = parseLocation({ pathname: "/nope", search: "", hash: "" }, false);
  assert.equal(r.page, "/");
  assert.equal(r.known, false);
});

test("URL state round-trips in path mode and hash mode", () => {
  const query = { from: "2025-06-14T17:30:00", to: "2025-06-17T00:20:00", period: "P6-025", overlay: "o2_excluded" };
  for (const hashMode of [false, true]) {
    const link = href("/history", query, "graph", hashMode);
    const loc = hashMode ? { pathname: "/Dalmia-Kiln-POC/", search: "", hash: link } : (() => {
      const u = new URL(link, "http://x");
      return { pathname: u.pathname, search: u.search, hash: u.hash };
    })();
    const back = parseLocation(loc, hashMode);
    assert.equal(back.page, "/history");
    assert.deepEqual(back.query, query);
    assert.equal(back.anchor, "graph");
    assert.ok(linkTarget(link, hashMode), link);
  }
  const anchorOnly = parseLocation({ pathname: "/", search: "", hash: "#/validation#F18" }, true);
  assert.equal(anchorOnly.page, "/validation");
  assert.equal(anchorOnly.anchor, "F18");
  assert.equal(linkTarget("https://example.com/", false), null);
  assert.equal(linkTarget("#F1", false), null);
});

test("enums are shown in plain English and keep the raw value", () => {
  assert.deepEqual(plain("status", "NOT_SUPPORTED"), { text: "Not supported", meaning: "The score was not shown to rise before the abnormal periods", raw: "NOT_SUPPORTED" });
  assert.equal(plain("status", "WEAK").text, "Weak");
  assert.equal(plain("status", "NOT_AVAILABLE").text, "Not available");
  assert.equal(plain("severity", "HIGH").text, "High severity");
  assert.equal(plain("family", "DRAFT_PRESSURE").text, "Draft and pressure");
  assert.equal(plain("x", "SOME_NEW_VALUE").text, "Some new value");
  for (const [kind, map] of Object.entries(PLAIN)) {
    for (const [raw, [text]] of Object.entries(map)) assert.notEqual(text, raw, `${kind}.${raw} must be translated`);
  }
});

test("warning-rule findings collapse to one F3 row that names no rule", async () => {
  const findings = JSON.parse(await readFile(path.join(snapshot, "findings.json"), "utf8")).data;
  const grouped = groupFindings(findings);
  const f3 = grouped.filter((f) => f.finding_id.startsWith("F3"));
  assert.equal(f3.length, 1);
  assert.equal(f3[0].finding_id, "F3");
  assert.equal(f3[0].grouped.length, 5);
});
