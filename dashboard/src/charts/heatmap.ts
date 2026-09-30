// Category × category heatmap with a single-hue sequential scale and value labels.
import { brand } from "../theme";
import type { Option } from "./Chart";

export function heatmap({ x, y, cells, max, ramp, format, leftWidth = 88, darkLow = false }: {
  x: string[]; y: string[]; cells: [number, number, number | null][]; max: number; ramp: [string, string]; format: (v: number) => string; leftWidth?: number;
  darkLow?: boolean; // ramp runs dark → light (low values are the loud ones)
}): Option {
  return {
    grid: { left: leftWidth, right: 16, top: 36, bottom: 8 },
    tooltip: { trigger: "item", formatter: (p: { value: [number, number, number | null] }) => `${y[p.value[1]]} · ${x[p.value[0]]}: <b>${p.value[2] == null ? "–" : format(p.value[2])}</b>` },
    xAxis: { type: "category", data: x, position: "top", axisLine: { show: false }, axisLabel: { color: brand.ink, fontSize: 12, interval: 0 }, splitArea: { show: false } },
    yAxis: { type: "category", data: y, inverse: true, axisLine: { show: false }, axisLabel: { color: brand.ink, fontSize: 12 } },
    visualMap: { show: false, min: 0, max, inRange: { color: ramp } },
    series: [{
      type: "heatmap",
      // Dark cells get white labels so text stays readable on the ramp.
      data: cells.map(([a, b, v]) => ({ value: [a, b, v ?? "-"], label: { color: v != null && (darkLow ? v < max * 0.45 : v > max * 0.55) ? "#fff" : brand.ink } })),
      itemStyle: { borderColor: "#fff", borderWidth: 3, borderRadius: 4 },
      label: {
        show: true, fontSize: 11,
        formatter: (p: { value: [number, number, number | string] }) => (typeof p.value[2] === "number" ? format(p.value[2]) : "–"),
      },
      emphasis: { itemStyle: { borderColor: brand.navyInk, borderWidth: 2 } },
    }],
  };
}
