// Every user-facing string lives here so the wording can be reviewed in one place.
// tests/wording.test.ts scans this file. Words about present-time monitoring are allowed only
// in the Console ribbon and inside the marked future-stages block of the Roadmap.

export const brandLine = { dalmia: "DALMIA CEMENT", vendor: "Astrikos AI", product: "Kiln Intelligence" };
export const topChip = "Ariyalur Kiln · Historical data Jun–Aug 2025";
export const footer = "Built by Astrikos AI for Dalmia Cement, Ariyalur";

export const nav = {
  summary: "Executive Summary",
  console: "Kiln Health Console",
  efficiency: "Efficiency Story",
  periods: "Abnormal Periods",
  fuel: "Alternative Fuel",
  data: "Data Readiness",
  roadmap: "Roadmap & Value",
  validation: "How we validated",
  collapse: "Collapse menu",
  expand: "Expand menu",
  present: "Present",
  presentHint: "Presentation mode (P). Use ← → to move between pages.",
  exitPresent: "Exit presentation",
};

export const zoneName = { N: "Normal", W: "Watch", A: "Warning", C: "Critical" } as const;
export const zoneMeaning = {
  N: "Within the range your kiln showed in April–May.",
  W: "Drifting from your April–May normal. Worth watching.",
  A: "Well above your April–May normal, usually across several systems.",
  C: "Activates after calibration with your event logs.",
};
export const healthIndex = {
  name: "Kiln Health Index",
  scale: "0 = your April–May normal. Higher = further from normal.",
};
export const effIndex = {
  name: "Efficiency Deterioration Index",
  short: "Efficiency Index",
  scale: "0 = your April–May normal. Higher = less efficient.",
};

export const systemName: Record<string, string> = {
  EFFICIENCY: "Heat efficiency",
  COMBUSTION: "Combustion",
  THERMAL: "Thermal profile",
  DRAFT_PRESSURE: "Draft & pressure",
  STABILITY: "Process stability",
  BREADTH_PERSISTENCE: "Several systems, sustained",
};

export const reasonText: Record<string, string> = {
  COMBUSTION_DEVIATION: "Combustion readings (O₂, CO, NOx) are outside their normal range",
  DRAFT_PRESSURE_DEVIATION: "Draft and pressure (fans, dampers, preheater pressure) are outside their normal range",
  THERMAL_DEVIATION: "Kiln and preheater temperatures are outside their normal range",
  PROCESS_VARIABILITY_DEVIATION: "The process is swinging more than usual",
  EFFICIENCY_COMPONENT_DEVIATION: "Specific heat is above normal for this feed rate",
  MULTI_FAMILY_CONCURRENCE: "Several systems are off normal at the same time",
  PERSISTENT_DEVIATION: "The deviation has lasted most of the last 3 hours",
};
export const flagText: Record<string, string> = {
  SUSPECT_ANALYSER_AMBIENT_O2: "Kiln-inlet O₂ analyser may be reading ambient air. Check the instrument before acting.",
  POST_RESTART_SETTLING: "Kiln is still settling after a restart.",
};
export const severityName = { HIGH: "High", MODERATE: "Moderate", LOW: "Low" } as const;

export const labels = {
  month: "Month", day: "Day", system: "System", period: "Period", dataset: "Dataset",
  start: "Start", end: "End", duration: "Duration", severity: "Severity", mainSystem: "Main system",
  headline: "Headline numbers", skip: "Skip to content", pages: "Pages", with: "with",
  examples: "Examples of issues caught", rigour: "How the work was checked", domino: "What happens when alternative fuel stops",
  severityLegend: (s: string) => `${s} severity`,
};

export const common = {
  viewData: "View data",
  viewChart: "View chart",
  loading: "Loading…",
  error: "This section could not load its data.",
  stopped: "Kiln stopped / no data",
  illustrative: "Stage 3 · illustrative",
  close: "Close",
};

// ---------------------------------------------------------------- 1. Executive Summary
export const summary = {
  eyebrow: "Stage 1 · delivered on your data",
  heroTitle: "Kiln efficiency and deposit-risk intelligence for Ariyalur",
  heroSub: (rows: string) => `Built on ${rows} rows of your own SCADA data.`,
  heroCta: "Open the Kiln Health Console",
  heroCta2: "See the Stage 2 ask",
  journeyTitle: "Where Ariyalur is on the journey",
  journey: [
    { label: "Reactive", note: "Today: problems seen after they happen", state: "past" },
    { label: "Early detection", note: "Delivered on your data", state: "done" },
    { label: "Prediction", note: "Next: needs your event logs", state: "next" },
    { label: "Planned intervention", note: "Stages 3–4", state: "future" },
  ] as const,
  kpis: {
    rows: { label: "rows analysed", sub: (tags: number) => `${tags} process tags · Apr–Sep 2025` },
    periods: { label: "abnormal periods found automatically", sub: "Jun–Aug 2025, from process data" },
    eff: { label: "Efficiency Index, June → August", sub: "0 = your April–May normal" },
    issues: { label: "data issues caught before modelling", sub: "1 critical · 4 high · 16 medium · 11 low / info" },
  },
  findingsTitle: "What your kiln data revealed",
  findings: {
    drift: { title: "Time in Warning doubled from June to August", body: "Share of running time the Kiln Health Index spent in Warning.", link: "See the efficiency story" },
    multi: { title: (n: number, t: number) => `${n} of ${t} abnormal periods involved several systems at once`, body: "Thermal, combustion and draft most often moved together.", link: "See the periods" },
    multiLegend: { many: "several systems", one: "one system" },
    fuelFrom: "Alternative fuel (AFR) stops",
    fuelTo: (tph: number) => `PC coal +${tph} TPH`,
    fuelAfter: "Thermal profile: preheater, TAD and hood temperatures dip in the same hours.",
    fuel: { title: (tph: number) => `When alternative fuel stops, PC coal rises about ${tph} TPH within the hour`, body: "A coal-for-AFR swap seen across April–July and again in August.", link: "See alternative fuel" },
  },
  objectivesTitle: "Your seven first-phase objectives",
  objectives: [
    { name: "Normal operating baseline", status: "delivered", note: "203 tags; running vs stopped detected automatically" },
    { name: "Efficiency deterioration KPI", status: "delivered", note: "One 0–100 index from 33 tags across 5 systems" },
    { name: "Leading indicators", status: "signals", note: "One weak candidate (PC-coal firing rising about an hour before index increases); likely an operator response, not usable yet" },
    { name: "Alternative fuel vs kiln behaviour", status: "delivered", note: "27 of 43 patterns from April–July repeated in August" },
    { name: "Historical abnormal periods", status: "delivered", note: "12 found automatically, 11 multi-system" },
    { name: "Preliminary score: Kiln Health Index", status: "delivered", note: "A 0–100 index against your April–May normal, with Normal / Watch / Warning" },
    { name: "Early warning", status: "next", note: "Needs your event logs to calibrate" },
  ] as const,
  objectiveStatus: { delivered: "Delivered", signals: "Weak signal only", next: "Next stage: needs event logs" },
  cta: {
    title: "Early detection is delivered on your data. Early warning is the next stage.",
    body: "To start Stage 2 we need four things, starting with your coating, ring, cleaning and stoppage logs.",
    button: "See what Stage 2 needs from Dalmia",
  },
};

// ---------------------------------------------------------------- 2. Console
export const consoleCopy = {
  title: "Kiln Health Console",
  intro: "What a shift engineer would see, replayed on your June–August data.",
  ribbon: (t: string) => `Replay of historical data · ${t}. Live mode arrives with SCADA integration.`,
  gaugeLabel: healthIndex.name,
  gaugeAlt: (v: string, zone: string) => `${healthIndex.name} ${v} out of 100: ${zone}.`,
  criticalLocked: "Critical activates after calibration with your event logs",
  statusTitle: "Current state",
  inState: (d: string) => `In this state for ${d}`,
  trend: { up: "Rising over the last 3 h", down: "Easing over the last 3 h", flat: "Steady over the last 3 h", none: "Not enough history for a 3 h trend" },
  effTitle: effIndex.name,
  effSpark: "Last 24 h",
  driversTitle: "What's driving it",
  driversSub: "Index points contributed by each system at this moment",
  driversNone: "No system is contributing. The kiln is at its April–May normal.",
  reasonsTitle: "Top reasons",
  reasonsNone: "No system is outside its normal range right now.",
  trendTitle: "Last 24 hours",
  trendSub: "Shaded blocks are abnormal operating periods found in the history.",
  decisionsTitle: "Decision support",
  decisionsSub: "How the console will point to a decision once calibrated. Not tied to the moment being replayed.",
  decisions: [
    { title: "Optimise operation", when: "When Watch persists for a shift", action: "Review fuel and air balance, check analysers, steady the feed. No stop needed." },
    { title: "Planned cleaning / ring removal", when: "When Warning persists across shifts with thermal and draft signs", action: "Once your event logs confirm the link, review whether a cleaning window is warranted." },
    { title: "Planned shutdown for inspection", when: "When Critical is reached (after calibration)", action: "Discuss an inspection stop with crews and spares ready." },
  ],
  replay: {
    time: "Replay time",
    jump: "Jump to where a high-severity period began drifting",
    play: "Play",
    pause: "Pause",
    speed: "Speed",
    scrub: "Scrub through June to August",
    stepBack: "Back 10 minutes",
    stepFwd: "Forward 10 minutes",
  },
  gapTitle: "Kiln stopped / no data",
  gapBody: "The kiln was stopped, restarting, or the data was incomplete at this time. Nothing is drawn rather than guessed.",
};

// ---------------------------------------------------------------- 3. Efficiency
export const efficiency = {
  title: "Efficiency Story",
  question: "Is my kiln getting less efficient?",
  hero: (a: string, b: string) => `Time in Warning: ${a} in June → ${b} in August.`,
  heroSub: "Share of running time the Kiln Health Index spent in Warning, measured against your April–May normal. The August-versus-June difference is the one that holds up statistically.",
  zonesTitle: "Warning grew every month while Normal shrank",
  dailyTitle: "The daily index climbed through July and stayed high in August",
  dailySub: "Daily median of the Kiln Health Index (0–100). Dotted lines mark the day each abnormal period (#1–#12) began; gaps are days the kiln was stopped or had no data. Drag the handles below to zoom.",
  o2Toggle: "Sensitivity check: O₂ analyser excluded",
  o2Note: "Sensitivity view: the index refitted without the kiln-inlet O₂ analyser, on its own reference. Compare the shape, not the zones.",
  o2Legend: "O₂ analyser excluded",
  primaryLegend: "Kiln Health Index",
  driversTitle: "Each month, combustion or draft was the biggest single-system source",
  driversSub: "Share of index points from each system, by month. Several systems moving together, for hours, adds the rest.",
  insights: {
    median: (a: string, b: string) => ({ title: `Median index rose from ${a} to ${b}`, body: "June to August. August's time in Warning was above June's under all 25 alternative settings we tried." }),
    eff: (a: string, b: string) => ({ title: `Efficiency Index ${a} in June, ${b} in August`, body: "The rise is driven by process deviation (combustion, thermal, draft, stability). Specific heat did not rise against your April–May reference, so this is process drift, not a measured fuel-efficiency loss. Part of June's low level reflects the fit to April–May." }),
    o2: { title: "A question only your team can answer", body: "Part of the August rise may trace to the kiln-inlet O₂ analyser: leaving it out roughly halves the rise. Its calibration schedule will tell us how much is process and how much is instrument." },
  },
};

// ---------------------------------------------------------------- 4. Periods
export const periods = {
  title: "Abnormal Periods",
  question: "What went wrong, when, and which systems?",
  subtitle: "Found automatically from process data; next step is matching them to your plant logs.",
  tiles: { total: "abnormal periods, Jun–Aug", high: "high severity", multi: "involved several systems", longest: "longest period" },
  ganttTitle: "Periods cluster in mid-June and mid-July",
  ganttSub: "Each bar is one abnormal operating period. Click a bar for details.",
  heatTitle: "Combustion, thermal and draft deviate together most often",
  heatSub: "How far each system moved from its April–May normal during each period (darker = further)",
  label: (n: number) => `Period ${n}`,
  drawer: {
    when: "When",
    duration: "Duration",
    severity: "Severity",
    dominant: "Main system",
    systems: "Systems involved",
    load: "Load context",
    robust: "Repeatable?",
    robustVal: (p: string) => `Found again in ${p} of alternative settings`,
    chart: "Kiln Health Index, 24 h either side",
    replay: "Replay from where the drift began",
    onset: "Drift began",
  },
  loadText: (load: string, change: string) => load === "LOAD_ASSOCIATED"
    ? `Feed changed ${change} TPH against the 2 hours before, so load may have contributed.`
    : `Feed changed ${change} TPH against the 2 hours before (load link uncertain).`,
};

// ---------------------------------------------------------------- 5. Alternative fuel
export const fuel = {
  title: "Alternative Fuel",
  question: "How is co-processing affecting my kiln?",
  hero: "When alternative fuel stops, PC coal steps in within the hour.",
  heroSub: (a: number, c: number) => `${c} of ${a} fuel–process patterns seen in April–July repeated in August. AFR = alternative fuel (solid), TAD = tertiary air duct.`,
  domino: [
    { title: "AFR feed stops", body: "Solid alternative fuel drops to zero while the kiln keeps running." },
    { title: (tph: number) => `PC coal +${tph} TPH`, body: "Median rise within 1 hour, against matched periods with no AFR change." },
    { title: "Temperatures dip", body: "Preheater cyclone, TAD and hood temperatures fall in the same hours." },
  ],
  monthlyTitle: "AFR use eased from April to August while kiln feed stayed between about 380 and 420 TPH",
  afrPanel: "Mean AFR while running (TPH)",
  feedPanel: "Median kiln feed while running (TPH)",
  cardsTitle: "What moves with alternative fuel",
  strengthHint: "These are patterns seen together, not proven causes. The label shows how consistently a link repeated, not how big it is.",
  august: "Confirmed on August hold-out",
  notAugust: "Same direction in August, not yet firm",
  cards: {
    feed: { title: "AFR tracks kiln feed", body: (e: string) => `More feed, more AFR (correlation ${e} in June–July).` },
    coal: { title: "PC coal steps in when AFR stops", body: (e: string) => `Median ${e} TPH more PC coal in the hour after an AFR stop.` },
    o2: { title: "More AFR, lower preheater O₂", body: (e: string) => `Correlation ${e} after allowing for feed.` },
    nox: { title: "More AFR, falling NOx", body: (e: string) => `NOx changes move against AFR changes (correlation ${e}).` },
    tad: { title: "TAD temperature dips after AFR ramps down", body: (e: string) => `Median ${e} °C, one to three hours later.` },
    cyclone1: { title: "Cyclone 1 cools after AFR stops", body: (e: string) => `Median ${e} °C in the following hour.` },
    hood: { title: "Hood temperature dips after AFR ramps down", body: (e: string) => `Median ${e} °C, one to three hours later.` },
  } as Record<string, { title: string; body: (e: string) => string }>,
  deeperTitle: "To go deeper",
  deeperBody: "Your data records how much alternative fuel was fired, not what it was. Share these and we can link fuel quality to deposit risk:",
  deeperItems: ["Calorific value", "Moisture", "RDF / plastic split", "Fuel mix by source", "Chlorine and ash"],
  deeperUnlocks: "Unlocks fuel-quality → deposit-risk modelling.",
  caveat: "These are links seen in the data. The operator's reasons for each AFR change are not in the logs.",
};

// ---------------------------------------------------------------- 6. Data readiness
export const dataPage = {
  title: "Data Readiness",
  question: "Can we trust this, and what do you need?",
  coverageTitle: "Two logs are missing a whole month: main kiln (September) and Kiln-IIIA (April)",
  coverageSub: "Share of minutes present per dataset and month",
  issuesTitle: (n: number) => `${n} data issues caught before any modelling`,
  issuesSub: "By severity. Each was fixed, masked or set aside, never silently used.",
  sev: { critical: "Critical", high: "High", medium: "Medium", low: "Low", info: "Info" } as Record<string, string>,
  criticalNote: "The one critical issue: no kiln event logs were supplied. That is the Stage 2 ask.",
  rigour: [
    { title: "Tested against hindsight", body: "From baseline to scoring, no result uses data from after the moment it describes." },
    { title: "Reproducible", body: "Re-running any stage gives exactly the same numbers." },
    { title: "Independently reviewed", body: "Each stage was checked by independent engineering reviewers." },
    { title: "Versioned", body: "Every number traces to a frozen, versioned output." },
  ],
  asksTitle: "What we need from you",
  priority: (p: number) => (p === 1 ? "Priority 1" : "Priority 2"),
  unlocks: "Unlocks",
  copy: "Copy request",
  copied: "Copied",
  requestText: (title: string, detail: string) => `Request from Astrikos AI (Kiln Intelligence, Ariyalur): ${title}. ${detail}`,
};

// ---------------------------------------------------------------- 7. Roadmap
// wording:allow-live-start (future stages may name live integration)
export const roadmap = {
  title: "Roadmap & Value",
  question: "What do we get, and what does it take?",
  stages: [
    { tag: "Stage 1", title: "Early detection", when: "Delivered", done: true,
      get: ["Data-health audit", "Normal baseline for 203 tags", "Efficiency Deterioration Index", "Abnormal-period finder", "Alternative-fuel analysis", "Historical Kiln Health Console"],
      need: ["SCADA exports (received: five complete months, two re-exports needed)"] },
    { tag: "Stage 2", title: "Early warning", when: "8–12 weeks",
      get: ["Abnormal periods matched to your events", "Early-warning calibration on labelled events", "Critical state switched on", "Validation with your process engineers"],
      need: ["Coating / ring / cleaning / stoppage logs", "O₂ analyser calibration schedule", "Fuel-quality logs", "A process-engineering point of contact"] },
    { tag: "Stage 3", title: "Operator console", when: "After Stage 2",
      get: ["Live SCADA / historian integration", "Real-time operator console", "Alerts and shift reports", "Decision support in the control room"],
      need: ["Read-only historian access", "IT and OT security sign-off"] },
    { tag: "Stage 4", title: "Planned intervention", when: "Scale-up",
      get: ["Intervention recommendations", "Fuel-mix optimisation", "Roll-out to other kilns"],
      need: ["Fuel-lab integration", "Operations sponsorship"] },
  ],
  investment: "Stage 2 investment: to be scoped with you.",
  youGet: "You get",
  weNeed: "We need from you",
};
// wording:allow-live-end

export const value = {
  title: "What could early detection be worth?",
  label: "Illustrative: your inputs, not a measured result.",
  placeholder: "Grey values are placeholders. Type your own.",
  inputs: {
    clinkerTpd: { label: "Clinker output", unit: "t/day" },
    contributionPerT: { label: "Contribution per tonne", unit: "₹/t" },
    runningDays: { label: "Running days per year", unit: "days" },
    stoppageHours: { label: "Unplanned stoppage", unit: "h/yr" },
    depositSharePct: { label: "Share linked to deposits / rings", unit: "%" },
    convertiblePct: { label: "Share convertible to planned stops", unit: "%" },
    downtimeSavedPct: { label: "Downtime saved when planned", unit: "%" },
    heatKcalPerKg: { label: "Heat consumption", unit: "kcal/kg" },
    fuelPerMkcal: { label: "Fuel cost", unit: "₹/Mkcal" },
    efficiencyGainPct: { label: "Efficiency gain (enter your own)", unit: "%" },
  } as Record<string, { label: string; unit: string }>,
  groups: { production: "Stoppages", fuel: "Fuel" },
  out: {
    hours: "Production hours recovered",
    production: "Avoided production loss",
    fuel: "Fuel saving",
    total: "Total per year",
  },
  perYear: "/ yr",
  reset: "Reset to placeholders",
};

export const ask = {
  title: "The Stage 2 pilot needs four things from Dalmia",
  items: [
    "Coating, ring, cleaning and stoppage logs for April–September 2025",
    "The kiln-inlet O₂ analyser calibration schedule",
    "Alternative-fuel quality logs",
    "A process-engineering point of contact",
  ],
  print: "Download summary (PDF)",
};

// ---------------------------------------------------------------- 8. Validation
export const validation = {
  title: "How we validated",
  question: "For the engineer who asks: what holds, and what doesn't yet.",
  methodTitle: "The method in five steps",
  method: [
    { title: "Baseline", body: "Learn each tag's normal range from April–May running data, with stops and bad data masked." },
    { title: "Index", body: "Combine 33 tags across 5 systems into one 0–100 index, where 0 is the April–May normal." },
    { title: "Periods", body: "Find stretches where the index stayed abnormally high and at least one system was off, outside ordinary events like restarts." },
    { title: "Score", body: "Blend how far, how broad and how long the deviation is into the Kiln Health Index. Normal / Watch / Warning cut-offs come from how your kiln ran in April–May (its 75th and 90th percentiles)." },
    { title: "Test", body: "Fix the test before looking at results, then check whether the index rose ahead of each abnormal period." },
  ],
  resultTitle: "The result, stated straight",
  result: "On June–August data, the index did not reliably rise before the abnormal periods.",
  resultDetail: (pe: string, lo: string, hi: string, p: string) => `The median rise in the hour before was ${pe} percentile points (95% range ${lo} to ${hi}; p = ${p}). That is too small and too uncertain to call an early warning.`,
  chance: (a: string, b: string) => `Shifted and shuffled versions of the same test produce rises this size too (p = ${a} and ${b}), so we do not claim it.`,
  whyTitle: "Why",
  why: [
    (c: number, n: number) => `${c} of ${n} periods began drifting before the window we could look back over, so their true start is unknown.`,
    () => "The periods whose start could be timed precisely show no rise at all beforehand.",
    () => "There are no plant event logs, so there is nothing to confirm what a real event looks like.",
    () => "Results shift when the kiln-inlet O₂ analyser is left out, so its readings need checking.",
  ],
  fixTitle: "What fixes it",
  fix: (n: number) => `At least ${n} recorded events (coating, ring, cleaning or stoppage) from your logs that the test can use. We then re-run the same frozen test, unchanged, so the answer cannot be tuned.`,
  trustTitle: "Why you can trust what we do claim",
  trust: {
    leakage: { title: "Tested against hindsight", body: "The scoring stages give identical answers when the data after each cut-off is removed or scrambled." },
    future: { title: "No peeking at the future", body: "Scrambling everything after each period start leaves every earlier number identical." },
    repro: { title: "Reproducible", body: "Re-running any stage gives exactly the same numbers." },
    checks: { title: "Checked at every stage", body: (n: string) => `${n} automated validation checks pass across the pipeline.` },
  },
  techTitle: "Technical reference",
  tech: (v: Record<string, string>) => [
    `Index version ${v.index}, reference window ${v.reference}`,
    `Period finder version ${v.periods}`,
    "Data export: dashboard/scripts/export_data.py → dashboard/public/data/*.json (each file lists its sources)",
    "Full stage reports: reports/BUILD_STATUS.md",
  ],
};
