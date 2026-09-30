/** Every client-authored word in the dashboard. Served text (findings, limitations, requirements) is not here;
 *  it is shown as served. tests/honesty.test.mjs scans this file. */

export const BRAND = { mark: "DALMIA CEMENT", product: "Kiln Analytical POC", site: "Ariyalur kiln" };

export const DISCLAIMER = {
  strong: "Retrospective, not an early warning.",
  text: "Historical analysis of Jun–Aug 2025 only. It does not show live data, raise alarms or detect deposits, rings or coating.",
};

export const READ_ONLY = {
  banner: "Read-only hosted copy. It shows exported analysis results and cannot save plant annotations.",
  reason: "Read-only hosted copy — annotate on the local service",
};

export const PERIOD_LABEL = "KPI-derived abnormal periods (not plant events)";
export const PERIOD_ONE = "KPI-derived abnormal period (not a plant event)";

export const NAV = [
  ["/", "Overview"],
  ["/history", "Score history"],
  ["/abnormal-periods", "Abnormal periods"],
  ["/events", "Plant annotations"],
  ["/validation", "Validation"],
  ["/data-quality", "Data quality"],
  ["/methodology", "Methodology"],
];

/** Served enums -> [plain text, optional one-line meaning]. The raw value stays in a tooltip. */
export const PLAIN = {
  status: {
    NOT_SUPPORTED: ["Not supported", "The score was not shown to rise before the abnormal periods"],
    WEAK: ["Weak", "Suggestive, not decision-grade: passed only a looser test (p < 0.10 or interval above zero)"],
    SUPPORTED: ["Supported", "Met the Phase 8 rule for this narrow check only"],
    INSUFFICIENT_DATA: ["Insufficient data", "Too few periods to decide"],
    BLOCKED: ["Blocked", "Cannot be tested until plant event records exist"],
    NOT_AVAILABLE: ["Not available", "No plant event records exist yet"],
    SENSITIVITY_ANALYSIS: ["Sensitivity analysis", "Not preferred and never a substitute for the primary score"],
  },
  severity: { HIGH: ["High severity"], MODERATE: ["Moderate severity"], LOW: ["Low severity"] },
  confidence: { MEDIUM: ["Medium confidence (the highest possible without plant records)"], LOW: ["Low confidence"] },
  load: {
    LOAD_ASSOCIATED: ["Load-associated"],
    UNCERTAIN: ["Load association uncertain"],
    NOT_LOAD_ASSOCIATED: ["Not load-associated"],
  },
  family: {
    EFFICIENCY: ["Efficiency"],
    COMBUSTION: ["Combustion"],
    THERMAL: ["Thermal"],
    STABILITY: ["Stability"],
    DRAFT_PRESSURE: ["Draft and pressure"],
  },
  limitation: { OPEN: ["Open"], MASKED_UPSTREAM: ["Handled in data cleaning"], INFO: ["For information"] },
  limitationTopic: {
    EVENT_GROUND_TRUTH: ["No plant event ground truth"],
    MISSING_MONTH_KILN_I_SEPTEMBER: ["Kiln-I September 2025 missing"],
    KILN_IIIA_APRIL_DUPLICATION: ["Kiln-IIIA April 2025 duplicated"],
    FROZEN_WINDOW: ["Frozen (unchanging) sensor window"],
    SENTINEL_VALUES: ["Sentinel placeholder values"],
    UNIT_REVIEW_HOLDS: ["Units awaiting review"],
    O2_ANALYSER_KILN_I_X: ["Kiln-I!X O₂ analyser"],
    LOAD_DEPENDENCE: ["Score depends on load"],
    OPERATING_STATE_PROXY: ["Operating state is inferred"],
    REFERENCE_DEPENDENCE: ["Results depend on the reference period"],
    CENSORED_ONSETS: ["Capped period start times"],
    TIMEZONE: ["No timezone on timestamps"],
    HIGH_BAND_NOT_RARE: ["The high band is common"],
  },
  preference: { NEITHER_PREFERRED_UNTIL_PLANT_EXPLAINS_KILN_I_X: ["Neither variant is preferred until the plant explains the Kiln-I!X analyser readings"] },
  label: { KPI_DERIVED_EMPIRICAL_ABNORMAL_PERIOD: ["KPI-derived label"], PLANT_SUPPLIED_ANNOTATION: ["Plant-supplied"] },
  band: { VERY_HIGH: ["Very high"] },
  eventStatus: { ACTIVE: ["Active"], DELETED: ["Withdrawn"] },
  context: { NONE: ["None recorded"] },
};

export const PAGE = {
  overview: {
    title: "Kiln analytical overview",
    answer: "Retrospective analysis of Jun–Aug 2025. The risk score was not shown to rise before the 12 KPI-derived abnormal periods; plant event logs are needed to go further.",
    method: "score",
  },
  history: {
    title: "Score history",
    answer: "The empirical POC risk score for each operational ten-minute bucket, 1 Jun – 23 Aug 2025. It is a historical reading relative to Apr–May, not a limit.",
    method: "score",
  },
  periods: {
    title: "KPI-derived abnormal periods",
    answer: "Stretches where the POC efficiency KPI was at or above the 90th percentile of its reference period. They are analytical labels, not plant events, and most coincide with load changes.",
    method: "periods",
  },
  events: {
    title: "Plant annotations",
    answer: "Plant-supplied records of what happened in the kiln, placed on the timeline. With plant logs, they are what this analysis needs to be revalidated.",
    method: "annotations",
  },
  validation: {
    title: "Validation",
    answer: "Early-warning validation: not supported. Phase 8 did not show the score rising before the abnormal periods. The O₂-excluded check is weak and analyser-dependent, and neither variant is preferred.",
    method: "validation",
  },
  quality: {
    title: "Data quality",
    answer: "Some dataset-months are missing; missing data is shown as a gap and never filled in, and several plant questions remain open.",
    method: "data",
  },
  methodology: {
    title: "Methodology",
    answer: "How the frozen phases fit together. This dashboard reads served results and recalculates none of them.",
    method: "score",
  },
};

export const SECTION = {
  kpis: "Key figures",
  insights: "What the evidence shows",
  advisory: "How to read this",
  steps: "Recommended next steps — data and review",
  actions: "Actions",
  method: "Methodology",
};

/** Insight sources per page: F<n> = /findings row, L<nn> = /metadata/limitations row. */
export const INSIGHTS = {
  overview: ["F1", "F18", "F5", "F6", "L01"],
  history: ["L08", "L13", "L10", "F5"],
  periods: ["L11", "F1", "L10", "F4"],
  events: ["L01", "F15", "L12"],
  validation: ["F1", "F7", "F11", "F18", "F5"],
  quality: ["L02", "L03", "L07", "L06", "L09"],
  methodology: ["F9", "L10", "L08"],
};

/** Advisory items: a heading here, the text from the served field named by `from`. */
export const ADVISORY = {
  reference: { title: "The score is reference-relative", from: "L10" },
  load: { title: "The score is higher at low feed", from: "L08" },
  censoring: { title: "Many period start times are capped", from: "censoring" },
  o2: { title: "The O₂ analyser may be reading ambient air", from: "L07" },
  truth: { title: "There is no plant ground truth", from: "L01" },
  highband: { title: "The high band is common, not rare", from: "L13" },
  timezone: { title: "Times have no timezone", from: "L12" },
};

export const ADVICE = {
  overview: ["reference", "load", "censoring", "o2", "truth"],
  history: ["reference", "load", "highband", "o2"],
  periods: ["reference", "censoring", "load"],
  events: ["truth", "timezone"],
  validation: ["censoring", "o2", "truth"],
  quality: ["o2", "timezone", "reference"],
  methodology: ["reference", "truth"],
};

/** Next steps per page. req:<i> = plant_data_requirements[i], q:<i> = plant_questions_open[i],
 *  annotate:<severity> = the first served period of that KPI severity class, revalidation = served threshold. */
export const STEPS = {
  overview: ["req:0", "req:1", "annotate:HIGH", "revalidation"],
  history: ["req:2", "q:0", "annotate:HIGH"],
  periods: ["annotate:HIGH", "req:4", "req:3"],
  events: ["revalidation", "req:0", "q:3"],
  validation: ["revalidation", "req:1", "q:1"],
  quality: ["req:8", "q:0", "q:4", "q:3"],
  methodology: ["q:1", "req:3"],
};

export const STEP_TEXT = {
  annotate: (id, when) => `Annotate what happened around period ${id} (${when})`,
  revalidation: (n) => `Record at least ${n} evaluable plant annotations so the frozen Phase 8 protocol can be re-run`,
  unblocks: (what) => `Needed to review: ${what}`,
  question: "Open plant question",
  copy: "Copy request",
  start: "Start annotation",
  add: "Add an annotation",
  copied: "Request copied as plain text.",
  copyFailed: "Copy was blocked by the browser. Select the request text and copy it by hand.",
};

export function requestText(item) {
  return [
    "Data request — Dalmia Cement, Ariyalur kiln analytical POC",
    `Please supply: ${item.data}.`,
    item.unblocks ? `Needed to review: ${item.unblocks}.` : "",
    "Context: retrospective analysis of Jun–Aug 2025. No process or operating change is requested.",
  ].filter(Boolean).join("\n");
}

export function questionText(question) {
  return [
    "Plant question — Dalmia Cement, Ariyalur kiln analytical POC",
    question,
    "Context: retrospective analysis of Jun–Aug 2025. No process or operating change is requested.",
  ].join("\n");
}

export const CARD = {
  scored: { label: "Scored history", unit: "ten-minute buckets" },
  periods: { label: "KPI-derived abnormal periods", meaning: "Analytical labels from the efficiency KPI, not plant events" },
  validation: { label: "Early-warning validation" },
  o2: { label: "O₂-analyser sensitivity", value: "Weak", meaning: "Analyser-dependent; neither variant is preferred" },
  annotations: { label: "Plant annotations", meaning: (n) => `recorded · at least ${n} evaluable plant annotations are needed before Phase 8 can be re-run` },
  gaps: { label: "Data gaps and open questions", meaning: () => "missing dataset-months · open plant questions" },
};

export const ACTIONS = {
  overview: { primary: ["Add the first annotation", "/events/new", true], secondary: [["Review abnormal periods", "/abnormal-periods"], ["Why validation is not supported", "/validation", "primary"], ["Data gaps", "/data-quality"]] },
  history: { primary: ["Annotate a period", "/abnormal-periods", false], secondary: [["Why validation is not supported", "/validation", "primary"], ["Data gaps", "/data-quality"]] },
  periods: { primary: ["Add an annotation", "/events/new", true], secondary: [["See them on the score history", "/history"], ["Censored onsets", "/validation", "censoring"]] },
  events: { primary: ["Add an annotation", "/events/new", true], secondary: [["Abnormal periods to annotate", "/abnormal-periods"], ["Revalidation threshold", "/validation", "primary"]] },
  validation: { primary: ["Add an annotation", "/events/new", true], secondary: [["Compare variants", "/history", "", { overlay: "o2_excluded" }], ["Data gaps", "/data-quality"]] },
  quality: { primary: ["Add an annotation", "/events/new", true], secondary: [["Validation", "/validation"], ["Methodology", "/methodology", "data"]] },
  methodology: { primary: ["Review abnormal periods", "/abnormal-periods", false], secondary: [["Validation", "/validation"], ["Data quality", "/data-quality"]] },
};

export const MSG = {
  loading: "Loading the analysis…",
  loadingChart: "Loading the score series…",
  notFound: "That page does not exist. Showing the overview.",
  unavailable: "The analysis service is not responding (error 503). Try again shortly; if it continues, ask the analytics team to restart it.",
  mismatch: "The analysis service withheld its results because a stored file failed its integrity check (error 503). Nothing is shown rather than unverified numbers. Ask the analytics team to check the service.",
  failed: "This part of the page could not be loaded.",
  noAnnotations: "No plant annotations yet. Annotations are how this analysis can be revalidated.",
  addFirst: "Add the first annotation",
  withdrawConfirm: (type, when) => `Withdraw the ${type} annotation starting ${when}? It stays in the audit trail and can be read, but not edited.`,
  saved: "Annotation saved.",
  withdrawn: "Annotation withdrawn. The audit trail keeps it.",
  conflict: "Someone changed this annotation before your save. It has been reloaded; check it and save again.",
  actorHelp: "Your name or role is recorded with the change. It is attribution only, not a login.",
  fromPeriod: (id) => `Started from ${id}. That period is a KPI-derived label; describe what the plant records say happened, not the label.`,
  viewedScore: "Pre-set to yes because you came from the score analysis. Change it if that is wrong.",
  gapLegend: "Gap: no operational data (not a zero score)",
  weakCaveat: "Weak results at 2–6 h use the looser test and come from capped start times whose window already lies inside the KPI shift. They are not evidence that the score rose earlier (Phase 8 F2, F18).",
  cappedOnset: " — capped at the 6-hour look-back; the KPI shift had already begun and may have started earlier",
  cappedMeaning: "start time capped at 6 h before the period, so the score window already sits inside the KPI shift",
  o2Toggle: "O₂-excluded overlay — sensitivity analysis, not preferred",
  o2Note: "Dashed grey line: the score rebuilt without the Kiln-I!X O₂ analyser. It is a sensitivity analysis and does not replace the primary score. Neither variant is preferred until the plant explains the analyser readings.",
  brushHint: "Drag across the chart to zoom, or set the dates. Select a band to open that period.",
  tableToggle: "View as table",
  marksToggle: "List the periods and annotations in this chart",
  inspect: "Step through the plotted scores (arrow keys)",
  actorPrompt: "Your name or role, recorded with the withdrawal (attribution only, not a login):",
  confirmationHint: "How sure the plant is that this happened as described.",
  timeBasisHint: "Whether the start time was seen directly, estimated afterwards, or reported by someone else.",
  entryKindHint: "Written at the time it happened, or recorded later from memory or logs.",
};

export const TABLE_NOTE = {
  thinned: (shown, total) => `${shown} of ${total} plotted points (first 20 and last 5). Every value is served by the API; long ranges are thinned for drawing and gaps are never filled.`,
  all: "Every plotted point, as served by the API.",
};

export const METHOD = {
  flow: [
    ["Phase 3", "POC efficiency KPI from the historian export."],
    ["Phase 6", "KPI-derived abnormal periods."],
    ["Phase 7", "Empirical POC risk score, relative to the Apr–May reference."],
    ["Phase 8", "Historical validation of the score against those periods."],
    ["Phase 9", "Read-only API over the frozen results, plus the plant annotation store."],
    ["Phase 10", "This dashboard. It draws served results and recalculates nothing."],
  ],
  boundary: [
    "An empirical proof of concept",
    "not a validated plant-event detector",
    "does not anticipate plant events",
    "does not raise warnings or alarms",
    "not a source of process or set-point advice",
  ],
};

export const FINDINGS_NOTE = "Each finding keeps its own Phase 8 class. Classes are not added up or scored.";
export const F3_GROUP = {
  title: "Historical rule definitions (Phase 8 F3) were each tested against the abnormal periods",
  note: "Details are withheld under Phase 8 section 26. None of these rules is used in this dashboard.",
};
