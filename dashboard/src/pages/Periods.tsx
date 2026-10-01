import { Fragment, useCallback, useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Play } from "lucide-react";
import Chart from "../charts/Chart";
import { hbars } from "../charts/bars";
import { gantt } from "../charts/gantt";
import { heatmap } from "../charts/heatmap";
import { zoneLine } from "../charts/zoneLine";
import ChartCard from "../components/ChartCard";
import Drawer, { DrawerSection } from "../components/Drawer";
import { Badge, KpiTile, Loading, PageHeader, PeriodEvidence, SectionHeader } from "../components/ui";
import { evidence, healthIndex, labels, periods as t, severityName, systemName } from "../copy";
import { useData, type Family, type Period, type Severity } from "../data";
import { fmtDateTime, fmtDuration, fmtPct, fmtSigned, toMs } from "../lib/format";
import { brand, severityColor, systemColor } from "../theme";

const FAMILIES: Family[] = ["EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"];
const SEVERITIES: Severity[] = ["HIGH", "MODERATE", "LOW"];

/** Severity as a word with a magnitude swatch (navy ramp): never colour alone. */
const SeverityTag = ({ s }: { s: Severity }) => (
  <span className="inline-flex items-center gap-1.5 text-label font-medium text-ink">
    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: severityColor[s] }} aria-hidden />{severityName[s]}
  </span>
);

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
      tip: {
        title: t.label(p.n), sub: `${fmtDateTime(p.start)} → ${fmtDateTime(p.end)}`,
        rows: [
          { label: labels.severity, value: severityName[p.severity], color: severityColor[p.severity] },
          { label: labels.mainSystem, value: systemName[p.dominant] },
          { label: labels.duration, value: fmtDuration(p.durationMin) },
        ],
        note: `${evidence.kpiDerived} · ${evidence.notValidated}`,
      },
    })),
  }), [d]);

  const heatOption = useMemo(() => d && heatmap({
    x: FAMILIES.map((f) => systemName[f]), y: d.periods.map((p) => t.label(p.n)), leftWidth: 72,
    cells: d.periods.flatMap((p, row) => FAMILIES.map((f, col) => [col, row, p.deviation[f]] as [number, number, number])),
    max: 3, ramp: [brand.heatLow, brand.navyInk], format: (v) => v.toFixed(1), valueLabel: t.matrixLabel,
  }), [d]);

  const onBar = useMemo(() => ({ click: (e: { data?: { id?: string } }) => { if (e.data?.id) navigate(`/periods/${e.data.id}`); } }), [navigate]);
  const onCell = useMemo(() => ({ click: (e: { value?: [number, number] }) => { if (e.value && d) navigate(`/periods/${d.periods[e.value[1]].id}`); } }), [navigate, d]);

  if (!d || !s || !ganttOption || !heatOption) return <Loading />;
  const longest = d.periods.reduce((a, b) => (b.durationMin > a.durationMin ? b : a), d.periods[0]);
  const open = d.periods.find((p) => p.id === id);
  const sevLegend = SEVERITIES.map((k) => ({ name: labels.severityLegend(severityName[k]), color: severityColor[k] }));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.question} badges={<PeriodEvidence plural />} />

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-label={labels.headline}>
        <KpiTile label={t.tiles.total} value={s.periods.total} evidence={evidence.kpiDerivedPlural} />
        <KpiTile label={t.tiles.high} value={s.periods.high} evidence={t.tiles.highNote} />
        <KpiTile label={t.tiles.multi} value={s.periods.multiSystem} evidence={t.tiles.multiNote(s.periods.total)} />
        <KpiTile label={t.tiles.longest} value={<span className="text-title sm:whitespace-nowrap">{fmtDuration(longest.durationMin)}</span>} evidence={`${t.label(longest.n)} · ${fmtDateTime(longest.start)}`} />
      </section>

      <ChartCard title={t.ganttTitle} sub={`${t.subtitle} ${t.ganttSub}`} legend={sevLegend} source={t.source}
        table={{ columns: [labels.period, labels.start, labels.end, labels.duration, labels.severity, labels.mainSystem], rows: d.periods.map((p) => [t.label(p.n), fmtDateTime(p.start), fmtDateTime(p.end), fmtDuration(p.durationMin), severityName[p.severity], systemName[p.dominant]]) }}>
        <Chart option={ganttOption} height={340} label={t.ganttTitle} onEvents={onBar} />
      </ChartCard>

      <section className="card !p-0" aria-labelledby="index">
          <div className="px-6 pt-5"><SectionHeader id="index" title={t.indexTitle} sub={t.indexSub} /></div>
          <div className="overflow-x-auto px-3 pb-3">
            <table className="data-table">
              <caption className="sr-only">{t.indexTitle}. {evidence.kpiDerivedPlural}; {evidence.notValidatedPlural.toLowerCase()}.</caption>
              <thead>
                <tr>
                  <th scope="col" className="pl-3">{labels.period}</th>
                  <th scope="col">{t.drawer.onset}</th>
                  <th scope="col" className="text-right">{labels.duration}</th>
                  <th scope="col">{labels.severity}</th>
                  <th scope="col">{labels.mainSystem}</th>
                  <th scope="col" className="text-right">{t.drawer.systems}</th>
                </tr>
              </thead>
              <tbody>
                {d.periods.map((p) => (
                  <tr key={p.id} className={`cursor-pointer ${p.id === id ? "!bg-navy-tint" : ""}`} onClick={() => navigate(`/periods/${p.id}`)}>
                    <td className="whitespace-nowrap pl-3"><Link to={`/periods/${p.id}`} className="font-semibold text-navy hover:underline" aria-current={p.id === id ? "true" : undefined} onClick={(e) => e.stopPropagation()}>{t.label(p.n)}</Link></td>
                    <td className="num whitespace-nowrap">{fmtDateTime(p.onset)}</td>
                    <td className="num whitespace-nowrap text-right">{fmtDuration(p.durationMin)}</td>
                    <td><SeverityTag s={p.severity} /></td>
                    <td className="whitespace-nowrap">
                      <span className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle" style={{ background: systemColor[p.dominant] }} aria-hidden />{systemName[p.dominant]}
                    </td>
                    <td className="num text-right">{t.systemsCount(p.systems.length)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      </section>

      <ChartCard title={t.heatTitle} sub={t.heatSub}
          table={{ columns: [labels.period, ...FAMILIES.map((f) => systemName[f])], rows: d.periods.map((p) => [t.label(p.n), ...FAMILIES.map((f) => p.deviation[f].toFixed(2))]) }}>
        <Chart option={heatOption} height={430} label={t.heatTitle} onEvents={onCell} />
      </ChartCard>

      {open && <PeriodDrawer p={open} edges={d.bandEdges} onClose={close} />}
    </div>
  );
}

function PeriodDrawer({ p, edges, onClose }: { p: Period; edges: { watch: number; warning: number }; onClose: () => void }) {
  const context = useMemo(() => zoneLine({
    series: [{ name: healthIndex.name, data: p.series.map(([ts, v]) => [toMs(ts), v]), color: brand.navyInk }],
    edges, periods: [{ from: toMs(p.start), to: toMs(p.end), label: t.label(p.n) }], note: `${evidence.kpiDerived} shaded`,
  }), [p, edges]);
  const systems = useMemo(() => hbars({
    items: FAMILIES.map((f) => ({ name: systemName[f], value: p.deviation[f], color: systemColor[f] })),
    max: Math.max(3, ...FAMILIES.map((f) => p.deviation[f])), unit: t.matrixLabel,
  }), [p]);
  const facts: [string, string][] = [
    [t.drawer.when, `${fmtDateTime(p.start)} → ${fmtDateTime(p.end)}`],
    [t.drawer.onset, fmtDateTime(p.onset)],
    [t.drawer.duration, fmtDuration(p.durationMin)],
    [t.drawer.classification, evidence.kpiDerived],
    [t.drawer.robust, t.drawer.robustVal(fmtPct(p.robustness))],
  ];
  const changed: [string, string][] = [
    [t.drawer.dominant, systemName[p.dominant]],
    [t.drawer.systems, p.systems.map((f) => systemName[f]).join(", ")],
    [t.drawer.load, t.loadText(p.load, fmtSigned(p.feedChange))],
  ];
  return (
    <Drawer title={t.label(p.n)} onClose={onClose}
      meta={<><Badge tone="navy">{severityName[p.severity]} {labels.severity.toLowerCase()}</Badge><PeriodEvidence /></>}>
      <DrawerSection title={t.drawer.factsTitle}><Facts rows={facts} /></DrawerSection>
      <DrawerSection title={t.drawer.changedTitle}><Facts rows={changed} /></DrawerSection>
      <DrawerSection title={t.drawer.evidenceTitle} sub={t.drawer.evidenceSub}>
        <Chart option={systems} height={170} label={FAMILIES.map((f) => `${systemName[f]} ${p.deviation[f].toFixed(1)}`).join(", ")} />
      </DrawerSection>
      <DrawerSection title={t.drawer.contextTitle} sub={t.drawer.chart}>
        <Chart option={context} height={190} label={t.drawer.chart} />
      </DrawerSection>
      <div className="flex flex-col gap-3 border-t border-line pt-5">
        <Link to={`/console?t=${encodeURIComponent(p.onset)}`} className="btn-navy self-start"><Play size={16} aria-hidden /> {t.drawer.replay}</Link>
        <p className="text-caption text-ink-muted">{t.subtitle}</p>
      </div>
    </Drawer>
  );
}

const Facts = ({ rows }: { rows: [string, string][] }) => (
  <dl className="grid grid-cols-[9rem_1fr] gap-x-4 gap-y-2.5 text-label">
    {rows.map(([k, v]) => <Fragment key={k}><dt className="text-ink-muted">{k}</dt><dd className="text-ink">{v}</dd></Fragment>)}
  </dl>
);
