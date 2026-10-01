import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, CircleDashed, Sparkles } from "lucide-react";
import { ProcessLines } from "../components/Brand";
import { CountUp, HeroBand, InsightCard, KpiTile, Loading, NumberDot, SectionHeader, Stepper } from "../components/ui";
import { ask, brandLine, context, labels, summary as t } from "../copy";
import { useData } from "../data";
import { fmt1, fmtMonth, fmtPct } from "../lib/format";
import { issueColor, status } from "../theme";

const objectiveStyle = {
  delivered: { icon: CheckCircle2, className: "text-normal-ink" },
  signals: { icon: Sparkles, className: "text-navy" },
  next: { icon: CircleDashed, className: "text-ink-muted" },
};

const ISSUE_ORDER = ["critical", "high", "medium", "low", "info"] as const;

export default function ExecSummary() {
  const s = useData("summary");
  const afr = useData("afr");
  if (!s || !afr) return <Loading />;
  const medians = s.kpiMonthly.map((k) => k.median);
  const [jun, , aug] = s.kpiMonthly;
  const zJun = s.zoneShares[0];
  const zAug = s.zoneShares[s.zoneShares.length - 1];
  const maxWarning = Math.max(...s.zoneShares.map((z) => z.warning));
  return (
    <>
      {/* Level 1: brand → product → context → insight. The flagship hero. */}
      <section className="atmosphere" aria-labelledby="hero">
        <ProcessLines />
        <div className="mx-auto grid max-w-page gap-10 px-4 pb-20 pt-10 sm:px-8 lg:grid-cols-[1.3fr_1fr] lg:items-center lg:pb-24 lg:pt-12">
          <div>
            <p className="eyebrow-dark">{brandLine.product} · {context.plantShort}</p>
            <h1 id="hero" className="mt-4 max-w-2xl text-display font-semibold text-white sm:text-hero">{t.heroTitle}</h1>
            <p className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-eyebrow uppercase text-mist">
              <span className="rounded-full border border-sky/40 px-3 py-1 font-medium text-sky-soft">{t.heroPeriod}</span>
              <span>{t.eyebrow}</span>
            </p>
            <p className="mt-4 max-w-xl text-label text-mist">{t.heroSub(`${(s.rows / 1e6).toFixed(2)} million`)}</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link to="/console" className="btn-primary">{t.heroCta} <ArrowRight size={16} aria-hidden /></Link>
              <Link to="/roadmap" className="btn-ghost">{t.heroCta2} <ArrowRight size={16} aria-hidden /></Link>
            </div>
          </div>
          <section className="surface-glass p-6 sm:p-7" aria-labelledby="core">
            <h2 id="core" className="eyebrow-dark">{t.core.label}</h2>
            <p className="mt-3 text-lead font-semibold text-white">{t.core.lead}</p>
            <div className="mt-3 flex items-end gap-4 text-white num">
              <div><div className="text-numeral font-semibold">{fmtPct(zJun.warning)}</div><div className="mt-1 font-mono text-eyebrow uppercase text-mist">{t.core.from}</div></div>
              <span aria-hidden className="pb-6 text-title text-sky">→</span><span className="sr-only"> to </span>
              <div><div className="text-numeral font-semibold text-sky-soft">{fmtPct(zAug.warning)}</div><div className="mt-1 font-mono text-eyebrow uppercase text-mist">{t.core.to}</div></div>
            </div>
            <p className="mt-4 text-label text-mist">{t.core.sub}</p>
            <p className="mt-4 border-t border-haze/20 pt-4 text-caption text-mist">{t.core.foot(s.periods.total)}</p>
          </section>
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-page flex-col gap-10 px-4 pb-8 sm:px-8">
        {/* Level 2: the evidence, rising out of the hero */}
        <section className="relative -mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label={labels.headline}>
          <KpiTile label={t.kpis.rows.label} value={<CountUp to={s.rows / 1e6} format={(n) => n.toFixed(2)} />} unit="M" sub={t.kpis.rows.sub(s.tags)} evidence={t.evidence.rows} />
          <KpiTile label={t.kpis.periods.label} value={<CountUp to={s.periods.total} />} sub={t.kpis.periods.sub(s.periods.high)} evidence={t.evidence.periods}
            micro={<div className="flex gap-[3px]">{Array.from({ length: s.periods.total }, (_, i) => <span key={i} className={`h-5 w-1 rounded-full ${i < s.periods.high ? "bg-navy-ink" : "bg-navy-line"}`} />)}</div>} />
          <KpiTile label={t.kpis.eff.label} value={<span className="whitespace-nowrap text-title">{fmt1(jun.median)}<span className="mx-1.5 text-ink-faint" aria-hidden>→</span><span className="sr-only"> to </span>{fmt1(aug.median)}</span>} sub={t.kpis.eff.sub} evidence={t.evidence.eff}
            micro={<div className="flex h-8 items-end gap-1">{medians.map((m, i) => <span key={i} className={`w-2 rounded-t-sm ${i === medians.length - 1 ? "bg-navy-ink" : "bg-indigo/60"}`} style={{ height: `${Math.max(12, (m / Math.max(...medians)) * 100)}%` }} />)}</div>} />
          <KpiTile label={t.kpis.issues.label} value={<CountUp to={s.issuesTotal} />} sub={t.kpis.issues.sub(s.issues)} evidence={t.evidence.issues}
            micro={<div className="flex h-1.5 w-16 overflow-hidden rounded-full">{ISSUE_ORDER.map((k) => <span key={k} style={{ width: `${(s.issues[k] / s.issuesTotal) * 100}%`, background: issueColor[k] }} />)}</div>} />
        </section>

        {/* What we found: an open layout, not three boxes */}
        <section aria-labelledby="findings">
          <SectionHeader id="findings" title={t.findingsTitle} />
          <div className="grid gap-x-10 gap-y-8 lg:grid-cols-3">
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

        {/* Where this goes */}
        <section aria-labelledby="journey">
          <SectionHeader id="journey" title={t.journeyTitle} />
          <Stepper steps={t.journey} />
        </section>

        <section className="card" aria-labelledby="objectives">
          <SectionHeader id="objectives" title={t.objectivesTitle} />
          <ul className="grid gap-x-10 md:grid-cols-2">
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

        {/* The ask: the closing statement, in the same atmosphere as the hero */}
        <HeroBand>
          <div className="grid gap-8 p-7 sm:p-9 lg:grid-cols-[1fr_1.2fr] lg:items-center">
            <div>
              <p className="eyebrow-dark">{t.nextTitle}</p>
              <h2 className="mt-2 text-lead font-semibold">{t.nextBody}</h2>
              <Link to="/roadmap" className="btn-primary mt-5">{t.heroCta2} <ArrowRight size={16} aria-hidden /></Link>
            </div>
            <ol className="grid gap-3 sm:grid-cols-2">
              {ask.items.map((a, i) => (
                <li key={a} className="surface-glass flex items-start gap-2.5 p-4 text-label text-white/90">
                  <NumberDot n={i + 1} tone="sky" />{a}
                </li>
              ))}
            </ol>
          </div>
        </HeroBand>
      </div>
    </>
  );
}
