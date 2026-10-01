// Token discipline: every colour originates in src/theme.ts. Any hex or rgb(a)/hsl literal elsewhere in src/ fails with file:line.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");
const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(rgba?|hsla?)\(/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.(ts|tsx|css)$/.test(f) ? [p] : [];
  });
}

describe("colour tokens", () => {
  it("has no colour literals outside src/theme.ts", () => {
    const out: string[] = [];
    for (const file of files(SRC)) {
      const rel = relative(SRC, file).replaceAll("\\", "/");
      if (rel === "theme.ts") continue;
      readFileSync(file, "utf8").split("\n").forEach((line, i) => {
        // Anchors and element ids ("#main", href="#x") are not colours; a hex run of 3–8 digits/a–f is.
        if (COLOUR.test(line.replace(/href="#[^"]*"|["']#(main|root)["']/g, ""))) out.push(`${rel}:${i + 1} ${line.trim()}`);
      });
    }
    if (out.length) console.error("Colour literals outside theme.ts:\n" + out.join("\n"));
    expect(out).toEqual([]);
  });
});
