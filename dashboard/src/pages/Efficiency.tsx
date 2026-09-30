import { useMemo, useState } from "react";
import Chart from "../charts/Chart";
import { stackedColumns } from "../charts/bars";
import { zoneLine, type LineSeries } from "../charts/zoneLine";
import ChartCard from "../components/ChartCard";
import { HeroBand, InsightCard, Legend, Loading, PageHeader } from "../components/ui";
import { efficiency as t, labels, systemName, zoneName } from "../copy";
import { useData } from "../data";
import { fmt1, fmtDate, fmtMonth, fmtPct, toMs } from "../lib/format";
import { brand, status, systemColor } from "../theme";

const DAY = 86_400_000;

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

  if (!e || !p || !daily) return <Loading />;
  const months = e.zoneShares.map((z) => fmtMonth(z.month));
  const [jun, , aug] = e.zoneShares;

  const series: LineSeries[] = [{ name: t.primaryLegend, data: daily.s, color: brand.navyInk, width: 2.5 }];
  if (o2) series.push({ name: t.o2Legend, data: daily.x, color: systemColor.COMBUSTION, dashed: true });
  // The O₂-excluded variant has its own reference, so zone bands are hidden while it is shown.
  const lineOption = zoneLine({
    series, edges: o2 ? undefined : e.bandEdges, zoom: true, tooltipDate: fmtDate,
    markers: p.periods.map((q) => ({ at: toMs(q.start.slice(0, 10) + "T00:00"), label: `#${q.n}` })),
  });

  const zoneStacks = [
    { name: zoneName.N, color: status.N.fill, values: e.zoneShares.map((z) => z.normal) },
    { name: zoneName.W, color: status.W.fill, values: e.zoneShares.map((z) => z.watch), labelColor: brand.ink },
    { name: zoneName.A, color: status.A.fill, values: e.zoneShares.map((z) => z.warning) },
  ];

  const fam = ["efficiency", "combustion", "thermal", "draft_pressure", "stability"] as const;
  const driverStacks = [
    ...fam.map((f) => ({ name: systemName[f.toUpperCase()], color: systemColor[f.toUpperCase()], values: e.drivers.map((d) => d[f]) })),
    { name: systemName.BREADTH_PERSISTENCE, color: systemColor.BREADTH_PERSISTENCE, values: e.drivers.map((d) => d.concurrence + d.persistence), labelColor: brand.ink },
  ];

  const i1 = t.insights.median(fmt1(jun.median), fmt1(aug.median));
  const i2 = t.insights.eff(fmt1(e.kpiMonthly[0].median), fmt1(e.kpiMonthly[2].median));
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.question} />
      <HeroBand className="!p-8">
        <p className="text-3xl font-bold text-white">{t.hero(fmtPct(jun.warning), fmtPct(aug.warning))}</p>
        <p className="mt-2 max-w-3xl text-white/85">{t.heroSub}</p>
      </HeroBand>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title={t.zonesTitle} sub={`${zoneName.N} / ${zoneName.W} / ${zoneName.A}, share of running time`}
          table={{ columns: [labels.month, zoneName.N, zoneName.W, zoneName.A], rows: e.zoneShares.map((z, i) => [months[i], fmtPct(z.normal, 1), fmtPct(z.watch, 1), fmtPct(z.warning, 1)]) }}>
          <Chart option={stackedColumns({ categories: months, stacks: zoneStacks })} height={300} label={e.zoneShares.map((z, i) => `${months[i]}: ${zoneName.A} ${fmtPct(z.warning)}`).join("; ")} />
          <Legend items={[...zoneStacks].reverse()} />
        </ChartCard>
        <ChartCard title={t.driversTitle} sub={t.driversSub}
          table={{ columns: [labels.system, ...months], rows: driverStacks.map((s) => [s.name, ...s.values.map((v) => fmtPct(v, 1))]) }}>
          <Chart option={stackedColumns({ categories: months, stacks: driverStacks })} height={300} label={t.driversTitle} />
          <Legend items={[...driverStacks].reverse()} />
        </ChartCard>
      </div>

      <ChartCard title={t.dailyTitle} sub={t.dailySub}
        actions={
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-ink">
            <input type="checkbox" className="h-4 w-4 accent-navy" checked={o2} onChange={(ev) => setO2(ev.target.checked)} />
            {t.o2Toggle}
          </label>
        }
        table={{ columns: [labels.day, t.primaryLegend, t.o2Legend], rows: e.daily.map((d) => [d.d, fmt1(d.s), fmt1(d.o2)]) }}>
        {o2 && <p className="mb-2 rounded-lg bg-cyan/10 px-3 py-2 text-sm text-navy-ink">{t.o2Note}</p>}
        <Chart option={lineOption} height={340} label={t.dailyTitle} />
        <Legend items={series.map((x) => ({ name: x.name, color: x.color }))} />
      </ChartCard>

      <div className="grid gap-4 lg:grid-cols-3">
        <InsightCard title={i1.title} body={i1.body} accent={brand.navy} />
        <InsightCard title={i2.title} body={i2.body} accent={systemColor.EFFICIENCY} />
        <InsightCard title={t.insights.o2.title} body={t.insights.o2.body} accent={brand.cyan} />
      </div>
    </div>
  );
}
