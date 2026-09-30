import { XCircle } from "lucide-react";
import { Loading, PageHeader } from "../components/ui";
import { validation as t } from "../copy";
import { useData } from "../data";
import { fmtInt } from "../lib/format";

export default function Validation() {
  const d = useData("validation");
  if (!d) return <Loading />;
  const pts = (x: number) => (x * 100).toFixed(1);
  const checks = Object.values(d.checks).reduce((a, b) => a + b, 0);
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <PageHeader title={t.title} question={t.question} />

      <section className="card">
        <h2 className="mb-4 text-lg font-semibold">{t.methodTitle}</h2>
        <ol className="flex flex-col gap-3">
          {t.method.map((m, i) => (
            <li key={m.title} className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-navy-tint text-sm font-bold text-navy">{i + 1}</span>
              <p className="text-ink"><span className="font-semibold">{m.title}.</span> {m.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="card border-l-4 border-navy">
        <h2 className="text-lg font-semibold">{t.resultTitle}</h2>
        <p className="mt-3 flex items-start gap-2 text-xl font-semibold text-navy-ink"><XCircle size={24} className="mt-0.5 shrink-0 text-ink-muted" aria-hidden />{t.result}</p>
        <p className="mt-2 text-ink-muted">{t.resultDetail(pts(d.primary.pe), pts(d.primary.ciLow), pts(d.primary.ciHigh), d.primary.p.toFixed(2))} {t.chance(d.negativeControls.NC1.p.toFixed(2), d.negativeControls.NC2.p.toFixed(2))}</p>
        <div className="mt-5 grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="font-semibold">{t.whyTitle}</h3>
            <ul className="mt-2 list-disc pl-5 text-sm text-ink">
              {t.why.map((w, i) => <li key={i} className="mb-1">{w(d.censored, d.periods)}</li>)}
            </ul>
          </div>
          <div>
            <h3 className="font-semibold">{t.fixTitle}</h3>
            <p className="mt-2 text-sm text-ink">{t.fix(d.revalidateAt)}</p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">{t.trustTitle}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <Trust title={t.trust.leakage.title} body={t.trust.leakage.body} />
          <Trust title={t.trust.future.title} body={t.trust.future.body} />
          <Trust title={t.trust.repro.title} body={t.trust.repro.body} />
          <Trust title={t.trust.checks.title} body={t.trust.checks.body(fmtInt(checks))} />
        </div>
      </section>

      <footer className="border-t border-line pt-4 text-xs text-ink-muted">
        <h2 className="mb-1 font-semibold text-ink-muted">{t.techTitle}</h2>
        <ul>{t.tech(d.versions).map((l) => <li key={l}>{l}</li>)}</ul>
      </footer>
    </div>
  );
}

const Trust = ({ title, body }: { title: string; body: string }) => (
  <div className="card !p-5">
    <h3 className="font-semibold">{title}</h3>
    <p className="mt-1 text-sm text-ink-muted">{body}</p>
  </div>
);
