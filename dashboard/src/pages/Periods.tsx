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
import { Badge, KpiTile, Loading, Page, PeriodEvidence } from "../components/ui";
import { evidence, healthIndex, labels, nav, periods as t, severityName, systemName } from "../copy";
import { useData, type Family, type Period, type Severity } from "../data";
import { fmtDateTime, fmtDuration, fmtPct, fmtSigned, fmtStamp, toMs } from "../lib/format";
import { chart, semantic, severityColor, systemColor } from "../theme";

const FAMILIES: Family[] = ["EFFICIENCY", "COMBUSTION", "THERMAL", "DRAFT_PRESSURE", "STABILITY"];
const SEVERITIES: Severity[] = ["HIGH", "MODERATE", "LOW"];
const monthName = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", month: "long", year: "numeric" });

/** The vertical timeline: Brunswick base, Emerald markers, orange only for high severity. Each item is a link to its evidence drawer. */
function Timeline({ periods, openId }: { periods: Period[]; openId?: string }) {
  const groups = useMemo(() => {
    const out: { month: string; items: Period[] }[] = [];
    for (const p of periods) {
      const month = monthName.format(toMs(p.start));
      const last = out[out.length - 1];
      if (last?.month === month) last.items.push(p); else out.push({ month, items: [p] });
    }
    return out;
  }, [periods]);
  return (
    <section className="surface-dark p-5 sm:p-6 lg:col-span-5" aria-labelledby="timeline">
      <p className="eyebrow-dark">{t.indexTitle}</p>
      <h2 id="timeline" className="mt-1 text-section font-semibold">{t.timelineTitle}</h2>
      <p className="mt-1 text-label text-mist">{t.indexSub}</p>
      <p className="mt-1 flex items-center gap-1.5 text-caption text-sage"><span aria-hidden className="h-2 w-2 rounded-full bg-dalmia-orange" />{t.timelineNote}</p>
      <div className="mt-5 flex flex-col gap-6">
        {groups.map((g) => (
          <div key={g.month}>
            <h3 className="font-mono !text-eyebrow font-medium uppercase !text-sage">{g.month}</h3>
            <ol className="relative ml-[7px] mt-3 border-l border-moss">
              {g.items.map((p) => {
                const high = p.severity === "HIGH";
                const open = p.id === openId;
                return (
                  <li key={p.id} className="relative pb-3 pl-5 last:pb-0">
                    <span aria-hidden className={`absolute -left-[7px] top-4 h-3.5 w-3.5 rounded-full border-2 border-brunswick ${high ? "bg-dalmia-orange" : "bg-emerald"} ${open ? "ring-2 ring-white" : ""}`} />
                    <Link to={`/periods/${p.id}`} aria-current={open ? "page" : undefined}
                      className={`block rounded-panel px-3 py-2.5 transition-colors duration-fast hover:bg-white/[0.07] ${open ? "bg-white/[0.09]" : ""}`}>
                      <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                        <span className="text-card font-semibold text-white">{t.label(p.n)}</span>
                        <span className="num font-mono text-caption text-sage">{fmtStamp(p.onset)}</span>
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-label text-mist">
                        <span className={high ? "font-semibold text-dalmia-orange" : ""}>{severityName[p.severity]} {labels.severity.toLowerCase()}</span>
                        <span>{systemName[p.dominant]}</span>
                        <span className="num">{fmtDuration(p.durationMin)}</span>
                        <span className="num">{t.systemsCount(p.systems.length)}</span>
                      </span>
                      <span className="mt-1 block text-caption text-sage">{evidence.kpiDerived} · {evidence.notValidated}</span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          </div>
        ))}
      </div>
    </section>
  );
}

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
    max: 3, ramp: [semantic.heatLow, semantic.textPrimary], format: (v) => v.toFixed(1), valueLabel: t.matrixLabel,
  }), [d]);

  const onBar = useMemo(() => ({ click: (e: { data?: { id?: string } }) => { if (e.data?.id) navigate(`/periods/${e.data.id}`); } }), [navigate]);
  const onCell = useMemo(() => ({ click: (e: { value?: [number, number] }) => { if (e.value && d) navigate(`/periods/${d.periods[e.value[1]].id}`); } }), [navigate, d]);

  if (!d || !s || !ganttOption || !heatOption) return <Loading />;
  const longest = d.periods.reduce((a, b) => (b.durationMin > a.durationMin ? b : a), d.periods[0]);
  const open = d.periods.find((p) => p.id === id);
  const sevLegend = SEVERITIES.map((k) => ({ name: labels.severityLegend(severityName[k]), color: severityColor[k] }));

  return (
    <Page eyebrow={nav.groups.intelligence} title={t.title} question={t.question} badges={<PeriodEvidence plural dark />}>
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-label={labels.headline}>
        <KpiTile label={t.tiles.total} value={s.periods.total} evidence={evidence.kpiDerivedPlural} />
        <KpiTile label={t.tiles.high} value={s.periods.high} evidence={t.tiles.highNote} />
        <KpiTile label={t.tiles.multi} value={s.periods.multiSystem} evidence={t.tiles.multiNote(s.periods.total)} />
        <KpiTile label={t.tiles.longest} value={<span className="text-title sm:whitespace-nowrap">{fmtDuration(longest.durationMin)}</span>} evidence={`${t.label(longest.n)} · ${fmtDateTime(longest.start)}`} />
      </section>

      <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
        <Timeline periods={d.periods} openId={id} />
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-7">
          <ChartCard title={t.ganttTitle} sub={`${t.subtitle} ${t.ganttSub}`} legend={sevLegend} source={t.source}
            table={{ columns: [labels.period, labels.start, labels.end, labels.duration, labels.severity, labels.mainSystem], rows: d.periods.map((p) => [t.label(p.n), fmtDateTime(p.start), fmtDateTime(p.end), fmtDuration(p.durationMin), severityName[p.severity], systemName[p.dominant]]) }}>
            <Chart option={ganttOption} height={340} label={t.ganttTitle} onEvents={onBar} />
          </ChartCard>
          <ChartCard title={t.heatTitle} sub={t.heatSub}
            table={{ columns: [labels.period, ...FAMILIES.map((f) => systemName[f])], rows: d.periods.map((p) => [t.label(p.n), ...FAMILIES.map((f) => p.deviation[f].toFixed(2))]) }}>
            <Chart option={heatOption} height={430} label={t.heatTitle} onEvents={onCell} />
          </ChartCard>
        </div>
      </div>

      {open && <PeriodDrawer p={open} edges={d.bandEdges} onClose={close} />}
    </Page>
  );
}

function PeriodDrawer({ p, edges, onClose }: { p: Period; edges: { watch: number; warning: number }; onClose: () => void }) {
  const context = useMemo(() => zoneLine({
    series: [{ name: healthIndex.name, data: p.series.map(([ts, v]) => [toMs(ts), v]), color: chart.primary }],
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
    <Drawer title={t.label(p.n)} eyebrow={t.drawer.eyebrow(fmtStamp(p.onset))} onClose={onClose}
      meta={<><Badge tone="brand">{severityName[p.severity]} {labels.severity.toLowerCase()}</Badge><PeriodEvidence /></>}>
      <DrawerSection title={t.drawer.factsTitle}><Facts rows={facts} /></DrawerSection>
      <DrawerSection title={t.drawer.changedTitle}><Facts rows={changed} /></DrawerSection>
      <DrawerSection title={t.drawer.evidenceTitle} sub={t.drawer.evidenceSub}>
        <Chart option={systems} height={170} label={FAMILIES.map((f) => `${systemName[f]} ${p.deviation[f].toFixed(1)}`).join(", ")} />
      </DrawerSection>
      <DrawerSection title={t.drawer.contextTitle} sub={t.drawer.chart}>
        <Chart option={context} height={190} label={t.drawer.chart} />
      </DrawerSection>
      <div className="flex flex-col gap-3 border-t border-line pt-5">
        <Link to={`/console?t=${encodeURIComponent(p.onset)}`} className="btn-brand self-start"><Play size={16} aria-hidden /> {t.drawer.replay}</Link>
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
