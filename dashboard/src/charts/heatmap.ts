// Category × category heatmap with a single-hue sequential scale and value labels.
import { brand } from "../theme";
import type { Option } from "./Chart";
import { tip } from "./tooltip";

export function heatmap({ x, y, cells, max, ramp, format, leftWidth = 88, darkLow = false, valueLabel, note }: {
  x: string[]; y: string[]; cells: [number, number, number | null][]; max: number; ramp: [string, string]; format: (v: number) => string; leftWidth?: number;
  darkLow?: boolean; // ramp runs dark → light (low values are the loud ones)
  valueLabel: string; // tooltip row label, e.g. "Deviation from normal"
  note?: string;
}): Option {
  return {
    grid: { left: leftWidth, right: 8, top: 40, bottom: 4 },
    tooltip: {
      trigger: "item",
      formatter: (p: { value: [number, number, number | string] }) => tip({
        title: y[p.value[1]], sub: x[p.value[0]],
        rows: [{ label: valueLabel, value: typeof p.value[2] === "number" ? format(p.value[2]) : "–" }], note,
      }),
    },
    xAxis: { type: "category", data: x, position: "top", axisLine: { show: false }, axisLabel: { color: brand.ink, fontSize: 12, interval: 0, width: 84, overflow: "break", lineHeight: 14 }, splitArea: { show: false } },
    yAxis: { type: "category", data: y, inverse: true, axisLine: { show: false }, axisLabel: { color: brand.ink, fontSize: 12 } },
    visualMap: { show: false, min: 0, max, inRange: { color: ramp } },
    series: [{
      type: "heatmap",
      // Dark cells get white labels so text stays readable on the ramp.
      data: cells.map(([a, b, v]) => ({ value: [a, b, v ?? "-"], label: { color: v != null && (darkLow ? v < max * 0.45 : v > max * 0.55) ? "#fff" : brand.ink } })),
      itemStyle: { borderColor: "#fff", borderWidth: 2, borderRadius: 3 },
      label: {
        show: true, fontSize: 11,
        formatter: (p: { value: [number, number, number | string] }) => (typeof p.value[2] === "number" ? format(p.value[2]) : "–"),
      },
      emphasis: { itemStyle: { borderColor: brand.cyan, borderWidth: 2 } },
    }],
  };
}
