import { XCircle } from "lucide-react";
import { Loading, NumberDot, PageHeader, SectionHeader } from "../components/ui";
import { validation as t } from "../copy";
import { useData } from "../data";
import { fmtInt } from "../lib/format";

export default function Validation() {
  const d = useData("validation");
  if (!d) return <Loading />;
  const pts = (x: number) => (x * 100).toFixed(1);
  const checks = Object.values(d.checks).reduce((a, b) => a + b, 0);
  const stats: [string, string][] = [
    [t.stats.rise, `${pts(d.primary.pe)} ${t.stats.pts}`],
    [t.stats.range, `${pts(d.primary.ciLow)} to ${pts(d.primary.ciHigh)}`],
    [t.stats.p, d.primary.p.toFixed(2)],
  ];
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.question} />

      {/* The primary conclusion, first and unsoftened */}
      <section className="card grid overflow-hidden !p-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]" aria-labelledby="verdict">
        <div className="flex flex-col justify-center gap-2 border-b border-line bg-page p-6 lg:border-b-0 lg:border-r">
          <h2 id="verdict" className="t-label">{t.verdictLabel}</h2>
          <p className="flex items-center gap-2.5 text-title font-bold uppercase tracking-wide text-navy-ink">
            <XCircle size={28} className="shrink-0 text-ink-muted" aria-hidden />{t.verdict}
          </p>
          <p className="text-caption text-ink-muted">{t.verdictNote}</p>
        </div>
        <div className="p-6">
          <p className="text-card font-semibold text-navy-ink">{t.result}</p>
          <dl className="mt-4 grid grid-cols-3 gap-3">
            {stats.map(([k, v]) => (
              <div key={k} className="inset !p-3">
                <dt className="t-caption">{k}</dt>
                <dd className="mt-0.5 text-section font-semibold text-navy-ink num">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-label text-ink-body">{t.resultDetail(pts(d.primary.pe), pts(d.primary.ciLow), pts(d.primary.ciHigh), d.primary.p.toFixed(2))} {t.chance(d.negativeControls.NC1.p.toFixed(2), d.negativeControls.NC2.p.toFixed(2))}</p>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card" aria-labelledby="why">
          <SectionHeader id="why" title={t.whyTitle} />
          <ul className="flex flex-col gap-2.5">
            {t.why.map((w, i) => (
              <li key={i} className="flex gap-2.5 text-label text-ink-body"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-navy" aria-hidden />{w(d.censored, d.periods)}</li>
            ))}
          </ul>
        </section>
        <section className="panel" aria-labelledby="fix">
          <SectionHeader id="fix" title={t.fixTitle} />
          <p className="text-label text-navy-ink">{t.fix(d.revalidateAt)}</p>
        </section>
      </div>

      <section className="card" aria-labelledby="method">
        <SectionHeader id="method" title={t.methodTitle} />
        <ol className="grid gap-4 md:grid-cols-5">
          {t.method.map((m, i) => (
            <li key={m.title} className="flex flex-col gap-2">
              <div className="flex items-center gap-2"><NumberDot n={i + 1} tone="tint" /><h3 className="t-card">{m.title}</h3></div>
              <p className="text-label text-ink-muted">{m.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="trust">
        <SectionHeader id="trust" title={t.trustTitle} />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Trust title={t.trust.leakage.title} body={t.trust.leakage.body} />
          <Trust title={t.trust.future.title} body={t.trust.future.body} />
          <Trust title={t.trust.repro.title} body={t.trust.repro.body} />
          <Trust title={t.trust.checks.title} body={t.trust.checks.body(fmtInt(checks))} />
        </div>
      </section>

      <footer className="border-t border-line pt-4 text-caption text-ink-muted">
        <h2 className="mb-1 font-semibold text-ink-muted">{t.techTitle}</h2>
        <ul>{t.tech(d.versions).map((l) => <li key={l}>{l}</li>)}</ul>
      </footer>
    </div>
  );
}

const Trust = ({ title, body }: { title: string; body: string }) => (
  <div className="card !p-5">
    <h3 className="t-card">{title}</h3>
    <p className="mt-1 text-label text-ink-muted">{body}</p>
  </div>
);
