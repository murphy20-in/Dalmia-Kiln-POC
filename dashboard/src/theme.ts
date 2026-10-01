// Design tokens: the single source of colour for Tailwind (tailwind.config.ts imports this file)
// and ECharts. Brand values sampled from dalmiacement.com; status and system palettes validated
// with the dataviz palette validator (see REVIEW_LOG.md). Plain TS only: no React imports here.
export const brand = {
  navy: "#2a469c",
  navyDeep: "#233d8e",
  navyInk: "#1b2c63",
  navyTint: "#eef1f8",
  cyan: "#00a8ce",
  cyanInk: "#00728c",
  ink: "#414142",
  muted: "#5f6368",
  faint: "#8a8f98",
  line: "#e3e6ec",
  lineStrong: "#cfd5df",
  grid: "#eef0f4",
  page: "#f4f6f9",
  heatLow: "#f1f4fb",
  navyLine: "#d5dcef",
  cyanSoft: "#7fd6ec",
  heading: "#2b2f36",
  hoverFill: "rgba(42,70,156,0.05)",
  periodFill: "rgba(27,44,99,0.08)",
  periodEdge: "rgba(27,44,99,0.25)",
  gapFill: "rgba(138,143,152,0.16)",
  zoomFill: "rgba(42,70,156,0.10)",
  card: "#ffffff",
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

// Magnitude, not alarm: period severity and data-issue severity use a navy ramp, never the status palette.
export const severityColor: Record<string, string> = { HIGH: "#1b2c63", MODERATE: "#4a67c0", LOW: "#a9b8e6" };
export const issueColor: Record<string, string> = { critical: "#1b2c63", high: "#2a469c", medium: "#6f86cf", low: "#a9b8e6", info: "#cdd6ef" };

const axisLabel = { color: brand.muted, fontSize: 12 };

export const echartsTheme = {
  color: [brand.navy, systemColor.COMBUSTION, systemColor.THERMAL, systemColor.DRAFT_PRESSURE, systemColor.STABILITY],
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: brand.muted, fontSize: 12 },
  categoryAxis: {
    axisLine: { lineStyle: { color: brand.lineStrong } },
    axisTick: { show: false },
    axisLabel,
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel,
    splitLine: { lineStyle: { color: brand.grid } },
    nameTextStyle: { color: brand.muted, fontSize: 11 },
  },
  timeAxis: {
    axisLine: { lineStyle: { color: brand.lineStrong } },
    axisTick: { show: false },
    axisLabel,
    splitLine: { show: false },
  },
  // Product-UI tooltip shell; the content comes from charts/tooltip.ts.
  tooltip: {
    backgroundColor: "#ffffff",
    borderColor: brand.lineStrong,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: brand.ink, fontSize: 12, fontFamily: "Inter, system-ui, sans-serif" },
    extraCssText: "box-shadow: 0 2px 4px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.10); border-radius: 8px; min-width: 168px;",
  },
};
