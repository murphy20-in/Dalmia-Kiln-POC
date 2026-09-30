// Design tokens. Brand values sampled from dalmiacement.com; status and system palettes
// validated with the dataviz palette validator (see REVIEW_LOG.md).
export const brand = {
  navy: "#2a469c",
  navyDeep: "#233d8e",
  navyInk: "#1b2c63",
  cyan: "#00a8ce",
  ink: "#414142",
  muted: "#5f6368",
  faint: "#8a8f98",
  line: "#e3e6ec",
  page: "#f5f6f8",
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

// Severity uses a navy ramp (magnitude), never the status palette.
export const severityColor: Record<string, string> = { HIGH: "#1b2c63", MODERATE: "#4a67c0", LOW: "#a9b8e6" };

export const echartsTheme = {
  color: [brand.navy, systemColor.COMBUSTION, systemColor.THERMAL, systemColor.DRAFT_PRESSURE, systemColor.STABILITY],
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: brand.muted, fontSize: 12 },
  categoryAxis: {
    axisLine: { lineStyle: { color: brand.line } },
    axisTick: { show: false },
    axisLabel: { color: brand.muted },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: brand.muted },
    splitLine: { lineStyle: { color: "#eef0f4" } },
    nameTextStyle: { color: brand.muted, fontSize: 11 },
  },
  timeAxis: {
    axisLine: { lineStyle: { color: brand.line } },
    axisTick: { show: false },
    axisLabel: { color: brand.muted },
    splitLine: { show: false },
  },
  tooltip: {
    backgroundColor: "#ffffff",
    borderColor: brand.line,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: brand.ink, fontSize: 12 },
    extraCssText: "box-shadow: 0 4px 16px rgba(20,30,60,.12); border-radius: 8px;",
  },
};
