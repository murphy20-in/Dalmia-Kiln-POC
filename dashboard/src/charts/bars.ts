// Stacked columns (monthly shares / points) and sorted horizontal bars (contributions).
import { brand } from "../theme";
import type { Option } from "./Chart";

export interface Stack { name: string; color: string; values: number[]; labelColor?: string }

/** Vertical stacked columns with values of 0–1 shown as %. Segments ≥ 6% are labelled inside;
 *  pair with <Legend> for series names. */
export function stackedColumns({ categories, stacks }: { categories: string[]; stacks: Stack[] }): Option {
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  return {
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v: number) => `${(v * 100).toFixed(1)}%` },
    xAxis: { type: "category", data: categories, axisLabel: { fontSize: 13, color: brand.ink, fontWeight: 600 } },
    yAxis: { type: "value", max: (v: { max: number }) => Math.max(1, v.max), axisLabel: { formatter: pct } },
    series: stacks.map((s, i) => ({
      type: "bar",
      name: s.name,
      stack: "all",
      barWidth: "46%",
      itemStyle: { color: s.color, borderColor: "#fff", borderWidth: 2, borderRadius: i === stacks.length - 1 ? [4, 4, 0, 0] : 0 },
      label: { show: true, color: s.labelColor ?? "#fff", fontWeight: 600, fontSize: 12, formatter: (p: { value: number }) => (p.value >= 0.06 ? pct(p.value) : "") },
      data: s.values,
      emphasis: { focus: "series" },
    })),
  };
}

/** Sorted horizontal bars with value labels. */
export function hbars({ items, max }: { items: { name: string; value: number; color: string }[]; max?: number }): Option {
  const sorted = [...items].sort((a, b) => a.value - b.value);
  return {
    grid: { left: 8, right: 48, top: 4, bottom: 4, containLabel: true },
    tooltip: { trigger: "item", valueFormatter: (v: number) => `${v.toFixed(1)} pts` },
    xAxis: { type: "value", max, show: false },
    yAxis: { type: "category", data: sorted.map((d) => d.name), axisLine: { show: false }, axisLabel: { color: brand.ink, fontSize: 13 } },
    series: [{
      type: "bar", barWidth: 16,
      data: sorted.map((d) => ({ value: d.value, itemStyle: { color: d.color, borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: "right", color: brand.ink, fontWeight: 600, formatter: (p: { value: number }) => p.value.toFixed(1) },
      animationDurationUpdate: 300,
    }],
  };
}
