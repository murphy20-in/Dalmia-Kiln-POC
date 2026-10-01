import { memo } from "react";
import { Lock } from "lucide-react";
import Chart from "../charts/Chart";
import { consoleCopy, healthIndex, zoneName } from "../copy";
import type { Edges } from "../data";
import { brand, font, status, type Zone } from "../theme";

/** 0–100 Health Index gauge. Critical is drawn as a greyed, locked outer arc over Warning:
 *  it has no edge until it is calibrated on the plant's event logs. */
export default memo(function StatusGauge({ value, zone, edges }: { value: number | null; zone: Zone | null; edges: Edges }) {
  const w = edges.watch / 100;
  const a = edges.warning / 100;
  const common = { type: "gauge", startAngle: 210, endAngle: -30, min: 0, max: 100, center: ["50%", "58%"], splitNumber: 1 };
  const option = {
    series: [
      {
        ...common,
        radius: "86%",
        axisLine: { lineStyle: { width: 20, color: [[w, status.N.fill], [a, status.W.fill], [1, status.A.fill]] } },
        pointer: { show: value != null, length: "62%", width: 6, itemStyle: { color: brand.navyInk } },
        anchor: { show: value != null, size: 14, itemStyle: { color: brand.navyInk } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { distance: -46, color: brand.muted, fontSize: 11, formatter: (v: number) => (v === 0 || v === 100 ? String(v) : "") },
        title: { show: false },
        detail: {
          valueAnimation: true, offsetCenter: [0, "38%"], fontSize: 40, fontWeight: 700, color: brand.navyInk,
          fontFamily: font.sans, formatter: () => (value == null ? "–" : value.toFixed(1)),
        },
        data: [{ value: value ?? 0 }],
        animationDurationUpdate: 300,
        animationEasingUpdate: "cubicOut",
      },
      {
        ...common,
        radius: "99%",
        axisLine: { lineStyle: { width: 5, color: [[a, brand.clear], [1, status.C.fill]] } },
        pointer: { show: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, detail: { show: false },
        data: [{ value: 0 }], silent: true,
      },
    ],
  };
  const zoneLabel = zone ? zoneName[zone] : consoleCopy.gapTitle;
  return (
    <div>
      <Chart option={option} height={220} label={value == null ? zoneLabel : consoleCopy.gaugeAlt(value.toFixed(1), zoneLabel)} />
      <p className="-mt-2 text-center text-caption text-ink-muted">{healthIndex.scale}</p>
      <ul className="mt-3 flex flex-wrap justify-center gap-x-3 gap-y-1 text-caption text-ink-body">
        <li><Swatch c={status.N.fill} /> {zoneName.N} &lt; {edges.watch}</li>
        <li><Swatch c={status.W.fill} /> {zoneName.W} {edges.watch}–{edges.warning}</li>
        <li><Swatch c={status.A.fill} /> {zoneName.A} ≥ {edges.warning}</li>
      </ul>
      <p className="mt-2 flex items-center justify-center gap-1.5 text-center text-caption font-medium" style={{ color: status.C.ink }}>
        <Lock size={12} aria-hidden /> {zoneName.C}: {consoleCopy.criticalLocked.replace("Critical ", "")}
      </p>
    </div>
  );
});

const Swatch = ({ c }: { c: string }) => <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: c }} aria-hidden />;
