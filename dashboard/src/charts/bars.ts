// Stacked columns (monthly shares), sorted horizontal bars (contributions) and small month columns.
import { brand } from "../theme";
import type { Option } from "./Chart";
import { tip } from "./tooltip";

export interface Stack { name: string; color: string; values: number[]; labelColor?: string }

const pct = (v: number, d = 0) => `${(v * 100).toFixed(d)}%`;

/** Vertical stacked columns with values of 0–1 shown as %. Segments ≥ 6% are labelled inside;
 *  pair with a legend for series names. */
export function stackedColumns({ categories, stacks }: { categories: string[]; stacks: Stack[] }): Option {
  return {
    grid: { left: 44, right: 8, top: 12, bottom: 28 },
    tooltip: {
      trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: brand.hoverFill } },
      formatter: (ps: { dataIndex: number }[]) => {
        const i = ps[0].dataIndex;
        return tip({ title: categories[i], rows: [...stacks].reverse().map((s) => ({ label: s.name, value: pct(s.values[i], 1), color: s.color })) });
      },
    },
    xAxis: { type: "category", data: categories, axisLabel: { fontSize: 13, color: brand.ink, fontWeight: 600 } },
    yAxis: { type: "value", max: (v: { max: number }) => Math.max(1, v.max), interval: 0.25, axisLabel: { formatter: (v: number) => pct(v) } },
    series: stacks.map((s, i) => ({
      type: "bar",
      name: s.name,
      stack: "all",
      barWidth: "44%",
      itemStyle: { color: s.color, borderColor: "#fff", borderWidth: 1.5, borderRadius: i === stacks.length - 1 ? [3, 3, 0, 0] : 0 },
      label: { show: true, color: s.labelColor ?? "#fff", fontWeight: 600, fontSize: 12, formatter: (p: { value: number }) => (p.value >= 0.06 ? pct(p.value) : "") },
      data: s.values,
      emphasis: { focus: "series" },
    })),
  };
}

/** Sorted horizontal bars with value labels. */
export function hbars({ items, max, unit = "Index points" }: { items: { name: string; value: number; color: string }[]; max?: number; unit?: string }): Option {
  const sorted = [...items].sort((a, b) => a.value - b.value);
  return {
    grid: { left: 8, right: 44, top: 4, bottom: 4, containLabel: true },
    tooltip: { trigger: "item", formatter: (p: { dataIndex: number }) => tip({ title: sorted[p.dataIndex].name, rows: [{ label: unit, value: sorted[p.dataIndex].value.toFixed(1), color: sorted[p.dataIndex].color }] }) },
    xAxis: { type: "value", max, show: false },
    yAxis: { type: "category", data: sorted.map((d) => d.name), axisLine: { show: false }, axisLabel: { color: brand.ink, fontSize: 13 } },
    series: [{
      type: "bar", barWidth: 14,
      showBackground: true, backgroundStyle: { color: brand.page, borderRadius: [0, 3, 3, 0] },
      data: sorted.map((d) => ({ value: d.value, itemStyle: { color: d.color, borderRadius: [0, 3, 3, 0] } })),
      label: { show: true, position: "right", color: brand.navyInk, fontWeight: 600, formatter: (p: { value: number }) => p.value.toFixed(1) },
      animationDurationUpdate: 250,
    }],
  };
}

/** One small column chart per measure: small multiples instead of a dual axis. */
export function monthBars({ months, values, color, unit }: { months: string[]; values: number[]; color: string; unit: string }): Option {
  return {
    grid: { left: 36, right: 8, top: 24, bottom: 24 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: brand.hoverFill } },
      formatter: (ps: { dataIndex: number }[]) => tip({ title: months[ps[0].dataIndex], rows: [{ label: unit, value: values[ps[0].dataIndex].toFixed(1), color }] }) },
    xAxis: { type: "category", data: months, axisLabel: { color: brand.ink } },
    yAxis: { type: "value", min: 0, splitNumber: 3 },
    series: [{ type: "bar", data: values, barWidth: "48%", itemStyle: { color, borderRadius: [3, 3, 0, 0] },
      label: { show: true, position: "top", color: brand.navyInk, fontWeight: 600, formatter: (p: { value: number }) => p.value.toFixed(1) } }],
  };
}
