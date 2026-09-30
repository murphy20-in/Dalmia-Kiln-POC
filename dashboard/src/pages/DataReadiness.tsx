import { useState } from "react";
import { Check, Copy, Fingerprint, GitBranch, ShieldCheck, Users } from "lucide-react";
import Chart from "../charts/Chart";
import { heatmap } from "../charts/heatmap";
import ChartCard from "../components/ChartCard";
import { Loading, PageHeader } from "../components/ui";
import { dataPage as t, labels } from "../copy";
import { useData } from "../data";
import { fmtMonth } from "../lib/format";
import { brand } from "../theme";

const SEV = ["critical", "high", "medium", "low", "info"] as const;
const rigourIcon = [ShieldCheck, Fingerprint, Users, GitBranch];

export default function DataReadiness() {
  const d = useData("data");
  const [copied, setCopied] = useState<number | null>(null);
  if (!d) return <Loading />;
  const months = d.months.map(fmtMonth);
  const total = SEV.reduce((a, s) => a + d.issues[s], 0);
  const maxIssues = Math.max(...SEV.map((s) => d.issues[s]));
  const coverage = heatmap({
    x: months, y: d.coverage.map((c) => c.dataset), max: 100, ramp: ["#c4511a", "#f1f4fb"], darkLow: true, leftWidth: 120,
    cells: d.coverage.flatMap((c, row) => c.pct.map((v, col) => [col, row, v] as [number, number, number])),
    format: (v) => (v === 0 ? "✕ 0%" : v >= 99.95 ? "✓ 100%" : `${v.toFixed(v >= 99 ? 1 : 0)}%`),
  });

  const copy = async (i: number, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(i); window.setTimeout(() => setCopied(null), 2000); } catch { /* clipboard blocked: button simply does not confirm */ }
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.question} />

      <div className="grid gap-6 lg:grid-cols-5">
        <ChartCard className="lg:col-span-3" title={t.coverageTitle} sub={t.coverageSub}
          table={{ columns: [labels.dataset, ...months], rows: d.coverage.map((c) => [c.dataset, ...c.pct.map((v) => `${v}%`)]) }}>
          <Chart option={coverage} height={420} label={t.coverageTitle} />
        </ChartCard>
        <ChartCard className="lg:col-span-2" title={t.issuesTitle(total)} sub={t.issuesSub}>
          <ul className="flex flex-col gap-2">
            {SEV.map((s) => (
              <li key={s} className="grid grid-cols-[5rem_1fr_2rem] items-center gap-3 text-sm">
                <span className="font-medium">{t.sev[s]}</span>
                <span className="h-4 rounded" style={{ width: `${(d.issues[s] / maxIssues) * 100}%`, background: s === "critical" ? brand.navyInk : s === "high" ? brand.navy : "#8fa1d8" }} aria-hidden />
                <span className="text-right font-semibold num">{d.issues[s]}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 rounded-lg bg-navy-tint p-3 text-sm text-navy-ink">{t.criticalNote}</p>
        </ChartCard>
      </div>

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-5" aria-label={labels.examples}>
        {d.examples.map((e) => (
          <article key={e.src} className="card !p-5">
            <span className="eyebrow">{t.sev[e.severity.toLowerCase()]}</span>
            <h3 className="mt-1 font-semibold leading-snug">{e.title}</h3>
            <p className="mt-2 text-sm text-ink-muted">{e.body}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-4 rounded-card bg-navy-tint p-6 md:grid-cols-4" aria-label={labels.rigour}>
        {t.rigour.map((r, i) => {
          const Icon = rigourIcon[i];
          return (
            <div key={r.title} className="flex gap-3">
              <Icon size={24} className="shrink-0 text-navy" aria-hidden />
              <div><h3 className="font-semibold">{r.title}</h3><p className="text-sm text-ink-muted">{r.body}</p></div>
            </div>
          );
        })}
      </section>

      <section aria-labelledby="asks">
        <h2 id="asks" className="mb-3 text-lg font-semibold">{t.asksTitle}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {d.asks.map((a, i) => (
            <article key={a.title} className="card flex flex-col gap-2">
              <span className={`self-start rounded-full px-2.5 py-0.5 text-xs font-semibold ${a.priority === 1 ? "bg-navy text-white" : "bg-navy-tint text-navy"}`}>{t.priority(a.priority)}</span>
              <h3 className="font-semibold">{a.title}</h3>
              <p className="text-sm text-ink">{a.detail}</p>
              <p className="text-sm text-ink-muted"><span className="font-semibold">{t.unlocks}:</span> {a.unlocks}</p>
              <button className="btn-outline mt-auto self-start px-3 py-1.5 text-xs" onClick={() => copy(i, t.requestText(a.title, a.detail))}>
                {copied === i ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />} {copied === i ? t.copied : t.copy}
              </button>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
