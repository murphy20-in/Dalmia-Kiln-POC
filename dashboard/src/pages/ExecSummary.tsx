import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, CircleDashed, Sparkles } from "lucide-react";
import { labels, summary as t } from "../copy";
import { useData } from "../data";
import { fmt1, fmtMonth, fmtPct } from "../lib/format";
import { CountUp, CtaBand, HeroBand, InsightCard, KpiTile, Loading, Stepper } from "../components/ui";
import { status } from "../theme";

const objectiveStyle = {
  delivered: { icon: CheckCircle2, color: status.N.ink },
  signals: { icon: Sparkles, color: "#2a469c" },
  next: { icon: CircleDashed, color: "#5f6368" },
};

export default function ExecSummary() {
  const s = useData("summary");
  const afr = useData("afr");
  if (!s || !afr) return <Loading />;
  const [jun, , aug] = s.kpiMonthly;
  return (
    <div className="flex flex-col gap-6">
      <HeroBand className="!py-8">
        <p className="text-sm font-semibold uppercase tracking-wider text-cyan-soft">{t.eyebrow}</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-bold leading-tight text-white">{t.heroTitle}</h1>
        <p className="mt-3 text-lg text-white/85">{t.heroSub(`${(s.rows / 1e6).toFixed(2)} million`)}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/console" className="btn-primary">{t.heroCta} <ArrowRight size={16} aria-hidden /></Link>
          <Link to="/roadmap" className="btn-ghost">{t.heroCta2}</Link>
        </div>
      </HeroBand>

      <section aria-labelledby="journey">
        <h2 id="journey" className="mb-3 text-lg font-semibold">{t.journeyTitle}</h2>
        <Stepper steps={t.journey} />
      </section>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-label={labels.headline}>
        <KpiTile value={<><CountUp to={s.rows / 1e6} format={(n) => n.toFixed(2)} /> M</>} label={t.kpis.rows.label} sub={t.kpis.rows.sub(s.tags)} />
        <KpiTile value={<CountUp to={s.periods.total} />} label={t.kpis.periods.label} sub={t.kpis.periods.sub} />
        <KpiTile value={<span>{fmt1(jun.median)} <span className="text-ink-faint">→</span> {fmt1(aug.median)}</span>} label={t.kpis.eff.label} sub={t.kpis.eff.sub} />
        <KpiTile value={<CountUp to={s.issuesTotal} />} label={t.kpis.issues.label} sub={t.kpis.issues.sub} />
      </section>

      <section aria-labelledby="findings">
        <h2 id="findings" className="mb-3 text-lg font-semibold">{t.findingsTitle}</h2>
        <div className="grid gap-4 lg:grid-cols-3">
          <InsightCard title={t.findings.drift.title} body={t.findings.drift.body} to="/efficiency" link={t.findings.drift.link}>
            <div className="flex h-28 items-end gap-4" aria-hidden>
              {s.zoneShares.map((z) => (
                <div key={z.month} className="flex flex-1 flex-col items-center gap-1">
                  <span className="text-sm font-bold num" style={{ color: status.A.ink }}>{fmtPct(z.warning)}</span>
                  <div className="w-full rounded-t" style={{ height: `${z.warning * 130}px`, background: status.A.fill }} />
                  <span className="text-xs text-ink-muted">{fmtMonth(z.month)}</span>
                </div>
              ))}
            </div>
          </InsightCard>
          <InsightCard title={t.findings.multi.title(s.periods.multiSystem, s.periods.total)} body={t.findings.multi.body} to="/periods" link={t.findings.multi.link}>
            <div className="grid grid-cols-6 gap-1.5" aria-hidden>
              {Array.from({ length: s.periods.total }, (_, i) => (
                <div key={i} className="h-7 rounded" style={{ background: i < s.periods.multiSystem ? "#2a469c" : "#c9d2ec" }} />
              ))}
            </div>
            <p className="text-xs text-ink-muted">
              <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-navy align-middle" /> {t.findings.multiLegend.many}
              <span className="ml-3 mr-1 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: "#c9d2ec" }} /> {t.findings.multiLegend.one}
            </p>
          </InsightCard>
          <InsightCard title={t.findings.fuel.title(afr.coalStepTph)} body={t.findings.fuel.body} to="/alternative-fuel" link={t.findings.fuel.link}>
            <div className="flex items-center gap-2 text-sm font-semibold" aria-hidden>
              <span className="rounded-lg bg-navy-tint px-3 py-2 text-navy-ink">{t.findings.fuelFrom}</span>
              <ArrowRight size={16} className="text-ink-faint" />
              <span className="rounded-lg bg-navy px-3 py-2 text-white">{t.findings.fuelTo(afr.coalStepTph)}</span>
            </div>
            <p className="text-xs text-ink-muted">{t.findings.fuelAfter}</p>
          </InsightCard>
        </div>
      </section>

      <section className="card" aria-labelledby="objectives">
        <h2 id="objectives" className="mb-4 text-lg font-semibold">{t.objectivesTitle}</h2>
        <ul className="grid gap-x-8 gap-y-3 md:grid-cols-2">
          {t.objectives.map((o, i) => {
            const st = objectiveStyle[o.status];
            return (
              <li key={o.name} className="flex items-start gap-3 border-b border-line pb-3">
                <st.icon size={20} className="mt-0.5 shrink-0" style={{ color: st.color }} aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold text-navy-ink">{i + 1}. {o.name}</span>
                    <span className="text-xs font-semibold" style={{ color: st.color }}>{t.objectiveStatus[o.status]}</span>
                  </div>
                  <p className="text-sm text-ink-muted">{o.note}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <CtaBand title={t.cta.title} body={t.cta.body} to="/roadmap" button={t.cta.button} />
    </div>
  );
}
