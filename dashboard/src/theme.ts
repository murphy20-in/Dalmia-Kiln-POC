// Design tokens: the single source of colour, gradient, elevation, motion and font for Tailwind
// (tailwind.config.ts imports this file, and index.css reads it through theme()) and for ECharts.
// Plain TS only: no React imports here. Rule: no hex or rgba literal anywhere else in src/
// (tests/tokens.test.ts enforces it). Logo SVGs under src/assets/brand keep their own artwork colours.
//
// Hierarchy of use: ~70% navy / white / cool grey, ~20% blue / indigo / slate, ~10% Dalmia accents.

/** Dark structure and blues. night…fog are the supplied reference palette (2E4265, 8599AB, A8B5C2, D5D5D6, 8FA3BC). */
export const brand = {
  night: "#091226",   // deepest: top bar, hero base, footer
  midnight: "#0f1d3b", // sidebar, console deck, tooltip
  steel: "#2e4265",   // reference mid navy: borders and raised panels on dark
  slate: "#8599ab",
  haze: "#8fa3bc",
  mist: "#a8b5c2",    // body text on dark (8:1 on midnight)
  fog: "#d5d5d6",
  // Blues
  navy: "#2a469c",     // links, actions, active icons
  navyDeep: "#233d8e", // action hover
  navyInk: "#14244b",  // headings and numbers on light
  navyTint: "#edf1f8",
  navyLine: "#d5dcef",
  indigo: "#4863b8",   // secondary data blue on light
  sky: "#79aef0",      // accent on dark: active rule, focus on dark, glow
  skySoft: "#b5d0f7",  // eyebrow text on dark
  // Text on light
  heading: "#1c2540",
  ink: "#414142",
  muted: "#5b6472",    // 5.9:1 on white, 5.2:1 on the canvas
  faint: "#8a8f98",    // decorative icons only, never text
  // Lines and fills
  line: "#dfe4ec",
  lineStrong: "#c9d1de",
  grid: "#e9edf3",
  heatLow: "#f1f4fb",
  white: "#ffffff",
  clear: "rgba(0,0,0,0)",
  hoverFill: "rgba(42,70,156,0.05)",
  periodFill: "rgba(20,36,75,0.07)",
  periodEdge: "rgba(20,36,75,0.28)",
  gapFill: "rgba(133,153,171,0.18)",
  zoomFill: "rgba(42,70,156,0.10)",
};

/** Dalmia Bharat logo accents. Marks, rules and annotations only: never a Health Index state, never body text on white. */
export const dalmia = {
  blue: "#0054a6",
  green: "#00923f",
  orange: "#f39500",
  grey: "#959c98",
};

/** Semantic names for the background layers (canvas → surface → dark). */
export const background = {
  canvas: "#eef1f6",
  navy: brand.night,
  hero: brand.midnight,
  surface: brand.white,
  surfaceElevated: brand.white,
  subtle: "#f5f7fb",
  overlay: "rgba(9,18,38,0.55)",
};

/** Gradients stay subtle: a cool lift in one corner, never a colour splash. */
export const gradient = {
  hero: `radial-gradient(900px 440px at 84% -12%, rgba(121,174,240,0.26), transparent 62%), radial-gradient(760px 420px at 6% 118%, rgba(46,66,101,0.70), transparent 66%), linear-gradient(180deg, ${brand.night} 0%, ${brand.midnight} 100%)`,
  sidebar: `linear-gradient(180deg, ${brand.midnight} 0%, ${brand.night} 100%)`,
  surface: `linear-gradient(180deg, ${brand.white} 0%, #f8f9fd 100%)`,
  accent: `linear-gradient(180deg, ${brand.sky} 0%, ${brand.navy} 100%)`,
  canvas: `linear-gradient(180deg, #e3e9f2 0, ${background.canvas} 420px)`,
};

export type Zone = "N" | "W" | "A";

// Status colours are reserved for Health Index states and always ship with the word.
export const status = {
  N: { fill: "#1f8a70", ink: "#177058", band: "rgba(31,138,112,0.07)" },
  W: { fill: "#d99a00", ink: "#8a6100", band: "rgba(217,154,0,0.09)" },
  A: { fill: "#c4511a", ink: "#b04515", band: "rgba(196,81,26,0.08)" },
  C: { fill: "#8a8f98", ink: "#5f6368", band: "rgba(138,143,152,0.10)" },
} as const;

// Fixed categorical order for the five process systems (never cycled, never status hues).
export const systemColor: Record<string, string> = {
  EFFICIENCY: "#2f62d6",
  COMBUSTION: "#0e95b0",
  THERMAL: "#8a5fd0",
  DRAFT_PRESSURE: "#6f8a1f",
  STABILITY: "#d4579b",
  BREADTH_PERSISTENCE: "#8f97a4",
};

// Magnitude, not alarm: period severity and data-issue severity use a navy → slate ramp, never the status palette.
export const severityColor: Record<string, string> = { HIGH: brand.navyInk, MODERATE: "#4a67c0", LOW: "#a9b8e6" };
export const issueColor: Record<string, string> = { critical: brand.navyInk, high: brand.navy, medium: "#6f86cf", low: "#a9b8e6", info: "#cdd6ef" };

/** Elevation: 1 px border first, then a soft shadow. Nothing heavier than `drawer`. */
export const elevation = {
  card: "0 1px 2px rgba(16,24,40,.04)",
  raised: "0 2px 4px rgba(16,24,40,.06), 0 10px 28px rgba(16,24,40,.09)",
  drawer: "-12px 0 40px rgba(9,18,38,.28)",
  glow: "0 0 14px rgba(121,174,240,.45)",
  dark: "0 8px 30px rgba(9,18,38,.35)",
};

/** Durations in ms. 120 hover/press, 180 page and panel, 240 drawer. Honour prefers-reduced-motion (index.css). */
export const motion = { fast: 120, normal: 180, slow: 240, ease: "cubic-bezier(.2,.8,.2,1)" };

/** Two families only: Inter for UI and numbers, JetBrains Mono for eyebrows and technical metadata. */
export const font = {
  sans: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
};

/** Chart environment: navy-slate axes, muted grid, one blue primary, slate comparison, orange for annotation only. */
export const chart = {
  axis: "#51607a",
  axisLine: brand.lineStrong,
  grid: brand.grid,
  primary: "#2c5bc4",
  compare: "#6d819c",
  annotation: dalmia.orange,
  annotationInk: "#9a5a00",
  pointer: brand.slate,
  tooltip: {
    bg: brand.midnight, border: "rgba(143,163,188,0.38)", title: brand.white, text: brand.mist, rule: "rgba(168,181,194,0.22)",
    shadow: "0 10px 30px rgba(9,18,38,.40)",
  },
};

const axisLabel = { color: chart.axis, fontSize: 12 };

export const echartsTheme = {
  color: [chart.primary, systemColor.COMBUSTION, systemColor.THERMAL, systemColor.DRAFT_PRESSURE, systemColor.STABILITY],
  backgroundColor: "transparent",
  textStyle: { fontFamily: font.sans, color: chart.axis, fontSize: 12 },
  categoryAxis: {
    axisLine: { lineStyle: { color: chart.axisLine } },
    axisTick: { show: false },
    axisLabel,
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel,
    splitLine: { lineStyle: { color: chart.grid } },
    nameTextStyle: { color: chart.axis, fontSize: 11 },
  },
  timeAxis: {
    axisLine: { lineStyle: { color: chart.axisLine } },
    axisTick: { show: false },
    axisLabel,
    splitLine: { show: false },
  },
  // Dark navy tooltip shell; the content comes from charts/tooltip.ts.
  tooltip: {
    backgroundColor: chart.tooltip.bg,
    borderColor: chart.tooltip.border,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: chart.tooltip.text, fontSize: 12, fontFamily: font.sans },
    extraCssText: `box-shadow: ${chart.tooltip.shadow}; border-radius: 8px; min-width: 176px;`,
  },
};
