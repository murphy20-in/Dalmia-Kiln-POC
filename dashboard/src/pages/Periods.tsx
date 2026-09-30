import { Fragment, useCallback, useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Play } from "lucide-react";
import Chart from "../charts/Chart";
import { gantt } from "../charts/gantt";
import { heatmap } from "../charts/heatmap";
import { zoneLine } from "../charts/zoneLine";
import ChartCard from "../components/ChartCard";
import Drawer from "../components/Drawer";
import { KpiTile, Legend, Loading, PageHeader } from "../components/ui";
import { healthIndex, labels, periods as t, severityName, systemName } from "../copy";
import { useData, type Family, type Period } from "../data";
import { fmtDateTime, fmtDuration, fmtPct, fmtSigned, toMs } from "../lib/format";
import { brand, severityColor } from "../theme";

const FAMILIES: Family[] = ["EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"];

export default function Periods() {
  const d = useData("periods");
  const s = useData("summary");
  const { id } = useParams();
  const navigate = useNavigate();
  const close = useCallback(() => navigate("/periods"), [navigate]);

  const ganttOption = useMemo(() => d && gantt({
    min: toMs(d.periods[0].start.slice(0, 8) + "01T00:00"), max: toMs(d.periods[d.periods.length - 1].end) + 5 * 86_400_000,
    items: d.periods.map((p) => ({
      id: p.id, label: t.label(p.n), from: toMs(p.start), to: toMs(p.end), color: severityColor[p.severity],
      text: `${severityName[p.severity]} · ${fmtDuration(p.durationMin)}`,
      tooltip: `<b>${t.label(p.n)}</b><br/>${fmtDateTime(p.start)} → ${fmtDateTime(p.end)}<br/>${severityName[p.severity]} severity · ${systemName[p.dominant]}`,
    })),
  }), [d]);

  const heatOption = useMemo(() => d && heatmap({
    x: FAMILIES.map((f) => systemName[f]), y: d.periods.map((p) => t.label(p.n)),
    cells: d.periods.flatMap((p, row) => FAMILIES.map((f, col) => [col, row, p.deviation[f]] as [number, number, number])),
    max: 3, ramp: ["#f1f4fb", brand.navyInk], format: (v) => v.toFixed(1),
  }), [d]);

  const onBar = useMemo(() => ({ click: (e: { data?: { id?: string } }) => { if (e.data?.id) navigate(`/periods/${e.data.id}`); } }), [navigate]);
  const onCell = useMemo(() => ({ click: (e: { value?: [number, number] }) => { if (e.value && d) navigate(`/periods/${d.periods[e.value[1]].id}`); } }), [navigate, d]);

  if (!d || !s || !ganttOption || !heatOption) return <Loading />;
  const longest = d.periods.reduce((a, b) => (b.durationMin > a.durationMin ? b : a), d.periods[0]);
  const open = d.periods.find((p) => p.id === id);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.question} />

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-label={labels.headline}>
        <KpiTile value={s.periods.total} label={t.tiles.total} />
        <KpiTile value={s.periods.high} label={t.tiles.high} />
        <KpiTile value={s.periods.multiSystem} label={t.tiles.multi} />
        <KpiTile value={fmtDuration(longest.durationMin)} label={t.tiles.longest} sub={`${t.label(longest.n)} · ${fmtDateTime(longest.start)}`} />
      </section>

      <ChartCard title={t.ganttTitle} sub={`${t.subtitle} ${t.ganttSub}`}
        table={{ columns: [labels.period, labels.start, labels.end, labels.duration, labels.severity, labels.mainSystem], rows: d.periods.map((p) => [t.label(p.n), fmtDateTime(p.start), fmtDateTime(p.end), fmtDuration(p.durationMin), severityName[p.severity], systemName[p.dominant]]) }}>
        <Chart option={ganttOption} height={380} label={t.ganttTitle} onEvents={onBar} />
        <Legend items={(["HIGH", "MODERATE", "LOW"] as const).map((k) => ({ name: labels.severityLegend(severityName[k]), color: severityColor[k] }))} />
        <ul className="sr-only">{d.periods.map((p) => <li key={p.id}><Link to={`/periods/${p.id}`}>{t.label(p.n)}</Link></li>)}</ul>
      </ChartCard>

      <ChartCard title={t.heatTitle} sub={t.heatSub}
        table={{ columns: [labels.period, ...FAMILIES.map((f) => systemName[f])], rows: d.periods.map((p) => [t.label(p.n), ...FAMILIES.map((f) => p.deviation[f].toFixed(2))]) }}>
        <Chart option={heatOption} height={460} label={t.heatTitle} onEvents={onCell} />
      </ChartCard>

      {open && <PeriodDrawer p={open} edges={d.bandEdges} onClose={close} />}
    </div>
  );
}

function PeriodDrawer({ p, edges, onClose }: { p: Period; edges: { watch: number; warning: number }; onClose: () => void }) {
  const option = useMemo(() => zoneLine({
    series: [{ name: healthIndex.name, data: p.series.map(([ts, v]) => [toMs(ts), v]), color: brand.navyInk }],
    edges, periods: [{ from: toMs(p.start), to: toMs(p.end), label: "" }],
  }), [p, edges]);
  const rows: [string, string][] = [
    [t.drawer.when, `${fmtDateTime(p.start)} → ${fmtDateTime(p.end)}`],
    [t.drawer.onset, fmtDateTime(p.onset)],
    [t.drawer.duration, fmtDuration(p.durationMin)],
    [t.drawer.severity, severityName[p.severity]],
    [t.drawer.dominant, systemName[p.dominant]],
    [t.drawer.systems, p.systems.map((f) => systemName[f]).join(", ")],
    [t.drawer.load, t.loadText(p.load, fmtSigned(p.feedChange))],
    [t.drawer.robust, t.drawer.robustVal(fmtPct(p.robustness))],
  ];
  return (
    <Drawer title={t.label(p.n)} onClose={onClose}>
      <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-3 text-sm">
        {rows.map(([k, v]) => <Fragment key={k}><dt className="font-semibold text-ink-muted">{k}</dt><dd className="text-ink">{v}</dd></Fragment>)}
      </dl>
      <h3 className="mt-6 text-sm font-semibold text-ink-muted">{t.drawer.chart}</h3>
      <Chart option={option} height={200} label={t.drawer.chart} />
      <Link to={`/console?t=${encodeURIComponent(p.onset)}`} className="btn-navy mt-6"><Play size={16} aria-hidden /> {t.drawer.replay}</Link>
      <p className="mt-4 text-xs text-ink-muted">{t.subtitle}</p>
    </Drawer>
  );
}
