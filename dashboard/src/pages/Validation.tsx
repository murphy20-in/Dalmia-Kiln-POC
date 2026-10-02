import { XCircle } from "lucide-react";
import { ProcessLines } from "../components/Brand";
import { Loading, NumberDot, SectionHeader } from "../components/ui";
import { nav, validation as t } from "../copy";
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
    <>
      {/* The primary conclusion, first, large and unsoftened: the technical authority page opens on the negative result. */}
      <section className="atmosphere" aria-labelledby="verdict">
        <ProcessLines />
        <div className="mx-auto grid max-w-page gap-8 px-4 py-9 sm:px-8 lg:grid-cols-[1fr_1.15fr] lg:items-center lg:py-11">
          <div>
            <p className="eyebrow-dark">{nav.groups.evidence}</p>
            <h1 className="mt-1.5 text-title font-semibold">{t.title}</h1>
            <p className="mt-1 max-w-prose text-body text-mist">{t.question}</p>
          </div>
          <div className="surface-glass p-6 sm:p-7">
            <h2 id="verdict" className="eyebrow-dark">{t.verdictLabel}</h2>
            <p className="mt-3 flex items-center gap-3 text-display font-semibold uppercase tracking-wide text-white sm:text-hero">
              <XCircle size={36} className="shrink-0 text-mist" aria-hidden />{t.verdict}
            </p>
            <p className="mt-3 text-label text-mist">{t.verdictNote}</p>
          </div>
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-page flex-col gap-8 px-4 py-8 sm:px-8">
        <section className="card" aria-labelledby="result">
          <SectionHeader id="result" eyebrow={t.sections.result} title={t.resultTitle} />
          <p className="text-lead font-semibold text-ink">{t.result}</p>
          <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {stats.map(([k, v]) => (
              <div key={k} className="inset">
                <dt className="eyebrow">{k}</dt>
                <dd className="mt-1 text-section font-semibold text-ink num">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 max-w-4xl text-label text-ink-body">{t.resultDetail(pts(d.primary.pe), pts(d.primary.ciLow), pts(d.primary.ciHigh), d.primary.p.toFixed(2))} {t.chance(d.negativeControls.NC1.p.toFixed(2), d.negativeControls.NC2.p.toFixed(2))}</p>
        </section>

        <div className="grid gap-6 lg:grid-cols-2">
          <section className="card" aria-labelledby="why">
            <SectionHeader id="why" eyebrow={t.sections.interpretation} title={t.whyTitle} />
            <ul className="flex flex-col gap-2.5">
              {t.why.map((w, i) => (
                <li key={i} className="flex gap-2.5 text-label text-ink-body"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brunswick" aria-hidden />{w(d.censored, d.periods)}</li>
              ))}
            </ul>
          </section>
          <section className="panel" aria-labelledby="fix">
            <SectionHeader id="fix" eyebrow={t.sections.limitations} title={t.fixTitle} />
            <p className="text-label text-ink">{t.fix(d.revalidateAt)}</p>
          </section>
        </div>

        <section className="card" aria-labelledby="method">
          <SectionHeader id="method" eyebrow={t.sections.method} title={t.methodTitle} />
          <ol className="grid gap-5 md:grid-cols-5">
            {t.method.map((m, i) => (
              <li key={m.title} className="flex flex-col gap-2 border-t-2 border-ink pt-3">
                <div className="flex items-center gap-2"><NumberDot n={i + 1} tone="tint" /><h3 className="t-card">{m.title}</h3></div>
                <p className="text-label text-ink-muted">{m.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="trust">
          <SectionHeader id="trust" eyebrow={t.sections.evidence} title={t.trustTitle} />
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Trust title={t.trust.leakage.title} body={t.trust.leakage.body} />
            <Trust title={t.trust.future.title} body={t.trust.future.body} />
            <Trust title={t.trust.repro.title} body={t.trust.repro.body} />
            <Trust title={t.trust.checks.title} body={t.trust.checks.body(fmtInt(checks))} />
          </div>
        </section>

        <section className="border-t border-line pt-4 text-caption text-ink-muted" aria-labelledby="tech">
          <h2 id="tech" className="eyebrow mb-1">{t.techTitle}</h2>
          <ul>{t.tech(d.versions).map((l) => <li key={l}>{l}</li>)}</ul>
        </section>
      </div>
    </>
  );
}

const Trust = ({ title, body }: { title: string; body: string }) => (
  <div className="card !p-5">
    <h3 className="t-card">{title}</h3>
    <p className="mt-1 text-label text-ink-muted">{body}</p>
  </div>
);
