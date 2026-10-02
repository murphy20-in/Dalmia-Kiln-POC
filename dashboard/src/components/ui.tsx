import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Check, CheckCircle2, Eye, FileSearch, Info, Lock, ShieldOff } from "lucide-react";
import { common, evidence, summary, zoneName } from "../copy";
import { status } from "../theme";
import { ProcessLines } from "./Brand";

/** Restrained skeleton in the shape of a page band and two cards. */
export const Loading = () => (
  <div role="status" className="mx-auto flex max-w-page flex-col gap-6 px-4 py-8 sm:px-8">
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

/**
 * Page frame. Level 1 is the dark atmospheric band (eyebrow, title, the question the page answers);
 * everything below it sits on the cool canvas as white analytical surfaces or open layouts.
 */
type BandProps = { eyebrow?: string; title: string; question: string; badges?: ReactNode; actions?: ReactNode };

/** The dark band on its own, for pages (Console) that memoise it away from per-tick re-renders. */
export function PageBand({ eyebrow, title, question, badges, actions }: BandProps) {
  return (
    <div className="atmosphere">
      <ProcessLines />
      <span aria-hidden className="absolute inset-x-0 bottom-0 h-px bg-rule opacity-70" />
      <div className="mx-auto flex max-w-page flex-wrap items-end justify-between gap-x-6 gap-y-3 px-4 py-4 sm:px-8 sm:py-5">
        <div className="min-w-0">
          {eyebrow && <p className="eyebrow-dark">{eyebrow}</p>}
          <h1 className="mt-1.5 text-title font-semibold">{title}</h1>
          <p className="mt-1 max-w-prose text-body text-mist">{question}</p>
          {badges && <div className="mt-3 flex flex-wrap gap-2">{badges}</div>}
        </div>
        {actions}
      </div>
    </div>
  );
}

export function Page({ children, gap = "gap-6", ...band }: BandProps & { children: ReactNode; gap?: string }) {
  return (
    <>
      <PageBand {...band} />
      <div className={`mx-auto flex w-full max-w-page flex-col px-4 py-6 sm:px-8 ${gap}`}>{children}</div>
    </>
  );
}

/** Level-1 takeaway on analytical pages: one sentence the page proves, set against a blue rule. */
export function Lead({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <section className="relative pl-5">
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] rounded-full bg-accent" />
      <p className="max-w-4xl text-lead font-semibold text-ink">{children}</p>
      {sub && <p className="mt-1.5 max-w-prose text-label text-ink-muted">{sub}</p>}
    </section>
  );
}

/** Dark atmospheric statement panel. Used sparingly (Executive Summary closing ask, Roadmap ask). */
export function HeroBand({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`atmosphere rounded-card border border-moss/60 shadow-dark ${className}`}>
      <ProcessLines />
      {children}
    </section>
  );
}

export function SectionHeader({ title, sub, id, aside, eyebrow }: { title: string; sub?: ReactNode; id?: string; aside?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
        <h2 id={id} className="t-section">{title}</h2>
        {sub && <p className="mt-0.5 text-label text-ink-muted">{sub}</p>}
      </div>
      {aside}
    </div>
  );
}

/**
 * Two layouts. With `category`: category eyebrow → large number (+ unit, micro trend) → the metric's name in plain
 * words → one context line → evidence line. Without: label eyebrow → number → context → evidence (compact tiles).
 */
export function KpiTile({ category, label, value, unit, sub, evidence: ev, micro, className = "" }: {
  category?: string; label: string; value: ReactNode; unit?: string; sub?: string; evidence?: string; micro?: ReactNode; className?: string;
}) {
  const number = (
    <div className="mt-2 flex items-end justify-between gap-3">
      <div className="flex min-w-0 items-baseline gap-1.5 text-kpi font-semibold text-ink num">
        {value}{unit && <span className="text-section font-medium text-ink-muted">{unit}</span>}
      </div>
      {micro && <div aria-hidden className="shrink-0 pb-1.5">{micro}</div>}
    </div>
  );
  return (
    <div className={`card card-lift relative flex flex-col overflow-hidden !p-5 !pl-6 ${className}`}>
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-accent" />
      {category ? (
        <>
          <div className="eyebrow">{category}</div>
          {number}
          <p className="mt-2 text-card font-semibold text-ink">{label}</p>
          {sub && <p className="mt-1 text-label text-ink-muted">{sub}</p>}
        </>
      ) : (
        <>
          <div className="eyebrow min-h-[2rem]">{label}</div>
          {number}
          {sub && <p className="mt-2 text-label text-ink-body">{sub}</p>}
        </>
      )}
      {ev && <p className="mt-auto flex items-center gap-1.5 border-t border-line pt-3 text-caption text-ink-muted [&:not(:first-child)]:mt-3"><FileSearch size={12} aria-hidden className="shrink-0" />{ev}</p>}
    </div>
  );
}

/** Level-3 open layout: a top rule and the content, no box. Use three in a row for findings. */
export function InsightCard({ title, body, children, to, link }: {
  title: string; body?: ReactNode; children?: ReactNode; to?: string; link?: string;
}) {
  return (
    <article className="flex flex-col gap-3 border-t-2 border-ink pt-4">
      <h3 className="t-card leading-snug">{title}</h3>
      {body && <p className="text-label text-ink-muted">{body}</p>}
      {children}
      {to && link && (
        <Link to={to} className="mt-auto inline-flex items-center gap-1 self-start pt-1 text-label font-semibold text-brunswick hover:underline">
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
    <span className={`inline-flex items-center gap-1.5 rounded-full bg-white font-semibold ${big ? "px-4 py-1.5 text-section" : "px-2.5 py-0.5 text-caption"}`}
      style={{ color: s.ink, backgroundImage: `linear-gradient(${s.band}, ${s.band})`, boxShadow: `inset 0 0 0 1.5px ${s.fill}` }}>
      <Icon size={big ? 20 : 13} aria-hidden />
      {zoneName[zone]}
    </span>
  );
}

const badgeTone = {
  brand: "bg-brunswick text-white border-brunswick",
  tint: "bg-polar text-ink border-sage/50",
  outline: "bg-white text-ink-body border-line-strong",
  dashed: "bg-white text-ink-muted border-line-strong border-dashed",
  caveat: "bg-watch/10 text-watch-ink border-watch/40",
  positive: "bg-normal/10 text-normal-ink border-normal/40",
  glass: "bg-white/10 text-white border-sage/30",
  glassDashed: "bg-transparent text-mist border-sage/40 border-dashed",
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

/** The two labels every abnormal-period surface carries. `dark` for use on a dark green band. */
export const PeriodEvidence = ({ plural = false, dark = false }: { plural?: boolean; dark?: boolean }) => (
  <>
    <Badge tone={dark ? "glass" : "tint"} icon={FileSearch}>{plural ? evidence.kpiDerivedPlural : evidence.kpiDerived}</Badge>
    <Badge tone={dark ? "glassDashed" : "dashed"} icon={ShieldOff}>{plural ? evidence.notValidatedPlural : evidence.notValidated}</Badge>
  </>
);

export function Callout({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "caveat" }) {
  return (
    <p className={`flex items-start gap-2 rounded-panel px-3 py-2.5 text-label ${tone === "info" ? "bg-polar text-ink" : "bg-watch/10 text-watch-ink"}`}>
      <Info size={15} className="mt-0.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

export const NumberDot = ({ n, tone = "brand" }: { n: ReactNode; tone?: "brand" | "tint" | "emerald" }) => (
  <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-caption font-bold ${tone === "brand" ? "bg-brunswick text-white" : tone === "emerald" ? "bg-emerald text-forest" : "bg-polar text-brunswick"}`}>{n}</span>
);

export const Source = ({ children }: { children: ReactNode }) => (
  <p className="mt-4 flex items-center gap-1.5 border-t border-line pt-3 text-caption text-ink-muted"><FileSearch size={12} aria-hidden className="shrink-0" />{children}</p>
);

export function Ribbon({ children, dark = false }: { children: ReactNode; dark?: boolean }) {
  return (
    <div role="note" className={`flex items-center gap-2 rounded-panel border px-3 py-2 text-label ${dark ? "border-sage/25 bg-white/[0.05] text-mist" : "border-sage/50 bg-polar text-ink"}`}>
      <Info size={15} className="shrink-0" aria-hidden />
      {children}
    </div>
  );
}

type StepState = "past" | "done" | "next" | "future";
/** The four-stage journey as one spine: solid where demonstrated, dashed where it needs plant data. */
export function Stepper({ steps }: { steps: readonly { label: string; note: string; state: StepState }[] }) {
  return (
    <ol className="grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
      {steps.map((s, i) => {
        const done = s.state === "done";
        const next = s.state === "next";
        const demonstrated = steps[i + 1]?.state === "done" || (done && steps[i + 1]?.state === "past");
        return (
          <li key={s.label} className="relative pt-7" aria-current={next ? "step" : undefined}>
            {i < steps.length - 1 && (
              <span aria-hidden className={`absolute left-4 top-[11px] hidden lg:block ${demonstrated ? "-right-6 h-px bg-brunswick" : "-right-6 border-t border-dashed border-slate"}`} />
            )}
            <span aria-hidden className={`absolute left-0 top-1 flex h-[14px] w-[14px] items-center justify-center rounded-full ${
              done ? "bg-normal-ink text-white" : next ? "bg-brunswick shadow-glow ring-2 ring-emerald/60" : s.state === "past" ? "bg-ink" : "border border-dashed border-slate bg-page"}`}>
              {done && <Check size={9} strokeWidth={3.5} />}
            </span>
            <div className="flex items-center gap-2">
              <span className={`text-card font-semibold ${s.state === "future" ? "text-ink-muted" : "text-ink"}`}>{s.label}</span>
              <span className="sr-only">{summary.stepState[s.state]}</span>
            </div>
            <p className="eyebrow mt-1">{summary.stepTag[s.state]}</p>
            <p className={`mt-1.5 text-label ${done ? "font-semibold text-normal-ink" : next ? "font-medium text-brunswick" : "text-ink-muted"}`}>{s.note}</p>
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
