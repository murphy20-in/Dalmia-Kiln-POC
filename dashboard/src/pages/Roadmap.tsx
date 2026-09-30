import { useMemo, useState } from "react";
import { CheckCircle2, Printer, RotateCcw } from "lucide-react";
import { PageHeader } from "../components/ui";
import { ask, roadmap as t, value as v } from "../copy";
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

export default function Roadmap() {
  const [inputs, setInputs] = useState<ValueInputs>(PLACEHOLDERS);
  const out = useMemo(() => computeValue(inputs), [inputs]);

  return (
    <div className="flex flex-col gap-8">
      <PageHeader title={t.title} question={t.question} />

      <ol className="grid gap-4 lg:grid-cols-4">
        {t.stages.map((s, i) => (
          <li key={s.tag} className={`card flex flex-col gap-3 ${i === 0 ? "border-t-4 border-normal" : i === 1 ? "border-t-4 border-navy ring-2 ring-navy/20" : "border-t-4 border-line"}`}>
            <div className="flex items-center justify-between">
              <span className="eyebrow">{s.tag}</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${i === 0 ? "bg-normal-ink text-white" : i === 1 ? "bg-navy text-white" : "bg-page text-ink-muted"}`}>
                {i === 0 && <CheckCircle2 size={12} className="mr-1 inline" aria-hidden />}{s.when}
              </span>
            </div>
            <h2 className="text-xl font-bold">{s.title}</h2>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{t.youGet}</h3>
              <ul className="mt-1 list-disc pl-4 text-sm text-ink">{s.get.map((g) => <li key={g}>{g}</li>)}</ul>
            </div>
            <div className="mt-auto rounded-lg bg-navy-tint p-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-navy">{t.weNeed}</h3>
              <ul className="mt-1 list-disc pl-4 text-sm text-navy-ink">{s.need.map((g) => <li key={g}>{g}</li>)}</ul>
            </div>
          </li>
        ))}
      </ol>

      <section className="card" aria-labelledby="value">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 id="value" className="text-xl font-bold">{v.title}</h2>
            <p className="mt-1 inline-block rounded-md bg-watch/15 px-2 py-1 text-sm font-semibold text-watch-ink">{v.label}</p>
            <p className="mt-2 text-xs text-ink-muted">{v.placeholder}</p>
          </div>
          <button className="btn-outline no-print" onClick={() => setInputs(PLACEHOLDERS)}><RotateCcw size={14} aria-hidden /> {v.reset}</button>
        </div>
        <div className="grid gap-8 lg:grid-cols-5">
          <div className="grid gap-6 sm:grid-cols-2 lg:col-span-3">
            {GROUPS.map((g) => (
              <fieldset key={g.title} className="flex flex-col gap-3">
                <legend className="mb-2 text-sm font-semibold text-navy">{g.title}</legend>
                {g.keys.map((k) => (
                  <label key={k} className="flex flex-col gap-1 text-sm">
                    <span className="font-medium text-ink">{v.inputs[k].label} <span className="text-ink-muted">({v.inputs[k].unit})</span></span>
                    <input type="number" min={0} max={v.inputs[k].unit === "%" ? 100 : undefined} inputMode="decimal"
                      className={`rounded-lg border border-line px-3 py-2 num focus:border-navy ${inputs[k] === PLACEHOLDERS[k] ? "text-ink-muted" : "font-semibold text-navy-ink"}`}
                      value={inputs[k]} onChange={(e) => setInputs((s) => ({ ...s, [k]: clamp(k, Number(e.target.value) || 0) }))} />
                  </label>
                ))}
              </fieldset>
            ))}
          </div>
          <div className="flex flex-col gap-3 lg:col-span-2" aria-live="polite">
            <Out label={v.out.hours} value={`${fmtInt(out.hoursRecovered)} h ${v.perYear}`} />
            <Out label={v.out.production} value={`${fmtRupees(out.productionProtected)} ${v.perYear}`} />
            <Out label={v.out.fuel} value={`${fmtRupees(out.fuelSaving)} ${v.perYear}`} />
            <div className="rounded-card bg-navy p-5 text-white">
              <div className="text-sm font-semibold text-white/80">{v.out.total}</div>
              <div className="text-3xl font-bold num">{fmtRupees(out.total)} <span className="text-base font-medium">{v.perYear}</span></div>
            </div>
            <p className="text-sm font-semibold text-watch-ink">{v.label}</p>
            <p className="text-sm text-ink-muted">{t.investment}</p>
          </div>
        </div>
      </section>

      <section id="ask" className="rounded-card bg-gradient-to-br from-navy to-navy-ink p-8 text-white shadow-card">
        <h2 className="text-2xl font-bold text-white">{ask.title}</h2>
        <ol className="mt-4 grid gap-3 md:grid-cols-2">
          {ask.items.map((a, i) => (
            <li key={a} className="flex items-start gap-3 rounded-lg bg-white/10 p-4">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-cyan font-bold text-navy-ink">{i + 1}</span>
              <span>{a}</span>
            </li>
          ))}
        </ol>
        <button className="btn-primary no-print mt-6" onClick={() => window.print()}><Printer size={16} aria-hidden /> {ask.print}</button>
      </section>
    </div>
  );
}

function Out({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-line p-4">
      <div className="text-sm text-ink-muted">{label}</div>
      <div className="text-2xl font-bold text-navy-ink num">{value}</div>
    </div>
  );
}
