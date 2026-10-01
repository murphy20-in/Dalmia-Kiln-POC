import { useMemo, useState } from "react";
import { Check, ChevronDown, Copy, Fingerprint, GitBranch, ShieldCheck, Users } from "lucide-react";
import Chart from "../charts/Chart";
import { heatmap } from "../charts/heatmap";
import ChartCard from "../components/ChartCard";
import { Badge, Callout, Lead, Loading, Page, SectionHeader } from "../components/ui";
import { dataPage as t, labels, nav } from "../copy";
import { useData } from "../data";
import { fmtMonth } from "../lib/format";
import { brand, issueColor } from "../theme";

const SEV = ["critical", "high", "medium", "low", "info"] as const;
const rigourIcon = [ShieldCheck, Fingerprint, Users, GitBranch];

/** Severity word with a magnitude swatch (navy ramp, not alarm colours). */
const SevChip = ({ s }: { s: string }) => (
  <Badge tone="outline"><span className="h-2 w-2 rounded-sm" style={{ background: issueColor[s] }} aria-hidden />{t.sev[s]}</Badge>
);

export default function DataReadiness() {
  const d = useData("data");
  const [copied, setCopied] = useState<number | null>(null);
  const months = useMemo(() => d?.months.map(fmtMonth) ?? [], [d]);
  // Memoised so a "Copied" click does not hand the chart a new option and redraw the heatmap.
  const coverage = useMemo(() => d && heatmap({
    x: months, y: d.coverage.map((c) => c.dataset), max: 100, ramp: [brand.navyInk, brand.heatLow], darkLow: true, leftWidth: 112,
    cells: d.coverage.flatMap((c, row) => c.pct.map((v, col) => [col, row, v] as [number, number, number])),
    format: (v) => (v === 0 ? "✕ 0%" : v >= 99.95 ? "100%" : `${v.toFixed(v >= 99 ? 1 : 0)}%`), valueLabel: t.coverageLabel,
  }), [d, months]);
  if (!d || !coverage) return <Loading />;
  const total = SEV.reduce((a, s) => a + d.issues[s], 0);
  const maxIssues = Math.max(...SEV.map((s) => d.issues[s]));

  const copy = async (i: number, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(i); window.setTimeout(() => setCopied(null), 2000); } catch { /* clipboard blocked: button simply does not confirm */ }
  };

  return (
    <Page eyebrow={nav.groups.evidence} title={t.title} question={t.question}>
      <Lead sub={t.issuesSub}>{t.issuesTitle(total)}</Lead>

      <div className="grid gap-6 lg:grid-cols-12">
        <ChartCard className="lg:col-span-7" title={t.coverageTitle} sub={t.coverageSub} source={t.coverageSource}
          legend={[{ name: t.coverageFull, color: brand.heatLow }, { name: t.coverageNone, color: brand.navyInk }]}
          table={{ columns: [labels.dataset, ...months], rows: d.coverage.map((c) => [c.dataset, ...c.pct.map((v) => `${v}%`)]) }}>
          <Chart option={coverage} height={400} label={t.coverageTitle} />
        </ChartCard>
        <section className="card flex flex-col lg:col-span-5" aria-labelledby="sev">
          <SectionHeader id="sev" title={t.bySeverity} sub={t.bySeveritySub} />
          <ul className="flex flex-col gap-3">
            {SEV.map((s) => (
              <li key={s} className="grid grid-cols-[6rem_1fr_2rem] items-center gap-3 text-label">
                <SevChip s={s} />
                <span className="h-2.5 overflow-hidden rounded-full bg-page" aria-hidden>
                  <span className="block h-full rounded-full" style={{ width: `${(d.issues[s] / maxIssues) * 100}%`, background: issueColor[s] }} />
                </span>
                <span className="text-right font-semibold text-navy-ink num">{d.issues[s]}</span>
              </li>
            ))}
          </ul>
          <div className="mt-5"><Callout>{t.criticalNote}</Callout></div>
        </section>
      </div>

      <section aria-labelledby="examples">
        <SectionHeader id="examples" title={labels.examples} sub={t.examplesSub(d.examples.length, total)} />
        <div className="grid gap-3 md:grid-cols-2">
          {d.examples.map((e) => (
            <details key={e.src} className="group card !p-0 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-start gap-3 rounded-card px-5 py-4 transition-colors hover:bg-page">
                <SevChip s={e.severity.toLowerCase()} />
                <span className="flex-1 text-label font-semibold text-navy-ink">{e.title}</span>
                <ChevronDown size={16} className="mt-0.5 shrink-0 text-ink-muted transition-transform group-open:rotate-180" aria-hidden />
              </summary>
              <p className="border-t border-line px-5 py-4 text-label text-ink-body">{e.body}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="panel grid gap-5 md:grid-cols-4" aria-label={labels.rigour}>
        {t.rigour.map((r, i) => {
          const Icon = rigourIcon[i];
          return (
            <div key={r.title} className="flex gap-3">
              <Icon size={20} className="mt-0.5 shrink-0 text-navy" aria-hidden />
              <div><h3 className="text-label font-semibold text-navy-ink">{r.title}</h3><p className="mt-0.5 text-label text-ink-muted">{r.body}</p></div>
            </div>
          );
        })}
      </section>

      <section aria-labelledby="asks">
        <SectionHeader id="asks" title={t.asksTitle} />
        <div className="grid gap-4 md:grid-cols-2">
          {d.asks.map((a, i) => (
            <article key={a.title} className="card flex flex-col gap-2 !p-5">
              <Badge tone={a.priority === 1 ? "navy" : "tint"} className="self-start">{t.priority(a.priority)}</Badge>
              <h3 className="t-card">{a.title}</h3>
              <p className="text-label text-ink-body">{a.detail}</p>
              <p className="text-label text-ink-muted"><span className="font-semibold text-ink">{t.unlocks}:</span> {a.unlocks}</p>
              <button className="btn-outline btn-sm mt-auto self-start" onClick={() => copy(i, t.requestText(a.title, a.detail))}>
                {copied === i ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />} {copied === i ? t.copied : t.copy}
              </button>
              <span className="sr-only" role="status">{copied === i ? t.copied : ""}</span>
            </article>
          ))}
        </div>
      </section>
    </Page>
  );
}
