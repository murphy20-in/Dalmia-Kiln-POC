// Timeline of periods: one row per period, a bar from start to end on a Jun–Aug time axis.
import { fmtDate, fromMs } from "../lib/format";
import { brand } from "../theme";
import type { Option } from "./Chart";

export interface GanttItem { id: string; label: string; from: number; to: number; color: string; text: string; tooltip: string }

export function gantt({ items, min, max }: { items: GanttItem[]; min: number; max: number }): Option {
  return {
    grid: { left: 88, right: 96, top: 8, bottom: 28 },
    tooltip: { trigger: "item", formatter: (p: { data: { tooltip: string } }) => p.data.tooltip },
    xAxis: { type: "time", min, max, axisLabel: { formatter: (v: number) => fmtDate(fromMs(v)), hideOverlap: true }, splitLine: { show: true, lineStyle: { color: "#f0f2f5" } } },
    yAxis: { type: "category", inverse: true, data: items.map((d) => d.label), axisLine: { show: false }, axisLabel: { color: brand.ink, fontSize: 12 } },
    series: [{
      type: "custom",
      encode: { x: [1, 2], y: 0 },
      data: items.map((d, i) => ({ id: d.id, value: [i, d.from, d.to], tooltip: d.tooltip, color: d.color, text: d.text })),
      renderItem: (params: { dataIndex: number }, api: { value: (i: number) => number; coord: (v: number[]) => number[]; size: (v: number[]) => number[] }) => {
        const row = api.value(0);
        const [x0, y] = api.coord([api.value(1), row]);
        const [x1] = api.coord([api.value(2), row]);
        const h = api.size([0, 1])[1] * 0.56;
        // Periods are hours long on a three-month axis, so bars get a minimum width to stay visible and clickable.
        const w = Math.max(x1 - x0, 10);
        const d = items[params.dataIndex];
        return {
          type: "group",
          children: [
            { type: "rect", shape: { x: x0, y: y - h / 2, width: w, height: h, r: 3 }, style: { fill: d.color }, cursor: "pointer" },
            { type: "text", x: x0 + w + 6, y, style: { text: d.text, fill: brand.ink, fontSize: 11, fontFamily: "Inter", verticalAlign: "middle" }, silent: true },
          ],
        };
      },
    }],
  };
}
