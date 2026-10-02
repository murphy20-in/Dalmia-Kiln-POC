import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowDownRight, ArrowRight, ArrowUpRight, ChevronLeft, ChevronRight, Info, Pause, Play, PowerOff } from "lucide-react";
import Chart from "../charts/Chart";
import { hbars } from "../charts/bars";
import { zoneLine } from "../charts/zoneLine";
import StatusGauge from "../components/StatusGauge";
import { Badge, Loading, NumberDot, PageBand, Ribbon, SectionHeader, StatusPill } from "../components/ui";
import { common, consoleCopy as t, effIndex, evidence, healthIndex, flagText, nav, periods as pc, reasonText, systemName, zoneMeaning, zoneName } from "../copy";
import { useData, type ConsoleData, type ConsoleRow, type Period } from "../data";
import { fmt1, fmtDate, fmtDateTime, fmtDuration, fmtStamp, fromMs, toMs } from "../lib/format";
import { chart, systemColor, type Zone } from "../theme";

const STEP = 10 * 60_000;
const HOUR = 60 * 60_000;
const DAY = 24 * HOUR;
const BLOCK = DAY;
const ZONES: Zone[] = ["N", "W", "A"];
/** State fills on the dark track (theme.ts → track). */
const ZONE_FILL: Record<Zone, string> = { N: "bg-track-normal", W: "bg-track-watch", A: "bg-track-warning pin" }; // Warning carries a texture as well as a colour

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
  // The timeline's state bar: one column per day, stacked by the share of that day's expected rows recorded in each
  // zone (Warning on top, Normal at the bottom). Presentation only: counts of the recorded zone, no new score, no
  // "dominant" rule that could hide a short excursion. Rows missing from a day leave blank space (the gap overlay names it).
  const start = times[0];
  const end = times[times.length - 1];
  const counts = Array.from({ length: Math.ceil((end - start) / BLOCK) + 1 }, () => [0, 0, 0]);
  c.rows.forEach((r, i) => { counts[Math.floor((times[i] - start) / BLOCK)][ZONES.indexOf(r[2])]++; });
  const perBlock = BLOCK / STEP;
  const segments = counts.flatMap((n, b) => (n[0] + n[1] + n[2] === 0 ? [] : [{
    from: start + b * BLOCK, to: Math.min(end, start + (b + 1) * BLOCK),
    share: { N: n[0] / perBlock, W: n[1] / perBlock, A: n[2] / perBlock } as Record<Zone, number>,
  }]));
  return { times, byTime, gaps, segments, nextIdx, runStart, start, end };
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
  const [sliderFocus, setSliderFocus] = useState(false); // the slider announces its own value, so the status line stays quiet then

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

  useEffect(() => { document.documentElement.classList.add("has-deck"); return () => document.documentElement.classList.remove("has-deck"); }, []);

  const go = useCallback((next: number) => { setPlaying(false); setMs(snap(next, ix)); }, [ix]);

  const i = ix.byTime.get(ms);
  const row: ConsoleRow | null = i == null ? null : data.rows[i];

  const inState = i == null ? null : ix.times[i] - ix.times[ix.runStart[i]] + STEP;
  // Only claim "stopped" where the recorded gap says so; a data gap is named as missing data, never as a plant state.
  const gapKind = row ? null : ix.gaps.find((g) => ms >= g.from && ms <= g.to)?.kind;
  const opState = row ? t.running : gapKind === "stopped" ? t.stoppedState : gapKind === "nodata" ? t.noDataState : t.stoppedOrNoData;

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
    series: [{ name: healthIndex.name, data: window24.s, color: chart.primary, width: 2.5 }],
    edges: data.bandEdges, periods: shaded, now: ms, note: shaded.length ? `${evidence.kpiDerived} shaded · ${evidence.notValidated}` : undefined,
  }), [window24, data.bandEdges, shaded, ms]);

  const sparkOption = useMemo(() => zoneLine({
    series: [{ name: effIndex.short, data: window24.k, color: systemColor.EFFICIENCY }], compact: true,
  }), [window24]);

  const driverOption = useMemo(() => row ? hbars({
    items: data.families.map((f, n) => ({ name: systemName[f], value: row[4][n], color: systemColor[f] })),
    max: Math.max(40, ...row[4]),
  }) : null, [row, data.families]);

  const stamp = fmtStamp(fromMs(ms));
  const announce = `${stamp}: ${row ? `${zoneName[row[2]]}, ${healthIndex.name} ${row[1].toFixed(1)}` : t.gapTitle}`;
  // Text alternative for the 24-h chart: current value and the range shown (formatting only).
  const trendLabel = useMemo(() => {
    const vals = window24.s.flatMap(([, v]) => (v == null ? [] : [v]));
    const range = vals.length ? t.trendRange(Math.min(...vals).toFixed(1), Math.max(...vals).toFixed(1)) : "";
    return `${t.trendTitle}: ${t.gaugeLabel} ${row ? `${row[1].toFixed(1)}, ${zoneName[row[2]]}` : t.gapTitle}. ${range}`;
  }, [window24, row]);
  const high = useMemo(() => periods.filter((p) => p.severity === "HIGH"), [periods]);

  return (
    <>
      <ConsoleBand />
      <div className="mx-auto flex w-full max-w-page flex-col gap-5 px-4 py-6 sm:px-8">
        {/* One polite announcement, only when not playing, so screen readers are not flooded during playback. */}
        <p className="sr-only" role="status">{playing || sliderFocus ? "" : announce}</p>

        {/* The console deck: the selected moment is the anchor of the page. Dark environment, light analytics beneath. */}
        <section aria-label={t.replay.time} className="on-dark deck-sticky relative isolate z-10 overflow-hidden rounded-shell border border-sage/20 bg-deck shadow-dark ring-1 ring-inset ring-white/[0.04]">
          <div className="flex flex-col gap-3 p-4 sm:p-5">
            {/* Header, in priority order: selected timestamp → historical state → running / data. */}
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              <div aria-hidden className="min-w-[14rem]">
                <p className="eyebrow-dark">{t.deckEyebrow}</p>
                <p className="num mt-1 text-[1.75rem] font-semibold uppercase leading-8 tracking-tight text-white">{stamp}</p>
              </div>
              <div aria-hidden className="border-l border-sage/15 pl-6">
                <p className="font-mono text-eyebrow font-medium uppercase text-sage">{healthIndex.name}</p>
                {row ? (
                  <div className="mt-1 flex items-center gap-3">
                    <span className="num text-[1.75rem] font-semibold leading-8 text-white">{row[1].toFixed(1)}</span>
                    <StatusPill zone={row[2]} />
                  </div>
                ) : (
                  <span className="hatch mt-1 inline-block rounded px-2 py-1 font-mono text-eyebrow font-medium uppercase text-mist">{t.noData}</span>
                )}
              </div>
              <div aria-hidden className="border-l border-sage/15 pl-6 sm:ml-auto">
                <p className="font-mono text-eyebrow font-medium uppercase text-sage">{t.deckState}</p>
                <p className="mt-1 text-label font-semibold text-white">{opState}</p>
                <p className="text-caption text-sage">{row ? t.dataPresent : t.dataAbsent}</p>
              </div>
            </div>
            {/* Legend, state bar, abnormal-period strip, selected marker and date scale: one track. */}
            <Scrubber ms={ms} ix={ix} onChange={go} periods={periods} valueText={announce} onFocusChange={setSliderFocus} />
            {/* Replay controls, separated by a hairline, still inside the same container. */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-sage/15 pt-4">
              <button className="btn-primary w-[6.5rem] justify-center" onClick={() => { if (!playing && ms >= ix.end) setMs(ix.start); setPlaying((p) => !p); }}>
                {playing ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />} {playing ? t.replay.pause : t.replay.play}
              </button>
              <div role="group" aria-label={t.replay.speed} className="flex overflow-hidden rounded-panel border border-sage/30">
                {([1, 4] as const).map((sp) => (
                  <button key={sp} className={`px-3 py-2 text-label font-semibold transition-colors duration-fast ${speed === sp ? "bg-emerald/20 text-white ring-1 ring-inset ring-emerald" : "text-mist hover:bg-white/10 hover:text-white"}`}
                    aria-pressed={speed === sp} onClick={() => setSpeed(sp)}>{sp}×</button>
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                <button className="btn-ghost !px-2 !py-2" onClick={() => go(ms - STEP)} aria-label={t.replay.stepBack}><ChevronLeft size={16} aria-hidden /></button>
                <button className="btn-ghost !px-2 !py-2" onClick={() => go(ms + STEP)} aria-label={t.replay.stepFwd}><ChevronRight size={16} aria-hidden /></button>
              </div>
              <label className="flex items-center gap-2">
                <span className="text-caption text-sage">{t.replay.goTo}</span>
                <input type="datetime-local" className="rounded-panel border border-sage/70 bg-white/[0.06] px-2.5 py-1.5 text-label text-white num transition-colors duration-fast [color-scheme:dark] hover:border-emerald/60" value={fromMs(ms)} step={600}
                  min={fromMs(ix.start)} max={fromMs(ix.end)}
                  onChange={(e) => e.target.value && go(toMs(e.target.value.slice(0, 16)))} />
              </label>
              <JumpChips high={high} onJump={go} />
            </div>
          </div>
        </section>

        {/* Score → state → contributing systems */}
        <div className="grid gap-5 lg:grid-cols-12">
          <section className="card !p-5 lg:col-span-4" aria-labelledby="gauge">
            <h2 id="gauge" className="eyebrow">{t.gaugeLabel}</h2>
            <StatusGauge value={row ? row[1] : null} zone={row ? row[2] : null} edges={data.bandEdges} />
          </section>
          <section className="card flex flex-col gap-3 !p-5 lg:col-span-3" aria-labelledby="state">
            <h2 id="state" className="eyebrow">{t.statusTitle}</h2>
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
            <h2 id="drivers" className="eyebrow">{t.driversTitle}</h2>
            <p className="mb-2 mt-1 text-caption text-ink-muted">{t.driversSub}</p>
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
              <h2 id="reasons" className="eyebrow mb-3">{t.reasonsTitle}</h2>
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
              <h2 id="eff" className="eyebrow">{t.effTitle}</h2>
              <div className="mt-1 flex items-end justify-between gap-4">
                <div className="text-kpi font-semibold text-ink num">{row ? fmt1(row[3]) : "–"}</div>
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
    </>
  );
}

/** Static parts are memoised so a playback tick re-renders only what depends on the time. */
const ConsoleBand = memo(function ConsoleBand() {
  return (
    <PageBand eyebrow={nav.groups.intelligence} title={t.title} question={t.intro} actions={<div className="max-w-sm"><Ribbon dark>{t.ribbon}</Ribbon></div>} />
  );
});

const JumpChips = memo(function JumpChips({ high, onJump }: { high: Period[]; onJump: (ms: number) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
      <span className="text-caption text-sage">{t.replay.jump}</span>
      {high.map((p) => (
        <button key={p.id} className="chip-dark" onClick={() => onJump(toMs(p.onset))} aria-label={t.replay.jumpTo(pc.label(p.n), fmtDateTime(p.onset))}>
          <span className="text-white">{pc.label(p.n)}</span>{" "}<span className="num font-medium text-sage">{fmtDateTime(p.onset)}</span>
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

/** A gap is drawn as a hatched, labelled absence: never interpolated, never a continuous measurement. */
function GapNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className="hatch flex items-center justify-center rounded-panel border border-dashed border-line-strong bg-subtle p-4">
      <div className="flex max-w-sm items-start gap-3 rounded-panel bg-white/95 px-4 py-3 text-ink-muted shadow-card">
        <PowerOff size={18} className="mt-0.5 shrink-0" aria-hidden />
        <div>
          <p className="eyebrow text-ink">{t.noData}</p>
          <p className="mt-0.5 text-label font-semibold text-ink">{t.gapTitle}</p>
          {!compact && <p className="mt-1 text-label">{t.gapBody}</p>}
        </div>
      </div>
    </div>
  );
}

/** Scale marks: the 1st, 8th, 15th and 22nd of each month; the 1st carries the month name. */
function scaleTicks(start: number, end: number) {
  const out: { ms: number; label: string; major: boolean }[] = [];
  for (let m = Math.ceil(start / DAY) * DAY; m <= end; m += DAY) {
    const dom = new Date(m).getUTCDate();
    if (dom === 1 || dom === 8 || dom === 15 || dom === 22) out.push({ ms: m, major: dom === 1, label: dom === 1 ? fmtDate(fromMs(m)) : String(dom) });
  }
  return out;
}

/**
 * The marks of the timeline, in flow so they share one horizontal grid (the lane they sit in):
 * state ribbon (52 px) → abnormal-period strip (10 px) → date scale (16 px). Memoised; only the marker moves.
 *
 * The ribbon is one continuous surface, not 92 separate bars: the columns butt against each other with no
 * divider and overlap by half a pixel, so neighbouring days read as a band of recorded history rather than
 * as a comb. What a column encodes is unchanged (see buildIndex): the share of that day's expected rows
 * recorded in each state, Warning on top, Normal at the base.
 */
const Track = memo(function Track({ ix, periods }: { ix: Index; periods: Period[] }) {
  const span = ix.end - ix.start;
  const pct = (m: number) => ((m - ix.start) / span) * 100;
  const ticks = useMemo(() => scaleTicks(ix.start, ix.end), [ix]);
  return (
    <>
      {/* State ribbon: one column per day, Warning stacked on top; stopped or missing data is a neutral gap. */}
      <div className="relative h-[52px] overflow-hidden rounded-lg bg-abyss/80 shadow-well ring-1 ring-inset ring-sage/20" aria-hidden>
        {ix.segments.map((s) => (
          <div key={s.from} className="absolute inset-y-0 flex flex-col justify-end" style={{ left: `${pct(s.from)}%`, width: `calc(${pct(s.to) - pct(s.from)}% + 0.5px)` }}>
            {(["A", "W", "N"] as const).map((z) => s.share[z] > 0 && <div key={z} className={ZONE_FILL[z]} style={{ height: `${Math.min(100, s.share[z] * 100)}%` }} />)}
          </div>
        ))}
        {ix.gaps.map((g) => (
          <div key={g.from} className="hatch absolute inset-y-0 bg-track-gap/45" style={{ left: `${pct(g.from)}%`, width: `calc(${Math.max(0.2, pct(g.to) - pct(g.from))}% + 0.5px)` }} />
        ))}
        {/* The floor of the ribbon: a hairline, so the band sits on a surface instead of floating in the well. */}
        <span className="absolute inset-x-0 bottom-0 h-px bg-abyss/60" />
      </div>
      {/* Abnormal periods (KPI-derived, not validated plant events): a strip directly under the ribbon. */}
      <div className="relative mt-[3px] h-2.5" aria-hidden>
        {periods.map((p) => (
          <div key={p.id} className={`absolute rounded-full ${p.severity === "HIGH" ? "top-0 h-2.5 bg-track-high" : "top-[3px] h-1 bg-track-other"}`}
            style={{ left: `${pct(toMs(p.start))}%`, width: `${Math.max(0.4, pct(toMs(p.end)) - pct(toMs(p.start)))}%` }} />
        ))}
      </div>
      {/* Date scale: a tick at the mark, its label beside it. No full-height rules — they cut the object into cells. */}
      <div className="pointer-events-none relative mt-1.5 h-4" aria-hidden>
        {ticks.map((k) => (
          <span key={k.ms} className="absolute top-0 flex items-start gap-1.5" style={{ left: `${pct(k.ms)}%` }}>
            <span className={`h-1.5 w-px shrink-0 ${k.major ? "bg-sage/70" : "bg-sage/30"}`} />
            <span className={`font-mono text-[11px] leading-[14px] ${k.major ? "font-medium text-mist" : "text-sage max-sm:hidden"}`}>{k.label}</span>
          </span>
        ))}
      </div>
    </>
  );
});

const Key = ({ swatch, children }: { swatch: string; children: string }) => (
  <li className="flex items-center gap-1.5"><span className={`h-2.5 w-4 shrink-0 rounded-sm ${swatch}`} />{children}</li>
);

/**
 * HistoricalConsoleTimeline: the timeline as ONE object — a well cut into the deck, clipped by its own border.
 * Three fused parts, with no floating row anywhere between or beside them:
 *   header strip   title · the range of recorded history · the four state keys
 *   lane           marker flag → state ribbon → period strip → date scale → selected marker, all on one grid
 *   footer strip   period keys · the evidence labels · how to read a column
 * Everything the timeline depicts lives inside this well; the deck around it carries only the title, the
 * selected moment and the replay controls.
 */
function Scrubber({ ms, ix, onChange, periods, valueText, onFocusChange }: {
  ms: number; ix: Index; onChange: (ms: number) => void; periods: Period[]; valueText: string; onFocusChange: (focused: boolean) => void;
}) {
  const pct = ((ms - ix.start) / (ix.end - ix.start)) * 100;
  return (
    <div className="relative overflow-hidden rounded-2xl border border-sage/25 bg-track shadow-inset focus-within:outline focus-within:outline-2 focus-within:outline-transparent focus-within:ring-2 focus-within:ring-emerald">
      {/* Internal header: the keys describe this track, so they sit on its own strip — never floating above it. */}
      <div aria-hidden className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-sage/15 bg-abyss/40 px-4 py-2">
        <p className="font-mono text-eyebrow font-medium uppercase text-emerald">{t.legend.title}</p>
        <p className="num font-mono text-caption text-sage">{fmtDate(fromMs(ix.start))} – {fmtDate(fromMs(ix.end))}</p>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-mist sm:ml-auto">
          <Key swatch="bg-track-normal">{t.legend.normal}</Key>
          <Key swatch="bg-track-watch">{t.legend.watch}</Key>
          <Key swatch="bg-track-warning pin">{t.legend.warning}</Key>
          <Key swatch="hatch bg-track-gap/45">{t.legend.gap}</Key>
        </ul>
      </div>
      <div className="px-4 pb-3 pt-2.5">
        {/* The lane: every row below shares its width, so the marker, ribbon, strip and scale line up exactly. */}
        <div className="relative">
          {/* Marker flag: the selected moment, labelled inside the timeline. The pill is kept inside the lane; the caret and line sit at the true position. */}
          <div aria-hidden className="relative h-5">
            <span className="absolute top-0 -translate-x-1/2 whitespace-nowrap rounded-md bg-emerald px-2 py-0.5 font-mono text-[11px] font-semibold leading-[14px] text-forest shadow-glow" style={{ left: `clamp(56px, ${pct}%, calc(100% - 56px))` }}>{fmtDateTime(fromMs(ms))}</span>
            <span className="absolute top-[15px] h-[5px] w-2 -translate-x-1/2 bg-emerald [clip-path:polygon(0_0,100%_0,50%_100%)]" style={{ left: `${pct}%` }} />
          </div>
          <Track ix={ix} periods={periods} />
          {/* The selected marker runs the full depth of the ribbon and the period strip, and no further. */}
          <div aria-hidden className="pointer-events-none absolute top-5 h-[65px] w-0.5 -translate-x-1/2 bg-emerald shadow-glow ring-1 ring-abyss/70" style={{ left: `${pct}%` }} />
          <input type="range" aria-label={t.replay.scrub} className="absolute inset-x-0 top-0 h-[85px] w-full cursor-pointer appearance-none bg-transparent opacity-0 [touch-action:pan-y] [&::-moz-range-thumb]:h-0 [&::-moz-range-thumb]:w-0 [&::-moz-range-thumb]:border-0 [&::-webkit-slider-thumb]:h-0 [&::-webkit-slider-thumb]:w-0 [&::-webkit-slider-thumb]:appearance-none"
            min={ix.start} max={ix.end} step={STEP} value={ms} aria-valuetext={valueText} aria-describedby="timeline-desc"
            onFocus={() => onFocusChange(true)} onBlur={() => onFocusChange(false)}
            onChange={(e) => onChange(Number(e.target.value))} />
          <p id="timeline-desc" className="sr-only">{t.legend.sr}</p>
        </div>
      </div>
      <ul aria-hidden className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-sage/15 bg-abyss/40 px-4 py-2 text-caption text-sage">
        <Key swatch="!h-2.5 bg-track-high">{t.legend.high}</Key>
        <Key swatch="!h-1 bg-track-other">{t.legend.other}</Key>
        <li>{evidence.kpiDerivedPlural} · {evidence.notValidatedPlural}</li>
        <li className="sm:ml-auto">{t.legend.note}</li>
      </ul>
    </div>
  );
}
