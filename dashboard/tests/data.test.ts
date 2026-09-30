// Data contract: the generated JSON must carry the verified pitch numbers and source maps.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const DIR = join(__dirname, "..", "public", "data");
const read = (name: string) => JSON.parse(readFileSync(join(DIR, name), "utf8"));

describe("exported data", () => {
  const summary = read("summary.json");
  const console_ = read("console.json");
  const periods = read("periods.json");

  it("has 9,557 operational 10-min buckets", () => {
    expect(summary.operationalBuckets).toBe(9557);
    expect(console_.rows).toHaveLength(9557);
    expect(console_.rows[0]).toHaveLength(7);
    expect(new Set(console_.rows.map((r: unknown[]) => r[2]))).toEqual(new Set(["N", "W", "A"]));
  });

  it("has 12 abnormal periods split 3 / 4 / 5, 11 multi-system", () => {
    expect(summary.periods).toMatchObject({ total: 12, high: 3, moderate: 4, low: 5, multiSystem: 11 });
    expect(periods.periods).toHaveLength(12);
  });

  it("has monthly time-in-Warning shares 0.251 / 0.416 / 0.530", () => {
    expect(summary.zoneShares.map((z: { warning: number }) => z.warning)).toEqual([0.251, 0.416, 0.53]);
  });

  it("has the audit, tag and band facts", () => {
    expect(summary.issuesTotal).toBe(32);
    expect(summary.issues).toEqual({ critical: 1, high: 4, medium: 16, low: 8, info: 3 });
    expect(summary.tags).toBe(203);
    expect(summary.rows).toBe(2575476);
    expect(summary.bandEdges).toEqual({ watch: 21.1, warning: 38.2 });
    expect(summary.kpiMonthly.map((k: { median: number }) => k.median)).toEqual([13.1, 17.5, 23.6]);
  });

  it("has the alternative-fuel facts", () => {
    const afr = read("afr.json");
    expect(afr).toMatchObject({ associated: 43, augustConfirmed: 27, coalStepTph: 6 });
  });

  it("gives every file a _sources map", () => {
    for (const f of readdirSync(DIR).filter((f) => f.endsWith(".json"))) {
      const s = read(f)._sources;
      expect(s, f).toBeTypeOf("object");
      expect(Object.keys(s).length, f).toBeGreaterThan(0);
    }
  });
});
