import { useMemo, useState } from "react";
import Chart from "../charts/Chart";
import { stackedColumns } from "../charts/bars";
import { zoneLine, type LineSeries } from "../charts/zoneLine";
import ChartCard from "../components/ChartCard";
import { Callout, Lead, Loading, PageHeader } from "../components/ui";
import { efficiency as t, labels, systemName, zoneName } from "../copy";
import { useData } from "../data";
import { fmt1, fmtDate, fmtMonth, fmtPct, toMs } from "../lib/format";
import { brand, status, systemColor } from "../theme";

const DAY = 86_400_000;
const FAM = ["efficiency", "combustion", "thermal", "draft_pressure", "stability"] as const;

export default function Efficiency() {
  const e = useData("efficiency");
  const p = useData("periods");
  const [o2, setO2] = useState(false);

  const daily = useMemo(() => {
    if (!e) return null;
    const by = new Map(e.daily.map((d) => [toMs(d.d + "T00:00"), d]));
    const first = toMs(e.daily[0].d + "T00:00");
    const last = toMs(e.daily[e.daily.length - 1].d + "T00:00");
    const s: [number, number | null][] = [];
    const x: [number, number | null][] = [];
    for (let m = first; m <= last; m += DAY) {
      const d = by.get(m); // days without running data stay null → drawn as gaps
      s.push([m, d ? d.s : null]);
      x.push([m, d ? d.o2 : null]);
    }
    return { s, x };
  }, [e]);

  const series = useMemo<LineSeries[]>(() => {
    if (!daily) return [];
    const out: LineSeries[] = [{ name: t.primaryLegend, data: daily.s, color: brand.navyInk, width: 2.5 }];
    if (o2) out.push({ name: t.o2Legend, data: daily.x, color: systemColor.COMBUSTION, dashed: true });
    return out;
  }, [daily, o2]);

  // The O₂-excluded variant has its own reference, so zone bands are hidden while it is shown.
  const lineOption = useMemo(() => e && p && zoneLine({
    series, edges: o2 ? undefined : e.bandEdges, zoom: true, tooltipDate: fmtDate,
    markers: p.periods.map((q) => ({ at: toMs(q.start.slice(0, 10) + "T00:00"), label: `#${q.n}` })),
  }), [e, p, series, o2]);

  if (!e || !p || !daily || !lineOption) return <Loading />;
  const months = e.zoneShares.map((z) => fmtMonth(z.month));
  const [jun, , aug] = e.zoneShares;

  const zoneStacks = [
    { name: zoneName.N, color: status.N.fill, values: e.zoneShares.map((z) => z.normal) },
    { name: zoneName.W, color: status.W.fill, values: e.zoneShares.map((z) => z.watch), labelColor: brand.ink },
    { name: zoneName.A, color: status.A.fill, values: e.zoneShares.map((z) => z.warning) },
  ];
  const driverStacks = [
    ...FAM.map((f) => ({ name: systemName[f.toUpperCase()], color: systemColor[f.toUpperCase()], values: e.drivers.map((d) => d[f]) })),
    { name: systemName.BREADTH_PERSISTENCE, color: systemColor.BREADTH_PERSISTENCE, values: e.drivers.map((d) => d.concurrence + d.persistence), labelColor: brand.ink },
  ];

  const i1 = t.insights.median(fmt1(jun.median), fmt1(aug.median));
  const i2 = t.insights.eff(fmt1(e.kpiMonthly[0].median), fmt1(e.kpiMonthly[2].median));
  const lineLegend = [
    ...series.map((x) => ({ name: x.name, color: x.color, dashed: x.dashed })),
    { name: t.markerLegend, color: brand.navyInk, dashed: true },
  ];
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.question} />
      <Lead sub={t.heroSub}>{t.hero(fmtPct(jun.warning), fmtPct(aug.warning))}</Lead>

      {/* What changed, and when */}
      <div className="grid gap-6 lg:grid-cols-12">
        <ChartCard className="lg:col-span-5" title={t.zonesTitle} sub={t.zonesSub} legend={[...zoneStacks].reverse()} source={t.source}
          table={{ columns: [labels.month, zoneName.N, zoneName.W, zoneName.A], rows: e.zoneShares.map((z, i) => [months[i], fmtPct(z.normal, 1), fmtPct(z.watch, 1), fmtPct(z.warning, 1)]) }}>
          <Chart option={stackedColumns({ categories: months, stacks: zoneStacks })} height={300} label={e.zoneShares.map((z, i) => `${months[i]}: ${zoneName.A} ${fmtPct(z.warning)}`).join("; ")} />
        </ChartCard>
        <ChartCard className="lg:col-span-7" title={t.dailyTitle} sub={t.dailySub} legend={lineLegend} source={t.source}
          actions={
            <label className="flex cursor-pointer items-center gap-2 rounded-panel border border-line-strong px-3 py-1.5 text-caption font-semibold text-ink transition-colors hover:border-navy">
              <input type="checkbox" className="h-4 w-4 accent-navy" checked={o2} onChange={(ev) => setO2(ev.target.checked)} />
              {t.o2Toggle}
            </label>
          }
          table={{ columns: [labels.day, t.primaryLegend, t.o2Legend], rows: e.daily.map((d) => [d.d, fmt1(d.s), fmt1(d.o2)]) }}>
          {o2 && <div className="mb-2"><Callout>{t.o2Note}</Callout></div>}
          <Chart option={lineOption} height={o2 ? 252 : 300} label={t.dailyTitle} />
        </ChartCard>
      </div>

      {/* Which systems moved, and what it does and does not establish */}
      <div className="grid gap-6 lg:grid-cols-12">
        <ChartCard className="lg:col-span-5" title={t.driversTitle} sub={t.driversSub} legend={[...driverStacks].reverse()}
          table={{ columns: [labels.system, ...months], rows: driverStacks.map((s) => [s.name, ...s.values.map((v) => fmtPct(v, 1))]) }}>
          <Chart option={stackedColumns({ categories: months, stacks: driverStacks })} height={300} label={t.driversTitle} />
        </ChartCard>
        <section className="card lg:col-span-7" aria-labelledby="interpret">
          <h2 id="interpret" className="t-section">{t.interpretTitle}</h2>
          <div className="mt-4 flex flex-col divide-y divide-line">
            {[{ ...i1, tone: brand.navy }, { ...i2, tone: systemColor.EFFICIENCY }, { ...t.insights.o2, tone: brand.cyan }].map((x) => (
              <article key={x.title} className="flex gap-4 py-4 first:pt-0 last:pb-0">
                <span className="mt-1 w-1 shrink-0 self-stretch rounded-full" style={{ background: x.tone }} aria-hidden />
                <div>
                  <h3 className="t-card">{x.title}</h3>
                  <p className="mt-1 text-label text-ink-body">{x.body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
