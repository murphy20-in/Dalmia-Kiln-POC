import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, CircleDashed, Sparkles } from "lucide-react";
import { ask, labels, summary as t } from "../copy";
import { useData } from "../data";
import { fmt1, fmtMonth, fmtPct } from "../lib/format";
import { CountUp, HeroBand, InsightCard, KpiTile, Loading, NumberDot, SectionHeader, Stepper } from "../components/ui";
import { status } from "../theme";

const objectiveStyle = {
  delivered: { icon: CheckCircle2, className: "text-normal-ink" },
  signals: { icon: Sparkles, className: "text-navy" },
  next: { icon: CircleDashed, className: "text-ink-muted" },
};

export default function ExecSummary() {
  const s = useData("summary");
  const afr = useData("afr");
  if (!s || !afr) return <Loading />;
  const [jun, , aug] = s.kpiMonthly;
  const zJun = s.zoneShares[0];
  const zAug = s.zoneShares[s.zoneShares.length - 1];
  const maxWarning = Math.max(...s.zoneShares.map((z) => z.warning));
  return (
    <div className="flex flex-col gap-6">
      {/* Level 1: what this is, what it found, and what Dalmia provides next */}
      <HeroBand className="grid lg:grid-cols-[1.6fr_1fr]">
        <div className="p-8 pl-9">
          <p className="text-label font-semibold text-cyan-soft">{t.eyebrow}</p>
          <h1 className="mt-2 max-w-2xl text-display font-bold text-white">{t.heroTitle}</h1>
          <p className="mt-3 max-w-2xl text-body text-white/85">{t.thesis(fmtPct(zJun.warning), fmtPct(zAug.warning), s.periods.total)}</p>
          <p className="mt-1 text-label text-white/60">{t.heroSub(`${(s.rows / 1e6).toFixed(2)} million`)}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/console" className="btn-primary">{t.heroCta} <ArrowRight size={16} aria-hidden /></Link>
          </div>
        </div>
        <aside className="border-t border-white/10 bg-white/[0.04] p-6 lg:border-l lg:border-t-0" aria-labelledby="next">
          <h2 id="next" className="text-card font-semibold text-white">{t.nextTitle}</h2>
          <p className="mt-1 text-label text-white/70">{t.nextBody}</p>
          <ol className="mt-4 flex flex-col gap-2.5">
            {ask.items.map((a, i) => (
              <li key={a} className="flex items-start gap-2.5 text-label text-white/90">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan text-caption font-bold text-navy-ink">{i + 1}</span>{a}
              </li>
            ))}
          </ol>
          <Link to="/roadmap" className="mt-5 inline-flex items-center gap-1 text-label font-semibold text-cyan-soft hover:text-white hover:underline">
            {t.heroCta2} <ArrowRight size={14} aria-hidden />
          </Link>
        </aside>
      </HeroBand>

      {/* Key evidence */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label={labels.headline}>
        <KpiTile label={t.kpis.rows.label} value={<CountUp to={s.rows / 1e6} format={(n) => n.toFixed(2)} />} unit="M" sub={t.kpis.rows.sub(s.tags)} evidence={t.evidence.rows} />
        <KpiTile label={t.kpis.periods.label} value={<CountUp to={s.periods.total} />} sub={t.kpis.periods.sub(s.periods.high)} evidence={t.evidence.periods} />
        <KpiTile label={t.kpis.eff.label} value={<span>{fmt1(jun.median)}<span className="mx-1.5 text-ink-faint" aria-hidden>→</span><span className="sr-only"> to </span>{fmt1(aug.median)}</span>} sub={t.kpis.eff.sub} evidence={t.evidence.eff} />
        <KpiTile label={t.kpis.issues.label} value={<CountUp to={s.issuesTotal} />} sub={t.kpis.issues.sub(s.issues)} evidence={t.evidence.issues} />
      </section>

      {/* What we found */}
      <section aria-labelledby="findings">
        <SectionHeader id="findings" title={t.findingsTitle} />
        <div className="grid gap-4 lg:grid-cols-3">
          <InsightCard title={t.findings.drift.title} body={t.findings.drift.body} to="/efficiency" link={t.findings.drift.link}>
            <div className="flex h-28 items-end gap-4" aria-hidden>
              {s.zoneShares.map((z) => (
                <div key={z.month} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
                  <span className="text-label font-bold num" style={{ color: status.A.ink }}>{fmtPct(z.warning)}</span>
                  <div className="w-full rounded-t-sm" style={{ height: `${(z.warning / maxWarning) * 64}%`, background: status.A.fill }} />
                  <span className="text-caption text-ink-muted">{fmtMonth(z.month)}</span>
                </div>
              ))}
            </div>
          </InsightCard>
          <InsightCard title={t.findings.multi.title(s.periods.multiSystem, s.periods.total)} body={t.findings.multi.body} to="/periods" link={t.findings.multi.link}>
            <div className="grid grid-cols-6 gap-1.5" aria-hidden>
              {Array.from({ length: s.periods.total }, (_, i) => (
                <div key={i} className={`h-7 rounded-sm ${i < s.periods.multiSystem ? "bg-navy" : "bg-navy-line"}`} />
              ))}
            </div>
            <p className="flex flex-wrap gap-x-3 text-caption text-ink-muted">
              <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-navy align-middle" aria-hidden />{t.findings.multiLegend.many}</span>
              <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-navy-line align-middle" aria-hidden />{t.findings.multiLegend.one}</span>
            </p>
          </InsightCard>
          <InsightCard title={t.findings.fuel.title(afr.coalStepTph)} body={t.findings.fuel.body} to="/alternative-fuel" link={t.findings.fuel.link}>
            <div className="flex flex-wrap items-center gap-2 text-label font-semibold" aria-hidden>
              <span className="rounded-panel bg-navy-tint px-3 py-2 text-navy-ink">{t.findings.fuelFrom}</span>
              <ArrowRight size={16} className="text-ink-faint" />
              <span className="rounded-panel bg-navy px-3 py-2 text-white">{t.findings.fuelTo(afr.coalStepTph)}</span>
            </div>
            <p className="text-caption text-ink-muted">{t.findings.fuelAfter}</p>
          </InsightCard>
        </div>
      </section>

      {/* Why it matters / what happens next */}
      <section aria-labelledby="journey">
        <SectionHeader id="journey" title={t.journeyTitle} />
        <Stepper steps={t.journey} />
      </section>

      <section className="card" aria-labelledby="objectives">
        <SectionHeader id="objectives" title={t.objectivesTitle} />
        <ul className="grid gap-x-8 md:grid-cols-2">
          {t.objectives.map((o, i) => {
            const st = objectiveStyle[o.status];
            return (
              <li key={o.name} className="flex items-start gap-3 border-b border-line py-3">
                <NumberDot n={i + 1} tone="tint" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <span className="text-label font-semibold text-navy-ink">{o.name}</span>
                    <span className={`inline-flex items-center gap-1 text-caption font-semibold ${st.className}`}><st.icon size={13} aria-hidden />{t.objectiveStatus[o.status]}</span>
                  </div>
                  <p className="mt-0.5 text-label text-ink-muted">{o.note}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
