import { describe, expect, it } from "vitest";
import { computeValue } from "../src/lib/value";

describe("value model", () => {
  it("computes a hand-checked case", () => {
    const v = computeValue({
      clinkerTpd: 4800, contributionPerT: 1000, runningDays: 300,
      stoppageHours: 100, depositSharePct: 50, convertiblePct: 50, downtimeSavedPct: 40,
      heatKcalPerKg: 700, fuelPerMkcal: 1000, efficiencyGainPct: 1,
    });
    // 100 h × 0.5 × 0.5 × 0.4 = 10 h; 10 h × 200 t/h × ₹1,000 = ₹20 lakh
    expect(v.hoursRecovered).toBeCloseTo(10);
    expect(v.productionProtected).toBeCloseTo(2_000_000);
    // 4,800 t × 300 d = 1.44 Mt; × 700,000 kcal/t = 1.008e12 kcal = 1,008,000 Mkcal; × ₹1,000 × 1% = ₹1.008 Cr
    expect(v.fuelSaving).toBeCloseTo(10_080_000);
    expect(v.total).toBeCloseTo(12_080_000);
  });

  it("is zero when nothing is convertible and there is no efficiency gain", () => {
    const v = computeValue({
      clinkerTpd: 5000, contributionPerT: 1500, runningDays: 330, stoppageHours: 120, depositSharePct: 40,
      convertiblePct: 0, downtimeSavedPct: 50, heatKcalPerKg: 720, fuelPerMkcal: 1500, efficiencyGainPct: 0,
    });
    expect(v.total).toBe(0);
  });
});
