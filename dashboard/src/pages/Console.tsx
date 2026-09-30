import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowDownRight, ArrowRight, ArrowUpRight, ChevronLeft, ChevronRight, Info, Pause, Play, PowerOff } from "lucide-react";
import Chart from "../charts/Chart";
import { hbars } from "../charts/bars";
import { zoneLine } from "../charts/zoneLine";
import StatusGauge from "../components/StatusGauge";
import { Loading, PageHeader, Ribbon, StatusPill } from "../components/ui";
import { common, consoleCopy as t, effIndex, healthIndex, flagText, reasonText, severityName, systemName, zoneMeaning, zoneName } from "../copy";
import { useData, type ConsoleData, type ConsoleRow, type Period } from "../data";
import { fmt1, fmtDateTime, fmtDuration, fmtMonth, fromMs, toMs } from "../lib/format";
import { brand, systemColor } from "../theme";

const STEP = 10 * 60_000;
const HOUR = 60 * 60_000;

/** Built once per dataset: time → row lookups for smooth scrubbing and playback. */
function buildIndex(c: ConsoleData) {
  const times = c.rows.map((r) => toMs(r[0]));
  const byTime = new Map<number, number>(times.map((ms, i) => [ms, i]));
  const gaps = c.gaps.map(([a, b, kind]) => ({ from: toMs(a), to: toMs(b), kind }));
  /** Index of the first row at or after ms (binary search). */
  const nextIdx = (ms: number) => {
    let lo = 0, hi = times.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (times[mid] < ms) lo = mid + 1; else hi = mid; }
    return lo;
  };
  // runStart[i] = first row of the unbroken same-zone run that row i belongs to ("in this state for …").
  const runStart = new Int32Array(times.length);
  for (let i = 1; i < times.length; i++) {
    runStart[i] = c.rows[i][2] === c.rows[i - 1][2] && times[i] - times[i - 1] === 10 * 60_000 ? runStart[i - 1] : i;
  }
  return { times, byTime, gaps, nextIdx, runStart, start: times[0], end: times[times.length - 1] };
}
type Index = ReturnType<typeof buildIndex>;

const snap = (ms: number, ix: Index) => Math.min(ix.end, Math.max(ix.start, Math.round(ms / STEP) * STEP));

export default function Console() {
  const data = useData("console");
  const periods = useData("periods");
  const ix = useMemo(() => (data ? buildIndex(data) : null), [data]);
  if (!data || !periods || !ix) return <Loading />;
  return <ConsoleView data={data} periods={periods.periods} ix={ix} />;
}

function ConsoleView({ data, periods, ix }: { data: ConsoleData; periods: Period[]; ix: Index }) {
  const [params, setParams] = useSearchParams();
  const worst = useMemo(() => periods.reduce((a, b) => (b.severityScore > a.severityScore ? b : a), periods[0]), [periods]);
  const initial = params.get("t");
  const [ms, setMs] = useState(() => snap(initial && !Number.isNaN(toMs(initial)) ? toMs(initial) : toMs(worst.onset), ix));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 4>(1);

  // A ?t= pasted or edited while on the page drives the replay (runs only when the URL value changes).
  const tParam = params.get("t");
  useEffect(() => {
    if (tParam && !Number.isNaN(toMs(tParam))) { setPlaying(false); setMs(snap(toMs(tParam), ix)); }
  }, [tParam, ix]);

  // Keep ?t= in the URL (only while paused, so playback does not flood history / router renders).
  // Runs on ms / playing changes only (params via ref), so a URL edit is never overwritten by the stale time.
  const paramsRef = useRef(params);
  paramsRef.current = params;
  useEffect(() => {
    if (playing || paramsRef.current.get("t") === fromMs(ms)) return;
    const next = new URLSearchParams(paramsRef.current);
    next.set("t", fromMs(ms));
    setParams(next, { replace: true });
  }, [ms, playing, setParams]);

  // Playback: one 10-minute step every 300 ms (1×) or 75 ms (4×), skipping over stopped / no-data spans.
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setMs((cur) => {
        const i = ix.nextIdx(cur + 1);
        return i >= ix.times.length ? cur : ix.times[i];
      });
    }, speed === 1 ? 300 : 75);
    return () => window.clearInterval(id);
  }, [playing, speed, ix]);
  useEffect(() => { if (playing && ms >= ix.end) setPlaying(false); }, [playing, ms, ix.end]);

  const go = useCallback((next: number) => { setPlaying(false); setMs(snap(next, ix)); }, [ix]);

  const i = ix.byTime.get(ms);
  const row: ConsoleRow | null = i == null ? null : data.rows[i];

  const inState = i == null ? null : ix.times[i] - ix.times[ix.runStart[i]] + STEP;

  const trend = useMemo(() => {
    if (!row) return null;
    const k = ix.byTime.get(ms - 3 * HOUR);
    if (k == null) return "none" as const;
    const d = row[1] - data.rows[k][1];
    return d > 3 ? "up" as const : d < -3 ? "down" as const : "flat" as const;
  }, [row, ms, ix, data.rows]);

  // Last-24-h window on the 10-min grid; missing buckets stay null so gaps are drawn as gaps.
  const window24 = useMemo(() => {
    const s: [number, number | null][] = [];
    const k: [number, number | null][] = [];
    for (let m = ms - 24 * HOUR; m <= ms; m += STEP) {
      const r = ix.byTime.get(m);
      s.push([m, r == null ? null : data.rows[r][1]]);
      k.push([m, r == null ? null : data.rows[r][3]]);
    }
    return { s, k };
  }, [ms, ix, data.rows]);

  const shaded = useMemo(() => periods
    .filter((p) => toMs(p.end) >= ms - 24 * HOUR && toMs(p.start) <= ms)
    .map((p) => ({ from: Math.max(toMs(p.start), ms - 24 * HOUR), to: Math.min(toMs(p.end), ms), label: `${severityName[p.severity]} · #${p.n}` })), [periods, ms]);

  const trendOption = useMemo(() => zoneLine({
    series: [{ name: healthIndex.name, data: window24.s, color: brand.navyInk, width: 2.5 }],
    edges: data.bandEdges, periods: shaded, now: ms,
  }), [window24, data.bandEdges, shaded, ms]);

  const sparkOption = useMemo(() => zoneLine({
    series: [{ name: effIndex.short, data: window24.k, color: "#2f62d6" }], compact: true,
  }), [window24]);

  const driverOption = useMemo(() => row ? hbars({
    items: data.families.map((f, n) => ({ name: systemName[f], value: row[4][n], color: systemColor[f] })),
    max: Math.max(40, ...row[4]),
  }) : null, [row, data.families]);

  const stamp = fmtDateTime(fromMs(ms));
  const high = periods.filter((p) => p.severity === "HIGH");

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t.title} question={t.intro} />
      <Ribbon>{t.ribbon(stamp)}</Ribbon>
      {/* One polite announcement, only when not playing, so screen readers are not flooded during playback. */}
      <p className="sr-only" role="status">{playing ? "" : `${stamp}: ${row ? `${zoneName[row[2]]}, ${healthIndex.name} ${row[1].toFixed(1)}` : t.gapTitle}`}</p>

      {/* Replay controls */}
      <section aria-label={t.replay.time} className="card z-10 flex flex-col gap-4 !py-4 lg:sticky lg:top-[4.5rem]">
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn-navy w-28 justify-center" onClick={() => setPlaying((p) => !p)}>
            {playing ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />} {playing ? t.replay.pause : t.replay.play}
          </button>
          <div role="group" aria-label={t.replay.speed} className="flex overflow-hidden rounded-lg border border-line">
            {([1, 4] as const).map((sp) => (
              <button key={sp} className={`px-3 py-2 text-sm font-semibold ${speed === sp ? "bg-navy text-white" : "bg-white text-navy"}`}
                aria-pressed={speed === sp} onClick={() => setSpeed(sp)}>{sp}×</button>
            ))}
          </div>
          <button className="btn-outline px-2" onClick={() => go(ms - STEP)} aria-label={t.replay.stepBack}><ChevronLeft size={16} /></button>
          <label className="flex items-center gap-2 text-sm font-medium">
            <span className="sr-only">{t.replay.time}</span>
            <input type="datetime-local" className="rounded-lg border border-line px-3 py-2 text-sm num" value={fromMs(ms)} step={600}
              min={fromMs(ix.start)} max={fromMs(ix.end)}
              onChange={(e) => e.target.value && go(toMs(e.target.value.slice(0, 16)))} />
          </label>
          <button className="btn-outline px-2" onClick={() => go(ms + STEP)} aria-label={t.replay.stepFwd}><ChevronRight size={16} /></button>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-ink-muted">{t.replay.jump}</span>
            {high.map((p) => (
              <button key={p.id} className="chip hover:border-navy hover:text-navy" onClick={() => go(toMs(p.onset))}>
                #{p.n} · {fmtDateTime(p.onset)}
              </button>
            ))}
          </div>
        </div>
        <Scrubber ms={ms} ix={ix} onChange={go} />
      </section>

      {/* Row 1: gauge, status, efficiency */}
      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card" aria-label={t.gaugeLabel}>
          <h2 className="text-sm font-semibold text-ink-muted">{t.gaugeLabel}</h2>
          <StatusGauge value={row ? row[1] : null} zone={row ? row[2] : null} edges={data.bandEdges} />
        </section>
        <section className="card flex flex-col gap-4">
          <h2 className="text-sm font-semibold text-ink-muted">{t.statusTitle}</h2>
          {row ? (
            <>
              <StatusPill zone={row[2]} size="lg" />
              <p className="text-ink">{zoneMeaning[row[2]]}</p>
              <p className="text-sm text-ink-muted">{inState != null && t.inState(fmtDuration(inState / 60_000))}</p>
              <p className="flex items-center gap-2 text-sm font-medium text-ink">
                {trend === "up" && <ArrowUpRight size={18} className="text-warning-ink" aria-hidden />}
                {trend === "down" && <ArrowDownRight size={18} className="text-normal-ink" aria-hidden />}
                {trend === "flat" && <ArrowRight size={18} className="text-ink-muted" aria-hidden />}
                {trend && t.trend[trend]}
              </p>
              {row[6].map((f) => (
                <p key={f} className="flex items-start gap-2 rounded-lg bg-navy-tint p-3 text-sm text-navy-ink"><Info size={16} className="mt-0.5 shrink-0" aria-hidden />{flagText[f]}</p>
              ))}
            </>
          ) : (
            <GapNotice />
          )}
        </section>
        <section className="card flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-ink-muted">{t.effTitle}</h2>
          <div className="text-5xl font-bold text-navy-ink num">{row ? fmt1(row[3]) : "–"}</div>
          <p className="text-xs text-ink-muted">{effIndex.scale}</p>
          <div className="mt-6">
            <p className="mb-1 text-xs font-semibold text-ink-muted">{t.effSpark}</p>
            <Chart option={sparkOption} animate={!playing} height={120} label={`${effIndex.name}, ${t.effSpark}`} />
          </div>
        </section>
      </div>

      {/* Row 2: drivers and reasons */}
      <div className="grid gap-6 lg:grid-cols-5">
        <section className="card lg:col-span-3">
          <h2 className="text-lg font-semibold">{t.driversTitle}</h2>
          <p className="mb-3 text-sm text-ink-muted">{t.driversSub}</p>
          {row && driverOption ? (row[1] > 0.5
            ? <Chart option={driverOption} animate={!playing} height={220} label={data.families.map((f, n) => `${systemName[f]} ${row[4][n]}`).join(", ")} />
            : <p className="text-sm text-ink-muted">{t.driversNone}</p>)
            : <GapNotice compact />}
        </section>
        <section className="card lg:col-span-2">
          <h2 className="mb-3 text-lg font-semibold">{t.reasonsTitle}</h2>
          {row ? (row[5].length ? (
            <ol className="flex flex-col gap-3">
              {row[5].map((r, n) => (
                <li key={r} className="flex gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-navy text-sm font-bold text-white">{n + 1}</span>
                  <span className="text-ink">{reasonText[r] ?? r}</span>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-ink-muted">{t.reasonsNone}</p>) : <GapNotice compact />}
        </section>
      </div>

      {/* Row 3: 24-h trend */}
      <section className="card">
        <h2 className="text-lg font-semibold">{t.trendTitle}</h2>
        <p className="mb-2 text-sm text-ink-muted">{t.trendSub}</p>
        {window24.s.every(([, v]) => v == null) ? <GapNotice /> : <Chart option={trendOption} animate={!playing} height={260} label={`${t.trendTitle}: ${t.gaugeLabel} ${row ? `now ${row[1].toFixed(1)}, ${zoneName[row[2]]}` : t.gapTitle}`} />}
      </section>

      {/* Row 4: decision support (illustrative, never tied to the replayed moment) */}
      <section aria-labelledby="decisions">
        <div className="mb-3 flex flex-wrap items-baseline gap-3">
          <h2 id="decisions" className="text-lg font-semibold">{t.decisionsTitle}</h2>
          <span className="chip border-dashed">{common.illustrative}</span>
        </div>
        <p className="mb-3 text-sm text-ink-muted">{t.decisionsSub}</p>
        <div className="grid gap-4 md:grid-cols-3">
          {t.decisions.map((d) => (
            <article key={d.title} className="card border border-dashed border-line !shadow-none">
              <h3 className="font-semibold">{d.title}</h3>
              <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">{d.when}</p>
              <p className="mt-2 text-sm text-ink">{d.action}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function GapNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-start gap-3 rounded-lg bg-page p-4 text-ink-muted">
      <PowerOff size={20} className="mt-0.5 shrink-0" aria-hidden />
      <div>
        <p className="font-semibold text-ink">{t.gapTitle}</p>
        {!compact && <p className="mt-1 text-sm">{t.gapBody}</p>}
      </div>
    </div>
  );
}

/** Full-range strip: gaps in grey, a range input over time, and the current position. */
function Scrubber({ ms, ix, onChange }: { ms: number; ix: Index; onChange: (ms: number) => void }) {
  const span = ix.end - ix.start;
  const pct = (m: number) => ((m - ix.start) / span) * 100;
  return (
    <div className="relative h-8 rounded focus-within:ring-2 focus-within:ring-navy focus-within:ring-offset-2">
      <div className="absolute inset-x-0 top-3 h-2 rounded-full bg-navy-tint" aria-hidden>
        {ix.gaps.map((g) => (
          <div key={g.from} className="absolute top-0 h-2 bg-ink-faint/60" style={{ left: `${pct(g.from)}%`, width: `${Math.max(0.2, pct(g.to) - pct(g.from))}%` }} />
        ))}
        <div className="absolute -top-1 h-4 w-1 rounded bg-navy-ink" style={{ left: `calc(${pct(ms)}% - 2px)` }} />
      </div>
      <input type="range" aria-label={t.replay.scrub} className="absolute inset-0 h-8 w-full cursor-pointer opacity-0"
        min={ix.start} max={ix.end} step={STEP} value={ms} aria-valuetext={fmtDateTime(fromMs(ms))}
        onChange={(e) => onChange(Number(e.target.value))} />
      <div className="pointer-events-none absolute inset-x-0 top-6 flex justify-between text-[11px] text-ink-muted" aria-hidden>
        {monthStarts(ix.start, ix.end).map((m) => <span key={m} style={{ position: "absolute", left: `${pct(m)}%` }}>{fmtMonth(fromMs(m).slice(0, 7))}</span>)}
      </div>
    </div>
  );
}

/** First instant of every month between start and end (for scrubber labels). */
function monthStarts(start: number, end: number) {
  const out: number[] = [];
  const d = new Date(start);
  for (let m = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1); m <= end; m = Date.UTC(new Date(m).getUTCFullYear(), new Date(m).getUTCMonth() + 1, 1)) {
    if (m >= start) out.push(m);
  }
  return out;
}
