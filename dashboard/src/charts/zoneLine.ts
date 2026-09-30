// Line over time with soft Normal / Watch / Warning bands, optional shaded periods and markers.
// Gaps are nulls in the data and are drawn as gaps (connectNulls stays false).
import type { Edges } from "../data";
import { fmtDateTime } from "../lib/format";
import { fromMs } from "../lib/format";
import { brand, status } from "../theme";
import type { Option } from "./Chart";

export interface LineSeries { name: string; data: [number, number | null][]; color: string; dashed?: boolean; width?: number }

export function zoneLine({ series, edges, periods = [], now, yMax = 100, zoom = false, markers = [], compact = false, tooltipDate = fmtDateTime }: {
  series: LineSeries[];
  edges?: Edges;
  periods?: { from: number; to: number; label: string }[];
  now?: number;
  yMax?: number;
  zoom?: boolean;
  markers?: { at: number; label: string }[];
  compact?: boolean;
  tooltipDate?: (t: string) => string;
}): Option {
  const bands = edges
    ? [
        [{ yAxis: 0, itemStyle: { color: status.N.band } }, { yAxis: edges.watch }],
        [{ yAxis: edges.watch, itemStyle: { color: status.W.band } }, { yAxis: edges.warning }],
        [{ yAxis: edges.warning, itemStyle: { color: status.A.band } }, { yAxis: yMax }],
      ]
    : [];
  const shaded = periods.map((p) => [
    { xAxis: p.from, name: p.label, itemStyle: { color: "rgba(27,44,99,0.10)" }, label: { show: !compact, position: "insideTop", color: brand.navyInk, fontSize: 10 } },
    { xAxis: p.to },
  ]);
  return {
    grid: compact ? { left: 4, right: 4, top: 4, bottom: 4 } : { left: 44, right: 16, top: 16, bottom: zoom ? 64 : 32 },
    tooltip: compact ? { show: false } : {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: brand.faint } },
      formatter: (ps: { axisValue: number; seriesName: string; value: [number, number | null]; color: string }[]) => {
        const head = `<b>${tooltipDate(fromMs(ps[0].axisValue))}</b>`;
        return [head, ...ps.map((p) => `<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${p.value[1] == null ? "–" : p.value[1].toFixed(1)}</b>`)].join("<br/>");
      },
    },
    xAxis: { type: "time", show: !compact, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", min: compact ? "dataMin" : 0, max: compact ? "dataMax" : yMax, show: !compact, interval: compact ? undefined : 25 },
    dataZoom: zoom ? [{ type: "slider", height: 22, bottom: 12, borderColor: brand.line, fillerColor: "rgba(42,70,156,0.12)", handleStyle: { color: brand.navy }, textStyle: { color: brand.muted }, labelFormatter: (v: number) => fromMs(v).slice(5, 10) }, { type: "inside" }] : undefined,
    series: series.map((s, i) => ({
      type: "line",
      name: s.name,
      data: s.data,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { color: s.color, width: s.width ?? 2, type: s.dashed ? "dashed" : "solid" },
      itemStyle: { color: s.color },
      emphasis: { disabled: true },
      z: 3 + i,
      ...(i === 0
        ? {
            markArea: { silent: true, data: [...bands, ...shaded] },
            markLine: now != null || markers.length
              ? {
                  silent: true, symbol: "none",
                  data: [
                    ...(now != null ? [{ xAxis: now, lineStyle: { color: brand.navyInk, width: 1.5, type: "solid" }, label: { show: false } }] : []),
                    ...markers.map((m) => ({ xAxis: m.at, lineStyle: { color: brand.navyInk, width: 1, type: "dotted", opacity: 0.6 }, label: { formatter: m.label, color: brand.navyInk, fontSize: 10, position: "end" } })),
                  ],
                }
              : undefined,
          }
        : {}),
    })),
  };
}
