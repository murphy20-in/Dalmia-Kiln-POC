import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowDownRight, ArrowRight, ArrowUpRight, ChevronLeft, ChevronRight, Info, Pause, Play, PowerOff } from "lucide-react";
import Chart from "../charts/Chart";
import { hbars } from "../charts/bars";
import { zoneLine } from "../charts/zoneLine";
import StatusGauge from "../components/StatusGauge";
import { Badge, Loading, NumberDot, PageHeader, Ribbon, SectionHeader, StatusPill } from "../components/ui";
import { common, consoleCopy as t, effIndex, evidence, healthIndex, flagText, periods as pc, reasonText, systemName, zoneMeaning, zoneName } from "../copy";
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
    .map((p) => ({ from: Math.max(toMs(p.start), ms - 24 * HOUR), to: Math.min(toMs(p.end), ms), label: pc.label(p.n) })), [periods, ms]);

  const trendOption = useMemo(() => zoneLine({
    series: [{ name: healthIndex.name, data: window24.s, color: brand.navyInk, width: 2.5 }],
    edges: data.bandEdges, periods: shaded, now: ms, note: shaded.length ? `${evidence.kpiDerived} shaded · ${evidence.notValidated}` : undefined,
  }), [window24, data.bandEdges, shaded, ms]);

  const sparkOption = useMemo(() => zoneLine({
    series: [{ name: effIndex.short, data: window24.k, color: systemColor.EFFICIENCY }], compact: true,
  }), [window24]);

  const driverOption = useMemo(() => row ? hbars({
    items: data.families.map((f, n) => ({ name: systemName[f], value: row[4][n], color: systemColor[f] })),
    max: Math.max(40, ...row[4]),
  }) : null, [row, data.families]);

  const stamp = fmtDateTime(fromMs(ms));
  // Text alternative for the 24-h chart: current value and the range shown (formatting only).
  const trendLabel = useMemo(() => {
    const vals = window24.s.flatMap(([, v]) => (v == null ? [] : [v]));
    const range = vals.length ? t.trendRange(Math.min(...vals).toFixed(1), Math.max(...vals).toFixed(1)) : "";
    return `${t.trendTitle}: ${t.gaugeLabel} ${row ? `${row[1].toFixed(1)}, ${zoneName[row[2]]}` : t.gapTitle}. ${range}`;
  }, [window24, row]);
  const high = useMemo(() => periods.filter((p) => p.severity === "HIGH"), [periods]);

  return (
    <div className="flex flex-col gap-5">
      <ConsoleHeader />
      {/* One polite announcement, only when not playing, so screen readers are not flooded during playback. */}
      <p className="sr-only" role="status">{playing ? "" : `${stamp}: ${row ? `${zoneName[row[2]]}, ${healthIndex.name} ${row[1].toFixed(1)}` : t.gapTitle}`}</p>

      {/* Replay controls: the selected moment is the anchor of the page */}
      <section aria-label={t.replay.time} className="card z-10 lg:sticky lg:top-[calc(var(--header-h)+0.5rem)] flex flex-col gap-3 !px-5 !py-4 shadow-raised">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <div className="flex items-center gap-2">
            <button className="btn-navy w-[6.5rem] justify-center" onClick={() => { if (!playing && ms >= ix.end) setMs(ix.start); setPlaying((p) => !p); }}>
              {playing ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />} {playing ? t.replay.pause : t.replay.play}
            </button>
            <div role="group" aria-label={t.replay.speed} className="flex overflow-hidden rounded-panel border border-line-strong">
              {([1, 4] as const).map((sp) => (
                <button key={sp} className={`px-3 py-2 text-label font-semibold transition-colors ${speed === sp ? "bg-navy text-white" : "bg-white text-navy hover:bg-navy-tint"}`}
                  aria-pressed={speed === sp} onClick={() => setSpeed(sp)}>{sp}×</button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-outline !px-2 !py-2" onClick={() => go(ms - STEP)} aria-label={t.replay.stepBack}><ChevronLeft size={16} aria-hidden /></button>
            <div className="min-w-[10.5rem] text-center">
              <div className="t-caption">{t.replay.selected}</div>
              <div className="num text-section font-semibold text-navy-ink" aria-hidden>{stamp}</div>
            </div>
            <button className="btn-outline !px-2 !py-2" onClick={() => go(ms + STEP)} aria-label={t.replay.stepFwd}><ChevronRight size={16} aria-hidden /></button>
          </div>
          <label className="flex items-center gap-2">
            <span className="t-caption">{t.replay.goTo}</span>
            <input type="datetime-local" className="rounded-panel border border-line-strong px-2.5 py-1.5 text-label num transition-colors hover:border-navy" value={fromMs(ms)} step={600}
              min={fromMs(ix.start)} max={fromMs(ix.end)}
              onChange={(e) => e.target.value && go(toMs(e.target.value.slice(0, 16)))} />
          </label>
          <JumpChips high={high} onJump={go} />
        </div>
        <Scrubber ms={ms} ix={ix} onChange={go} periods={periods} />
      </section>

      {/* Score → state → contributing systems */}
      <div className="grid gap-5 lg:grid-cols-12">
        <section className="card !p-5 lg:col-span-4" aria-labelledby="gauge">
          <h2 id="gauge" className="t-label">{t.gaugeLabel}</h2>
          <StatusGauge value={row ? row[1] : null} zone={row ? row[2] : null} edges={data.bandEdges} />
        </section>
        <section className="card flex flex-col gap-3 !p-5 lg:col-span-3" aria-labelledby="state">
          <h2 id="state" className="t-label">{t.statusTitle}</h2>
          {row ? (
            <>
              <div><StatusPill zone={row[2]} size="lg" /></div>
              <p className="text-body text-ink">{zoneMeaning[row[2]]}</p>
              <div className="flex flex-col gap-2 border-t border-line pt-3 text-label">
                <p className="text-ink-body">{inState != null && t.inState(fmtDuration(inState / 60_000))}</p>
                <p className="flex items-center gap-1.5 font-medium text-ink">
                  {trend === "up" && <ArrowUpRight size={16} className="text-warning-ink" aria-hidden />}
                  {trend === "down" && <ArrowDownRight size={16} className="text-normal-ink" aria-hidden />}
                  {trend === "flat" && <ArrowRight size={16} className="text-ink-muted" aria-hidden />}
                  {trend && t.trend[trend]}
                </p>
              </div>
              {row[6].map((f) => (
                <p key={f} className="flex items-start gap-2 rounded-panel bg-watch/10 p-3 text-label text-watch-ink"><Info size={15} className="mt-0.5 shrink-0" aria-hidden />{flagText[f]}</p>
              ))}
            </>
          ) : (
            <GapNotice />
          )}
        </section>
        <section className="card !p-5 lg:col-span-5" aria-labelledby="drivers">
          <h2 id="drivers" className="t-label">{t.driversTitle}</h2>
          <p className="mb-2 text-caption text-ink-muted">{t.driversSub}</p>
          {row && driverOption ? (row[1] > 0.5
            ? <Chart option={driverOption} animate={!playing} height={200} label={data.families.map((f, n) => `${systemName[f]} ${row[4][n]}`).join(", ")} />
            : <p className="text-label text-ink-muted">{t.driversNone}</p>)
            : <GapNotice compact />}
        </section>
      </div>

      {/* Trend, reasons, efficiency */}
      <div className="grid gap-5 lg:grid-cols-12">
        <section className="card !p-5 lg:col-span-8" aria-labelledby="trend">
          <SectionHeader id="trend" title={t.trendTitle} sub={t.trendSub} />
          {window24.s.every(([, v]) => v == null) ? <GapNotice /> : <Chart option={trendOption} animate={!playing} height={250} label={trendLabel} />}
        </section>
        <div className="flex flex-col gap-5 lg:col-span-4">
          <section className="card !p-5" aria-labelledby="reasons">
            <h2 id="reasons" className="t-label mb-3">{t.reasonsTitle}</h2>
            {row ? (row[5].length ? (
              <ol className="flex flex-col gap-2.5">
                {row[5].map((r, n) => (
                  <li key={r} className="flex gap-2.5 text-label text-ink">
                    <NumberDot n={n + 1} />
                    <span>{reasonText[r] ?? r}</span>
                  </li>
                ))}
              </ol>
            ) : <p className="text-label text-ink-muted">{t.reasonsNone}</p>) : <GapNotice compact />}
          </section>
          <section className="card !p-5" aria-labelledby="eff">
            <h2 id="eff" className="t-label">{t.effTitle}</h2>
            <div className="mt-1 flex items-end justify-between gap-4">
              <div className="text-kpi font-bold text-navy-ink num">{row ? fmt1(row[3]) : "–"}</div>
              <div className="w-1/2">
                <p className="t-caption mb-0.5 text-right">{t.effSpark}</p>
                <Chart option={sparkOption} animate={!playing} height={48} label={`${effIndex.name}, ${t.effSpark}`} />
              </div>
            </div>
            <p className="mt-2 text-caption text-ink-muted">{effIndex.scale}</p>
          </section>
        </div>
      </div>

      <Decisions />
    </div>
  );
}

/** Static parts are memoised so a playback tick re-renders only what depends on the time. */
const ConsoleHeader = memo(function ConsoleHeader() {
  return (
    <PageHeader title={t.title} question={t.intro}>
      <Ribbon>{t.ribbon}</Ribbon>
    </PageHeader>
  );
});

const JumpChips = memo(function JumpChips({ high, onJump }: { high: Period[]; onJump: (ms: number) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 xl:ml-auto">
      <span className="t-caption">{t.replay.jump}</span>
      {high.map((p) => (
        <button key={p.id} className="chip-btn" onClick={() => onJump(toMs(p.onset))} aria-label={t.replay.jumpTo(pc.label(p.n), fmtDateTime(p.onset))}>
          <span className="font-semibold text-navy-ink">{pc.label(p.n)}</span><span className="num font-medium text-ink-muted">{fmtDateTime(p.onset)}</span>
        </button>
      ))}
    </div>
  );
});

const Decisions = memo(function Decisions() {
  return (
    <section aria-labelledby="decisions">
      <SectionHeader id="decisions" title={t.decisionsTitle} sub={t.decisionsSub} aside={<Badge tone="dashed">{common.illustrative}</Badge>} />
      <div className="grid gap-4 md:grid-cols-3">
        {t.decisions.map((d) => (
          <article key={d.title} className="card-dashed">
            <h3 className="t-card">{d.title}</h3>
            <p className="mt-1.5 text-caption font-semibold text-ink-muted">{d.when}</p>
            <p className="mt-2 text-label text-ink-body">{d.action}</p>
          </article>
        ))}
      </div>
    </section>
  );
});

function GapNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-start gap-3 rounded-panel border border-dashed border-line-strong bg-page p-4 text-ink-muted">
      <PowerOff size={18} className="mt-0.5 shrink-0" aria-hidden />
      <div>
        <p className="text-label font-semibold text-ink">{t.gapTitle}</p>
        {!compact && <p className="mt-1 text-label">{t.gapBody}</p>}
      </div>
    </div>
  );
}

/** Static track: gaps in grey, period ticks and month labels. Memoised; only the thumb moves. */
const Track = memo(function Track({ ix, periods }: { ix: Index; periods: Period[] }) {
  const span = ix.end - ix.start;
  const pct = (m: number) => ((m - ix.start) / span) * 100;
  return (
    <>
      <div className="absolute inset-x-0 top-3 h-2 rounded-full bg-navy-tint" aria-hidden>
        {ix.gaps.map((g) => (
          <div key={g.from} className="absolute top-0 h-2 bg-ink-muted/80" style={{ left: `${pct(g.from)}%`, width: `${Math.max(0.2, pct(g.to) - pct(g.from))}%` }} />
        ))}
        {periods.map((p) => (
          <div key={p.id} className={`absolute -top-1.5 h-1 rounded-full ${p.severity === "HIGH" ? "bg-navy-ink" : "bg-navy/70"}`}
            style={{ left: `${pct(toMs(p.start))}%`, width: `${Math.max(0.35, pct(toMs(p.end)) - pct(toMs(p.start)))}%` }} />
        ))}
      </div>
      <div className="pointer-events-none absolute inset-x-0 top-6 text-[11px] text-ink-muted" aria-hidden>
        {monthStarts(ix.start, ix.end).map((m) => <span key={m} style={{ position: "absolute", left: `${pct(m)}%` }}>{fmtMonth(fromMs(m).slice(0, 7))}</span>)}
      </div>
    </>
  );
});

/** Full-range strip: a range input over time with the current position and a legend. */
function Scrubber({ ms, ix, onChange, periods }: { ms: number; ix: Index; onChange: (ms: number) => void; periods: Period[] }) {
  const pct = ((ms - ix.start) / (ix.end - ix.start)) * 100;
  return (
    <div>
      <div className="relative h-10 rounded focus-within:ring-2 focus-within:ring-navy focus-within:ring-offset-2">
        <Track ix={ix} periods={periods} />
        <div className="pointer-events-none absolute top-1.5 h-5 w-1 rounded bg-navy-ink" style={{ left: `calc(${pct}% - 2px)` }} aria-hidden />
        <input type="range" aria-label={t.replay.scrub} className="absolute inset-0 h-8 w-full cursor-pointer opacity-0"
          min={ix.start} max={ix.end} step={STEP} value={ms} aria-valuetext={fmtDateTime(fromMs(ms))}
          onChange={(e) => onChange(Number(e.target.value))} />
      </div>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-caption text-ink-muted" aria-hidden>
        <li className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-navy-tint ring-1 ring-navy-line" />{t.legend.running}</li>
        <li className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-ink-muted/80" />{common.stopped}</li>
        <li className="flex items-center gap-1.5"><span className="h-1 w-3 rounded-full bg-navy-ink" />{t.legend.high}</li>
        <li className="flex items-center gap-1.5"><span className="h-1 w-3 rounded-full bg-navy/70" />{t.legend.other}</li>
      </ul>
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
