// Scans every source file for wording that overclaims or leaks internals. Fails with file:line.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");

const RULES: { name: string; re: RegExp }[] = [
  { name: "POC", re: /\bPOC\b/ },
  { name: "phase number", re: /Phase \d/ },
  { name: "finding id", re: /p\d-(risk|abn)/ },
  { name: "enum leak", re: /NOT_SUPPORTED|INSUFFICIENT_DATA/ },
  // "Prediction" as the client's own journey-stage noun is allowed; every other form is not.
  { name: "predict", re: /predict(?!ion\b)/i },
  { name: "forecast", re: /forecast/i },
  { name: "lead time", re: /lead[- ]time/i },
  { name: "AUC", re: /\bAUC\b/ },
  { name: "accuracy", re: /accuracy/i },
  { name: "detects deposits", re: /detects? (deposit|ring|coating)/i },
  { name: "prevents shutdown", re: /prevent(s)? shutdown/i },
  { name: "tag id", re: /Kiln-I!/ },
  { name: "live", re: /real-time|(?<!aria-)\blive\b/i },
];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.(ts|tsx)$/.test(f) ? [p] : [];
  });
}

function violations(): string[] {
  const out: string[] = [];
  for (const file of files(SRC)) {
    const rel = relative(SRC, file).replaceAll("\\", "/");
    let allowLive = rel === "pages/Roadmap.tsx";
    readFileSync(file, "utf8").split("\n").forEach((line, i) => {
      if (line.includes("wording:allow-live-start")) allowLive = true;
      if (line.includes("wording:allow-live-end")) allowLive = rel === "pages/Roadmap.tsx";
      if (line.includes("wording:allow-live")) return;
      for (const { name, re } of RULES) {
        if (!re.test(line)) continue;
        if (name === "live" && (allowLive || /ribbon:/.test(line))) continue;
        if (name === "predict" && rel === "pages/Validation.tsx") continue;
        out.push(`${rel}:${i + 1} [${name}] ${line.trim()}`);
      }
    });
  }
  return out;
}

describe("on-screen wording", () => {
  it("has no banned phrases in src/", () => {
    const v = violations();
    if (v.length) console.error("Wording violations:\n" + v.join("\n"));
    expect(v).toEqual([]);
  });
});
