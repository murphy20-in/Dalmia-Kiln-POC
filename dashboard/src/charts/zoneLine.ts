// Line over time with soft Normal / Watch / Warning bands, optional shaded periods and markers.
// Gaps are nulls in the data: drawn as gaps (connectNulls stays false) and shaded grey with a label,
// so "kiln stopped / no data" is explicit rather than blank.
import { common } from "../copy";
import type { Edges } from "../data";
import { fmtDateTime, fromMs } from "../lib/format";
import { brand, status } from "../theme";
import type { Option } from "./Chart";
import { tip } from "./tooltip";

export interface LineSeries { name: string; data: [number, number | null][]; color: string; dashed?: boolean; width?: number }

/** Spans where the first series has no value, from the last point before to the first point after. */
function gapSpans(data: [number, number | null][]) {
  const out: { from: number; to: number }[] = [];
  let open: number | null = null;
  data.forEach(([t, v], i) => {
    if (v == null && open == null) open = i === 0 ? t : data[i - 1][0];
    if (v != null && open != null) { out.push({ from: open, to: t }); open = null; }
  });
  if (open != null) out.push({ from: open, to: data[data.length - 1][0] });
  return out;
}

export function zoneLine({ series, edges, periods = [], now, yMax = 100, zoom = false, markers = [], compact = false, tooltipDate = fmtDateTime, note }: {
  series: LineSeries[];
  edges?: Edges;
  periods?: { from: number; to: number; label: string }[];
  now?: number;
  yMax?: number;
  zoom?: boolean;
  markers?: { at: number; label: string }[];
  compact?: boolean;
  tooltipDate?: (t: string) => string;
  note?: string;
}): Option {
  const bands = edges
    ? [
        [{ yAxis: 0, itemStyle: { color: status.N.band } }, { yAxis: edges.watch }],
        [{ yAxis: edges.watch, itemStyle: { color: status.W.band } }, { yAxis: edges.warning }],
        [{ yAxis: edges.warning, itemStyle: { color: status.A.band } }, { yAxis: yMax }],
      ]
    : [];
  const shaded = periods.map((p) => [
    { xAxis: p.from, name: p.label, itemStyle: { color: brand.periodFill, borderColor: brand.periodEdge, borderWidth: 1, borderType: "dashed" },
      label: { show: !compact && !!p.label, position: "insideTop", color: brand.navyInk, fontSize: 10, fontWeight: 600 } },
    { xAxis: p.to },
  ]);
  const data0 = series[0]?.data ?? [];
  const range = data0.length > 1 ? data0[data0.length - 1][0] - data0[0][0] : 1;
  const gaps = compact ? [] : gapSpans(data0).map((g) => [
    { xAxis: g.from, name: common.stopped, itemStyle: { color: brand.gapFill },
      label: { show: (g.to - g.from) / range > 0.12, position: "insideBottom", color: brand.muted, fontSize: 10 } },
    { xAxis: g.to },
  ]);
  return {
    grid: compact ? { left: 4, right: 4, top: 4, bottom: 4 } : { left: 40, right: 16, top: 16, bottom: zoom ? 64 : 28 },
    tooltip: compact ? { show: false } : {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: brand.faint, type: "dashed" } },
      formatter: (ps: { axisValue: number; seriesName: string; value: [number, number | null]; color: string }[]) => tip({
        title: tooltipDate(fromMs(ps[0].axisValue)),
        rows: ps.map((p) => ({ label: p.seriesName, value: p.value[1] == null ? common.stopped : p.value[1].toFixed(1), color: p.color })),
        note,
      }),
    },
    xAxis: { type: "time", show: !compact, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", min: compact ? "dataMin" : 0, max: compact ? "dataMax" : yMax, show: !compact, interval: compact ? undefined : 25 },
    dataZoom: zoom ? [{ type: "slider", height: 20, bottom: 12, borderColor: brand.line, backgroundColor: brand.page, fillerColor: brand.zoomFill, handleStyle: { color: brand.navy }, moveHandleStyle: { color: brand.navyTint }, textStyle: { color: brand.muted }, labelFormatter: (v: number) => fromMs(v).slice(5, 10) }, { type: "inside" }] : undefined,
    series: series.map((s, i) => ({
      type: "line",
      name: s.name,
      data: s.data,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { color: s.color, width: s.width ?? 2, type: s.dashed ? "dashed" : "solid", cap: "round", join: "round" },
      itemStyle: { color: s.color },
      emphasis: { disabled: true },
      z: 3 + i,
      ...(i === 0
        ? {
            markArea: { silent: true, data: [...bands, ...gaps, ...shaded] },
            markLine: now != null || markers.length
              ? {
                  silent: true, symbol: "none",
                  data: [
                    ...(now != null ? [{ xAxis: now, lineStyle: { color: brand.navyInk, width: 1.5, type: "solid" }, label: { show: false } }] : []),
                    ...markers.map((m) => ({ xAxis: m.at, lineStyle: { color: brand.navyInk, width: 1, type: "dotted", opacity: 0.5 }, label: { formatter: m.label, color: brand.navyInk, fontSize: 10, position: "end" } })),
                  ],
                }
              : undefined,
          }
        : {}),
    })),
  };
}
