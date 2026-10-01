import { useMemo, useState } from "react";
import { Check, CheckCircle2, Lock, Printer, RotateCcw } from "lucide-react";
import { Badge, HeroBand, NumberDot, Page, SectionHeader, Stepper } from "../components/ui";
import { ask, nav, roadmap as t, summary, value as v } from "../copy";
import { computeValue, type ValueInputs } from "../lib/value";
import { fmtInt, fmtRupees } from "../lib/format";

// Round placeholder values, shown with a "placeholder" hint until the plant types its own.
const PLACEHOLDERS: ValueInputs = {
  clinkerTpd: 5000, contributionPerT: 1500, runningDays: 330,
  stoppageHours: 120, depositSharePct: 40, convertiblePct: 50, downtimeSavedPct: 50,
  heatKcalPerKg: 720, fuelPerMkcal: 1500, efficiencyGainPct: 0, // 0 until the plant sets it: Stage 1 measured process drift, not a fuel-efficiency loss
};
const GROUPS: { title: string; keys: (keyof ValueInputs)[] }[] = [
  { title: v.groups.production, keys: ["clinkerTpd", "contributionPerT", "stoppageHours", "depositSharePct", "convertiblePct", "downtimeSavedPct"] },
  { title: v.groups.fuel, keys: ["runningDays", "heatKcalPerKg", "fuelPerMkcal", "efficiencyGainPct"] },
];

const clamp = (k: keyof ValueInputs, n: number) => Math.max(0, v.inputs[k].unit === "%" ? Math.min(100, n) : n);

type Stage = (typeof t.stages)[number];

/** Demonstrated stage = solid card with a check. Everything else = dashed outline with a lock: it is not operational. */
function StageCard({ s, i }: { s: Stage; i: number }) {
  const done = i === 0;
  const next = i === 1;
  return (
    <li className={`flex flex-col gap-3 p-5 ${done ? "card !p-5 shadow-[inset_0_3px_0_theme(colors.normal.DEFAULT)]" : "rounded-card border border-dashed border-line-strong bg-white/60"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{s.tag}</span>
        <Badge tone={done ? "positive" : next ? "navy" : "outline"} icon={done ? CheckCircle2 : Lock}>{s.when}</Badge>
      </div>
      <h3 className="text-section font-semibold text-navy-ink">{s.title}</h3>
      <div>
        <h4 className="t-caption font-semibold">{t.youGet}</h4>
        <ul className="mt-1.5 flex flex-col gap-1">
          {s.get.map((g) => <li key={g} className="flex gap-2 text-label text-ink-body"><Check size={14} className={`mt-0.5 shrink-0 ${done ? "text-normal-ink" : "text-ink-faint"}`} aria-hidden />{g}</li>)}
        </ul>
      </div>
      <div className="mt-auto rounded-panel bg-navy-tint p-3">
        <h4 className="text-caption font-semibold text-navy">{t.weNeed}</h4>
        <ul className="mt-1 flex flex-col gap-0.5 text-label text-navy-ink">{s.need.map((g) => <li key={g}>{g}</li>)}</ul>
      </div>
    </li>
  );
}

export default function Roadmap() {
  const [inputs, setInputs] = useState<ValueInputs>(PLACEHOLDERS);
  const out = useMemo(() => computeValue(inputs), [inputs]);

  return (
    <Page eyebrow={nav.groups.roadmap} title={t.title} question={t.question} gap="gap-10">
      <section aria-labelledby="journey">
        <SectionHeader id="journey" title={summary.journeyTitle} />
        <Stepper steps={summary.journey} />
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_3fr]">
        <section aria-labelledby="demonstrated">
          <h2 id="demonstrated" className="mb-3 flex min-h-9 items-center gap-2 text-label font-semibold text-normal-ink"><CheckCircle2 size={15} aria-hidden />{t.demonstrated}</h2>
          <ol className="grid"><StageCard s={t.stages[0]} i={0} /></ol>
        </section>
        <section aria-labelledby="requires">
          <h2 id="requires" className="mb-3 flex min-h-9 items-center gap-2 text-label font-semibold text-ink-muted"><Lock size={14} aria-hidden />{t.requires}</h2>
          <ol className="grid gap-4 md:grid-cols-3" start={2}>{t.stages.slice(1).map((s, i) => <StageCard key={s.tag} s={s} i={i + 1} />)}</ol>
        </section>
      </div>

      {/* Illustrative: a dashed frame and the label keep this from reading as a validated business case. */}
      <section className="card border-dashed !border-line-strong" aria-labelledby="value">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="eyebrow mb-1">{v.short}</p>
            <h2 id="value" className="t-section">{v.title}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge tone="caveat" className="!whitespace-normal">{v.label}</Badge>
              <span className="t-caption">{v.placeholder}</span>
            </div>
          </div>
          <button className="btn-outline btn-sm no-print" onClick={() => setInputs(PLACEHOLDERS)}><RotateCcw size={14} aria-hidden /> {v.reset}</button>
        </div>
        <div className="grid gap-8 lg:grid-cols-5">
          <div className="grid gap-6 sm:grid-cols-2 lg:col-span-3">
            {GROUPS.map((g) => (
              <fieldset key={g.title} className="flex flex-col gap-3">
                <legend className="mb-2 text-label font-semibold text-navy">{g.title}</legend>
                {g.keys.map((k) => (
                  <label key={k} className="flex flex-col gap-1 text-label">
                    <span className="font-medium text-ink">{v.inputs[k].label} <span className="text-ink-muted">({v.inputs[k].unit})</span></span>
                    <input type="number" min={0} max={v.inputs[k].unit === "%" ? 100 : undefined} inputMode="decimal"
                      className={`rounded-panel border border-line-strong px-3 py-2 num transition-colors duration-fast hover:border-navy focus:border-navy ${inputs[k] === PLACEHOLDERS[k] ? "text-ink-muted" : "font-semibold text-navy-ink"}`}
                      value={inputs[k]} onChange={(e) => setInputs((s) => ({ ...s, [k]: clamp(k, Number(e.target.value) || 0) }))} />
                  </label>
                ))}
              </fieldset>
            ))}
          </div>
          <div className="flex flex-col gap-3 lg:col-span-2">
            <dl className="divide-y divide-line rounded-card border border-line">
              <Out label={v.out.hours} value={`${fmtInt(out.hoursRecovered)} h ${v.perYear}`} />
              <Out label={v.out.production} value={`${fmtRupees(out.productionProtected)} ${v.perYear}`} />
              <Out label={v.out.fuel} value={`${fmtRupees(out.fuelSaving)} ${v.perYear}`} />
            </dl>
            <div className="surface-dark border-dashed p-5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-label font-semibold text-mist">{v.out.total}</span>
                <span className="rounded-full border border-watch/60 px-2 py-0.5 text-caption font-semibold text-watch">{v.short}</span>
              </div>
              <div className="mt-1 text-kpi font-semibold text-white num" aria-live="polite" aria-atomic="true">{fmtRupees(out.total)} <span className="text-card font-medium text-mist">{v.perYear}</span></div>
            </div>
            <p className="text-label font-semibold text-watch-ink">{v.label}</p>
            <p className="text-label text-ink-muted">{t.investment}</p>
          </div>
        </div>
      </section>

      <HeroBand>
        <section id="ask" className="p-7 sm:p-9" aria-labelledby="ask-title">
          <h2 id="ask-title" className="text-title font-semibold">{ask.title}</h2>
          <ol className="mt-5 grid gap-3 md:grid-cols-2">
            {ask.items.map((a, i) => (
              <li key={a} className="surface-glass flex items-start gap-3 p-4 text-label text-white/90">
                <NumberDot n={i + 1} tone="sky" />
                <span>{a}</span>
              </li>
            ))}
          </ol>
          <button className="btn-primary no-print mt-6" onClick={() => window.print()}><Printer size={16} aria-hidden /> {ask.print}</button>
        </section>
      </HeroBand>
    </Page>
  );
}

function Out({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 px-4 py-3">
      <dt className="text-label text-ink-muted">{label}</dt>
      <dd className="text-section font-semibold text-navy-ink num">{value}</dd>
    </div>
  );
}
