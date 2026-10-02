import { BadgeCheck, CircleDashed, FlaskConical } from "lucide-react";
import Chart from "../charts/Chart";
import { monthBars } from "../charts/bars";
import ChartCard from "../components/ChartCard";
import { Badge, Lead, Loading, NumberDot, Page, SectionHeader } from "../components/ui";
import { fuel as t, labels, nav } from "../copy";
import { useData, type AfrCard } from "../data";
import { fmtMonth, fmtSigned } from "../lib/format";
import { chart } from "../theme";

const strengthTone: Record<AfrCard["strength"], "brand" | "tint" | "outline"> = {
  Consistent: "brand",
  "Lower confidence": "tint",
  Emerging: "outline",
};

export default function AltFuel() {
  const d = useData("afr");
  if (!d) return <Loading />;
  const months = d.monthly.map((m) => fmtMonth(m.month));
  const effect = (c: AfrCard) => (c.metric === "rho" ? fmtSigned(c.effect, 2) : fmtSigned(c.effect, c.unit === "TPH" ? 0 : 1));
  return (
    <Page eyebrow={nav.groups.intelligence} title={t.title} question={t.question}>
      <Lead sub={t.heroSub(d.associated, d.augustConfirmed)}>{t.hero}</Lead>

      {/* The sequence seen in the data: three linked steps, not proven causes */}
      <section className="card !p-0" aria-labelledby="domino">
        <div className="px-6 pt-5"><SectionHeader id="domino" title={labels.domino} sub={t.caveat} /></div>
        <ol className="grid border-t border-line md:grid-cols-3 md:divide-x md:divide-line">
          {t.domino.map((s, i) => (
            <li key={i} className="relative flex gap-3 border-b border-line p-5 last:border-b-0 md:border-b-0">
              <NumberDot n={i + 1} tone={i === 1 ? "brand" : "tint"} />
              <div>
                <h3 className="t-card">{typeof s.title === "function" ? s.title(d.coalStepTph) : s.title}</h3>
                <p className="mt-1 text-label text-ink-muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <ChartCard title={t.monthlyTitle} source={t.source} table={{ columns: [labels.month, t.afrPanel, t.feedPanel], rows: d.monthly.map((m, i) => [months[i], m.afr, m.feed]) }}>
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="t-label">{t.afrPanel}</h3>
            <Chart option={monthBars({ months, values: d.monthly.map((m) => m.afr), color: chart.primary, unit: t.afrPanel })} height={210} label={t.afrPanel} />
          </div>
          <div>
            <h3 className="t-label">{t.feedPanel}</h3>
            <Chart option={monthBars({ months, values: d.monthly.map((m) => m.feed), color: chart.compare, unit: t.feedPanel })} height={210} label={t.feedPanel} />
          </div>
        </div>
      </ChartCard>

      <section aria-labelledby="cards">
        <SectionHeader id="cards" title={t.cardsTitle} sub={t.strengthHint} />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {d.cards.map((c) => (
            <article key={c.key} className="card flex flex-col gap-2 !p-5">
              <Badge tone={strengthTone[c.strength]} className="self-start">{c.strength}</Badge>
              <h3 className="t-card leading-snug">{t.cards[c.key].title}</h3>
              <p className="text-label text-ink-muted">{t.cards[c.key].body(effect(c))}</p>
              <p className={`mt-auto flex items-center gap-1.5 border-t border-line pt-3 text-caption font-semibold ${c.augustConfirmed ? "text-normal-ink" : "text-ink-muted"}`}>
                {c.augustConfirmed ? <BadgeCheck size={14} aria-hidden /> : <CircleDashed size={14} aria-hidden />} {c.augustConfirmed ? t.august : t.notAugust}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="card-dashed flex flex-col gap-4 md:flex-row md:items-start" aria-labelledby="deeper">
        <FlaskConical size={28} className="shrink-0 text-brunswick" aria-hidden />
        <div>
          <h2 id="deeper" className="t-section">{t.deeperTitle}</h2>
          <p className="mt-1 text-label text-ink-muted">{t.deeperBody}</p>
          <ul className="mt-3 flex flex-wrap gap-2">{t.deeperItems.map((x) => <li key={x}><Badge>{x}</Badge></li>)}</ul>
          <p className="mt-3 text-label font-semibold text-brunswick">{t.deeperUnlocks}</p>
        </div>
      </section>
    </Page>
  );
}
