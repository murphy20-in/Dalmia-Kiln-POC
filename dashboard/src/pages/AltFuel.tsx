import { ArrowRight, BadgeCheck, FlaskConical } from "lucide-react";
import Chart from "../charts/Chart";
import ChartCard from "../components/ChartCard";
import { HeroBand, Loading, PageHeader } from "../components/ui";
import { fuel as t, labels } from "../copy";
import { useData, type AfrCard } from "../data";
import { fmtMonth, fmtSigned } from "../lib/format";
import { brand, systemColor } from "../theme";
import type { Option } from "../charts/Chart";

const strengthStyle: Record<AfrCard["strength"], string> = {
  Consistent: "bg-navy text-white",
  "Lower confidence": "bg-navy-tint text-navy",
  Emerging: "bg-page text-ink-muted",
};

/** One small column chart per measure: small multiples instead of a dual axis. */
function monthBars(months: string[], values: number[], color: string, min: number): Option {
  return {
    grid: { left: 40, right: 8, top: 24, bottom: 24 },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => `${v.toFixed(1)} TPH` },
    xAxis: { type: "category", data: months, axisLabel: { color: brand.ink } },
    yAxis: { type: "value", min, splitNumber: 3 },
    series: [{ type: "bar", data: values, barWidth: "50%", itemStyle: { color, borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: "top", color: brand.ink, fontWeight: 600, formatter: (p: { value: number }) => p.value.toFixed(1) } }],
  };
}

export default function AltFuel() {
  const d = useData("afr");
  if (!d) return <Loading />;
  const months = d.monthly.map((m) => fmtMonth(m.month));
  const effect = (c: AfrCard) => (c.metric === "rho" ? fmtSigned(c.effect, 2) : fmtSigned(c.effect, c.unit === "TPH" ? 0 : 1));
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.question} />
      <HeroBand className="!p-8">
        <p className="text-3xl font-bold text-white">{t.hero}</p>
        <p className="mt-2 text-white/85">{t.heroSub(d.associated, d.augustConfirmed)}</p>
      </HeroBand>

      <section className="grid items-stretch gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr]" aria-label={labels.domino}>
        {t.domino.map((s, i) => (
          <div key={i} className="contents">
            <div className="card flex flex-col gap-2" style={{ borderTop: `4px solid ${[brand.navy, systemColor.COMBUSTION, systemColor.THERMAL][i]}` }}>
              <span className="eyebrow">{i + 1}</span>
              <h2 className="text-xl font-bold">{typeof s.title === "function" ? s.title(d.coalStepTph) : s.title}</h2>
              <p className="text-sm text-ink-muted">{s.body}</p>
            </div>
            {i < 2 && <ArrowRight className="hidden self-center text-ink-faint md:block" size={28} aria-hidden />}
          </div>
        ))}
      </section>

      <ChartCard title={t.monthlyTitle} table={{ columns: [labels.month, t.afrPanel, t.feedPanel], rows: d.monthly.map((m, i) => [months[i], m.afr, m.feed]) }}>
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-ink-muted">{t.afrPanel}</h3>
            <Chart option={monthBars(months, d.monthly.map((m) => m.afr), brand.navy, 0)} height={220} label={t.afrPanel} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink-muted">{t.feedPanel}</h3>
            <Chart option={monthBars(months, d.monthly.map((m) => m.feed), systemColor.COMBUSTION, 0)} height={220} label={t.feedPanel} />
          </div>
        </div>
      </ChartCard>

      <section>
        <h2 className="text-lg font-semibold">{t.cardsTitle}</h2>
        <p className="mb-3 text-sm text-ink-muted">{t.strengthHint} {t.caveat}</p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {d.cards.map((c) => (
            <article key={c.key} className="card flex flex-col gap-2">
              <span className={`self-start rounded-full px-2.5 py-0.5 text-xs font-semibold ${strengthStyle[c.strength]}`}>{c.strength}</span>
              <h3 className="font-semibold">{t.cards[c.key].title}</h3>
              <p className="text-sm text-ink-muted">{t.cards[c.key].body(effect(c))}</p>
              <p className={`mt-auto flex items-center gap-1.5 text-xs font-semibold ${c.augustConfirmed ? "text-normal-ink" : "text-ink-muted"}`}>
                <BadgeCheck size={14} aria-hidden /> {c.augustConfirmed ? t.august : t.notAugust}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="card flex flex-col gap-4 border-2 border-dashed border-navy/30 !shadow-none md:flex-row md:items-center">
        <FlaskConical size={36} className="shrink-0 text-navy" aria-hidden />
        <div>
          <h2 className="text-lg font-semibold">{t.deeperTitle}</h2>
          <p className="text-sm text-ink-muted">{t.deeperBody}</p>
          <ul className="mt-2 flex flex-wrap gap-2">{t.deeperItems.map((x) => <li key={x} className="chip">{x}</li>)}</ul>
          <p className="mt-2 text-sm font-semibold text-navy">{t.deeperUnlocks}</p>
        </div>
      </section>
    </div>
  );
}
