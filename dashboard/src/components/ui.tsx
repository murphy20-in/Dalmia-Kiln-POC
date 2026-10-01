import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Check, CheckCircle2, Eye, FileSearch, Info, Lock, ShieldOff } from "lucide-react";
import { common, evidence, summary, zoneName } from "../copy";
import { status } from "../theme";

/** Restrained skeleton in the shape of a page header and two cards. */
export const Loading = () => (
  <div role="status" className="flex flex-col gap-6">
    <span className="sr-only">{common.loading}</span>
    <div className="h-8 w-72 animate-pulse rounded bg-line" aria-hidden />
    <div className="h-4 w-96 max-w-full animate-pulse rounded bg-line/70" aria-hidden />
    <div className="grid gap-6 lg:grid-cols-2" aria-hidden>
      <div className="h-64 animate-pulse rounded-card bg-white" />
      <div className="h-64 animate-pulse rounded-card bg-white" />
    </div>
  </div>
);

export const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** 300 ms count-up for hero numbers; instant under reduced motion. */
export function CountUp({ to, format = (n) => String(Math.round(n)) }: { to: number; format?: (n: number) => string }) {
  const [v, setV] = useState(reducedMotion() ? to : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reducedMotion()) { setV(to); return; }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - start) / 300);
      setV(a + (to - a) * (1 - (1 - k) ** 3));
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = to;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [to]);
  return <span className="num">{format(v)}</span>;
}

/** Page identity: title, the question the page answers, optional badges and actions. */
export function PageHeader({ title, question, badges, children }: { title: string; question: string; badges?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-title font-bold text-navy-ink">{title}</h1>
        <p className="mt-1 text-body text-ink-muted">{question}</p>
        {badges && <div className="mt-3 flex flex-wrap gap-2">{badges}</div>}
      </div>
      {children}
    </div>
  );
}

/** Level-1 takeaway on analytical pages: one sentence the page proves, with a cyan rule. */
export function Lead({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <section className="border-l-[3px] border-cyan pl-5">
      <p className="max-w-4xl text-lead font-semibold text-navy-ink">{children}</p>
      {sub && <p className="mt-1.5 max-w-prose text-label text-ink-muted">{sub}</p>}
    </section>
  );
}

/** Dark navy statement panel. Used once per page at most (Executive Summary hero, Roadmap ask). */
export function HeroBand({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`relative overflow-hidden rounded-card bg-navy-ink text-white ${className}`}>
      <div aria-hidden className="absolute inset-y-0 left-0 w-1 bg-cyan" />
      {children}
    </section>
  );
}

export function SectionHeader({ title, sub, id, aside }: { title: string; sub?: ReactNode; id?: string; aside?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 id={id} className="t-section">{title}</h2>
        {sub && <p className="mt-0.5 text-label text-ink-muted">{sub}</p>}
      </div>
      {aside}
    </div>
  );
}

/** Label → number (+ unit) → context → evidence line. */
export function KpiTile({ label, value, unit, sub, evidence: ev, className = "" }: {
  label: string; value: ReactNode; unit?: string; sub?: string; evidence?: string; className?: string;
}) {
  return (
    <div className={`card flex flex-col !p-5 ${className}`}>
      <div className="t-label">{label}</div>
      <div className="mt-2 flex items-baseline gap-1.5 text-kpi font-bold text-navy-ink num">
        {value}{unit && <span className="text-section font-semibold text-ink-muted">{unit}</span>}
      </div>
      {sub && <p className="mt-2 text-label text-ink-body">{sub}</p>}
      {ev && <p className="mt-auto flex items-center gap-1.5 border-t border-line pt-3 text-caption text-ink-muted [&:not(:first-child)]:mt-3"><FileSearch size={12} aria-hidden className="shrink-0" />{ev}</p>}
    </div>
  );
}

export function InsightCard({ title, body, children, to, link, accent }: {
  title: string; body?: ReactNode; children?: ReactNode; to?: string; link?: string; accent?: string;
}) {
  return (
    <article className="card flex flex-col gap-3" style={accent ? { boxShadow: `inset 0 3px 0 ${accent}` } : undefined}>
      <h3 className="t-card leading-snug">{title}</h3>
      {body && <p className="text-label text-ink-muted">{body}</p>}
      {children}
      {to && link && (
        <Link to={to} className="mt-auto inline-flex items-center gap-1 self-start text-label font-semibold text-navy hover:underline">
          {link} <ArrowRight size={14} aria-hidden />
        </Link>
      )}
    </article>
  );
}

const zoneIcon = { N: CheckCircle2, W: Eye, A: AlertTriangle, C: Lock };

export function StatusPill({ zone, size = "sm" }: { zone: "N" | "W" | "A" | "C"; size?: "sm" | "lg" }) {
  const Icon = zoneIcon[zone];
  const s = status[zone];
  const big = size === "lg";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${big ? "px-4 py-1.5 text-section" : "px-2.5 py-0.5 text-caption"}`}
      style={{ color: s.ink, background: s.band, boxShadow: `inset 0 0 0 1.5px ${s.fill}` }}>
      <Icon size={big ? 20 : 13} aria-hidden />
      {zoneName[zone]}
    </span>
  );
}

const badgeTone = {
  navy: "bg-navy text-white border-navy",
  tint: "bg-navy-tint text-navy-ink border-navy-line",
  outline: "bg-white text-ink-body border-line-strong",
  dashed: "bg-white text-ink-muted border-line-strong border-dashed",
  caveat: "bg-watch/10 text-watch-ink border-watch/40",
  positive: "bg-normal/10 text-normal-ink border-normal/40",
} as const;

/** Small word label. Colour is never the only signal: the text always carries the meaning. */
export function Badge({ tone = "outline", icon: Icon, children, className = "" }: {
  tone?: keyof typeof badgeTone; icon?: typeof Info; children: ReactNode; className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-caption font-semibold ${badgeTone[tone]} ${className}`}>
      {Icon && <Icon size={12} aria-hidden />}{children}
    </span>
  );
}

/** The two labels every abnormal-period surface carries. */
export const PeriodEvidence = ({ plural = false }: { plural?: boolean }) => (
  <>
    <Badge tone="tint" icon={FileSearch}>{plural ? evidence.kpiDerivedPlural : evidence.kpiDerived}</Badge>
    <Badge tone="dashed" icon={ShieldOff}>{plural ? evidence.notValidatedPlural : evidence.notValidated}</Badge>
  </>
);

export function Callout({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "caveat" }) {
  return (
    <p className={`flex items-start gap-2 rounded-panel px-3 py-2.5 text-label ${tone === "info" ? "bg-navy-tint text-navy-ink" : "bg-watch/10 text-watch-ink"}`}>
      <Info size={15} className="mt-0.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

export const NumberDot = ({ n, tone = "navy" }: { n: ReactNode; tone?: "navy" | "tint" }) => (
  <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-caption font-bold ${tone === "navy" ? "bg-navy text-white" : "bg-navy-tint text-navy"}`}>{n}</span>
);

export const Source = ({ children }: { children: ReactNode }) => (
  <p className="mt-4 flex items-center gap-1.5 border-t border-line pt-3 text-caption text-ink-muted"><FileSearch size={12} aria-hidden className="shrink-0" />{children}</p>
);

export function Ribbon({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="flex items-center gap-2 rounded-panel border border-navy-line bg-navy-tint px-3 py-2 text-label text-navy-ink">
      <Info size={15} className="shrink-0" aria-hidden />
      {children}
    </div>
  );
}

type StepState = "past" | "done" | "next" | "future";
/** The four-stage journey as one connected track: the top rule shows progress, not decoration. */
export function Stepper({ steps }: { steps: readonly { label: string; note: string; state: StepState }[] }) {
  return (
    <ol className="grid gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
      {steps.map((s, i) => {
        const done = s.state === "done";
        const next = s.state === "next";
        return (
          <li key={s.label} className="relative bg-white p-4" aria-current={next ? "step" : undefined}>
            <div aria-hidden className={`absolute inset-x-0 top-0 h-[3px] ${done ? "bg-normal" : next ? "bg-navy" : "bg-transparent"}`} />
            <div className="flex items-center gap-2">
              <span className={`flex h-6 w-6 items-center justify-center rounded-full text-caption font-bold ${done ? "bg-normal-ink text-white" : next ? "bg-navy text-white" : "bg-page text-ink-muted ring-1 ring-line-strong"}`}>
                {done ? <Check size={14} aria-hidden /> : i + 1}
              </span>
              <span className={`text-card font-semibold ${s.state === "past" || s.state === "future" ? "text-ink-muted" : "text-navy-ink"}`}>{s.label}</span>
              <span className="sr-only">{summary.stepState[s.state]}</span>
            </div>
            <p className={`mt-1.5 text-label ${done ? "font-semibold text-normal-ink" : next ? "font-medium text-navy" : "text-ink-muted"}`}>{s.note}</p>
          </li>
        );
      })}
    </ol>
  );
}

export function Legend({ items, className = "" }: { items: { name: string; color: string; dashed?: boolean }[]; className?: string }) {
  return (
    <ul className={`flex flex-wrap gap-x-4 gap-y-1 text-caption text-ink-body ${className}`}>
      {items.map((i) => (
        <li key={i.name} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={i.dashed ? { border: `1.5px dashed ${i.color}` } : { background: i.color }} aria-hidden />{i.name}
        </li>
      ))}
    </ul>
  );
}
