// Typed loaders for the static JSON produced by scripts/export_data.py.
import { useEffect, useState } from "react";
import type { Zone } from "./theme";

type Sources = { _sources: Record<string, string> };
type Month = string; // "2025-06"
export type Family = "EFFICIENCY" | "COMBUSTION" | "THERMAL" | "DRAFT_PRESSURE" | "STABILITY";
export type Severity = "HIGH" | "MODERATE" | "LOW";
export interface Edges { watch: number; warning: number }
export interface ZoneShare { month: Month; normal: number; watch: number; warning: number; median: number }

export interface Summary extends Sources {
  rows: number;
  datasets: number;
  tags: number;
  tagsHighConfidence: number;
  runningMinutes: number;
  kpiTags: number;
  issues: Record<"critical" | "high" | "medium" | "low" | "info", number>;
  issuesTotal: number;
  periods: { total: number; high: number; moderate: number; low: number; multiSystem: number };
  kpiMonthly: { month: Month; median: number }[];
  zoneShares: ZoneShare[];
  bandEdges: Edges;
  operationalBuckets: number;
}

// [time, Health Index, zone, Efficiency Index, contributions (5 systems + breadth/persistence), top-3 reason codes, flags]
export type ConsoleRow = [string, number, Zone, number | null, number[], string[], string[]];
export type Gap = [string, string, "stopped" | "nodata"];
export interface ConsoleData extends Sources {
  columns: string[];
  families: string[];
  stepMinutes: number;
  bandEdges: Edges;
  start: string;
  end: string;
  rows: ConsoleRow[];
  gaps: Gap[];
}

export interface EfficiencyData extends Sources {
  bandEdges: Edges;
  daily: { d: string; s: number; o2: number | null; k: number | null; n: number }[];
  zoneShares: ZoneShare[];
  o2MonthlyMedian: { month: Month; median: number }[];
  drivers: ({ month: Month } & Record<"efficiency" | "combustion" | "thermal" | "draft_pressure" | "stability" | "concurrence" | "persistence", number>)[];
  kpiMonthly: { month: Month; median: number }[];
  periods: { id: string; start: string; end: string; severity: Severity }[];
}

export interface Period {
  id: string;
  n: number;
  start: string;
  end: string;
  onset: string;
  durationMin: number;
  severity: Severity;
  severityScore: number;
  dominant: Family;
  systems: Family[];
  load: "LOAD_ASSOCIATED" | "UNCERTAIN";
  feedChange: number;
  robustness: number;
  peakKpi: number;
  deviation: Record<Family, number>;
  series: [string, number | null][];
}
export interface PeriodsData extends Sources { bandEdges: Edges; periods: Period[] }

export interface AfrCard { key: string; effect: number; unit: string; metric: "rho" | "delta"; strength: "Consistent" | "Lower confidence" | "Emerging"; augustConfirmed: boolean }
export interface AfrData extends Sources {
  monthly: { month: Month; afr: number; feed: number }[];
  cards: AfrCard[];
  associated: number;
  augustConfirmed: number;
  coalStepTph: number;
  feedRho: { aprMay: number; junJul: number; aug: number };
}

export interface DataReadiness extends Sources {
  months: Month[];
  coverage: { dataset: string; pct: number[] }[];
  issues: Summary["issues"];
  examples: { severity: string; title: string; body: string; src: string }[];
  asks: { priority: number; title: string; detail: string; unlocks: string }[];
}

export interface ValidationData extends Sources {
  primary: { pe: number; ciLow: number; ciHigh: number; p: number; supported: boolean };
  periods: number;
  censored: number;
  uncensored: number;
  o2RankCorrelation: number;
  negativeControls: Record<"NC1" | "NC2", { p: number }>;
  futurePerturbationIdentical: boolean;
  revalidateAt: number;
  checks: Record<string, number>;
  versions: Record<string, string>;
}

interface Files {
  summary: Summary;
  console: ConsoleData;
  efficiency: EfficiencyData;
  periods: PeriodsData;
  afr: AfrData;
  data: DataReadiness;
  validation: ValidationData;
}

const cache = new Map<keyof Files, Promise<unknown>>();

export function load<K extends keyof Files>(name: K): Promise<Files[K]> {
  if (!cache.has(name)) {
    cache.set(name, fetch(`${import.meta.env.BASE_URL}data/${name}.json`).then((r) => {
      if (!r.ok) throw new Error(`${name}.json: HTTP ${r.status}`);
      return r.json();
    }).catch((e: unknown) => { cache.delete(name); throw e; }));
  }
  return cache.get(name) as Promise<Files[K]>;
}

/** Returns the file once loaded (undefined while loading). Throws render-time on failure so the error boundary shows it. */
export function useData<K extends keyof Files>(name: K): Files[K] | undefined {
  const [state, setState] = useState<{ data?: Files[K]; error?: Error }>({});
  useEffect(() => {
    let active = true;
    load(name).then((data) => active && setState({ data }), (error: Error) => active && setState({ error }));
    return () => { active = false; };
  }, [name]);
  if (state.error) throw state.error;
  return state.data;
}
