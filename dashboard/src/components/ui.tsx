import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Check, CheckCircle2, Eye, Lock } from "lucide-react";
import { common, zoneName } from "../copy";
import { status } from "../theme";

export const Loading = () => <p className="p-8 text-ink-muted">{common.loading}</p>;

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

export function PageHeader({ title, question, children }: { title: string; question: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-lg text-ink-muted">{question}</p>
      </div>
      {children}
    </div>
  );
}

export function HeroBand({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`relative overflow-hidden rounded-card bg-gradient-to-br from-navy to-navy-ink p-10 text-white shadow-card ${className}`}>
      <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full border-[36px] border-cyan/20" />
      <div aria-hidden className="absolute bottom-0 left-0 h-1 w-full bg-cyan" />
      <div className="relative">{children}</div>
    </section>
  );
}

export function KpiTile({ value, label, sub, className = "" }: { value: ReactNode; label: string; sub?: string; className?: string }) {
  return (
    <div className={`card flex flex-col gap-1 ${className}`}>
      <div className="text-3xl font-bold text-navy-ink num">{value}</div>
      <div className="text-sm font-semibold text-ink">{label}</div>
      {sub && <div className="text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

export function InsightCard({ title, body, children, to, link, accent }: {
  title: string; body?: ReactNode; children?: ReactNode; to?: string; link?: string; accent?: string;
}) {
  return (
    <article className="card flex flex-col gap-3" style={accent ? { borderTop: `4px solid ${accent}` } : undefined}>
      <h3 className="text-lg font-semibold leading-snug">{title}</h3>
      {body && <p className="text-sm text-ink-muted">{body}</p>}
      {children}
      {to && link && (
        <Link to={to} className="mt-auto inline-flex items-center gap-1 text-sm font-semibold text-navy hover:underline">
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
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${big ? "px-4 py-1.5 text-lg" : "px-2.5 py-0.5 text-xs"}`}
      style={{ color: s.ink, background: s.band, boxShadow: `inset 0 0 0 1.5px ${s.fill}` }}>
      <Icon size={big ? 20 : 13} aria-hidden />
      {zoneName[zone]}
    </span>
  );
}

export function CtaBand({ title, body, to, button }: { title: string; body: string; to: string; button: string }) {
  return (
    <section className="mt-10 flex flex-wrap items-center justify-between gap-6 rounded-card bg-navy-tint p-8">
      <div className="max-w-2xl">
        <h2 className="text-xl font-bold">{title}</h2>
        <p className="mt-1 text-ink-muted">{body}</p>
      </div>
      <Link to={to} className="btn-navy">{button} <ArrowRight size={16} aria-hidden /></Link>
    </section>
  );
}

export function Ribbon({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="flex items-center gap-2 rounded-lg border border-cyan/40 bg-cyan/10 px-4 py-2 text-sm text-navy-ink">
      <span className="h-2 w-2 shrink-0 rounded-full bg-cyan" aria-hidden />
      {children}
    </div>
  );
}

type StepState = "past" | "done" | "next" | "future";
export function Stepper({ steps }: { steps: readonly { label: string; note: string; state: StepState }[] }) {
  return (
    <ol className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {steps.map((s, i) => {
        const done = s.state === "done";
        return (
          <li key={s.label} className={`relative rounded-card border-2 p-4 ${done ? "border-normal bg-white shadow-card" : s.state === "next" ? "border-dashed border-navy/50 bg-white" : "border-line bg-white/60"}`}>
            <div className="flex items-center gap-2">
              <span className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-bold ${done ? "bg-normal-ink text-white" : s.state === "next" ? "bg-navy text-white" : "bg-line text-ink-muted"}`}>
                {done ? <Check size={16} aria-hidden /> : i + 1}
              </span>
              <span className={`font-semibold ${s.state === "past" || s.state === "future" ? "text-ink-muted" : "text-navy-ink"}`}>{s.label}</span>
            </div>
            <p className={`mt-2 text-sm ${done ? "font-semibold text-normal-ink" : "text-ink-muted"}`}>{s.note}</p>
          </li>
        );
      })}
    </ol>
  );
}

export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink">
      {items.map((i) => (
        <li key={i.name} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} aria-hidden />{i.name}</li>
      ))}
    </ul>
  );
}
