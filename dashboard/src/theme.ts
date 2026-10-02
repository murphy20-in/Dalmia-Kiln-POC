// Design tokens: the single source of colour, gradient, elevation, motion and font for Tailwind
// (tailwind.config.ts imports this file, and index.css reads it through theme()) and for ECharts.
// Plain TS only: no React imports here. Rule: no hex or rgba literal anywhere else in src/
// (tests/tokens.test.ts enforces it). Logo SVGs under src/assets/brand keep their own artwork colours.
//
// Hierarchy of use:
//   Deep Forest / Brunswick  → structure and authority (shell, hero, dark decks, headings)
//   Emerald                  → attention and interaction (active, selected, key metric, primary series)
//   Eucalyptus / Moss / Sage → secondary analytical layers (comparison, baseline, reference, borders on dark)
//   Polar / Lichen           → breathing room and readable content (cards, canvas)

/**
 * The green scale. Brunswick, Emerald and Polar are the canonical brand palette (0C4137, 06D6A0, E6FBF6).
 * The tonal greens come from the second reference by its RGB values (its printed HEX values conflict):
 * Deep Forest 15·47·36, Moss Shadow 31·77·58, Eucalyptus 79·143·117, Sage Mist 159·195·178, Pale Lichen 231·241·236.
 * Every green has one job; there are no other greens in the UI.
 */
export const colors = {
  abyss: "#08201a",       // the darkest step of the Deep Forest family: gradient anchors and dark edges only, never a flat fill
  deepForest: "#0f2f24",  // deepest surface: top bar, hero base, tooltip, footer
  brunswick: "#0c4137",   // brand green: sidebar, dark decks, strong borders, actions on light
  moss: "#1f4d3a",        // raised panels and borders on dark; action hover; chart baseline
  eucalyptus: "#4f8f75",  // secondary data series, "Normal" on dark tracks
  sage: "#9fc3b2",        // reference lines, tertiary text on dark (6:1 on Brunswick)
  lichen: "#e7f1ec",      // page canvas
  emerald: "#06d6a0",     // accent on dark: active, selected, focus, key metric (6:1 on Brunswick); never text on light
  polar: "#e6fbf6",       // light panels and tints
  mist: "#c5ddd2",        // secondary text on dark (8:1 on Brunswick): a Sage→Polar blend
  emeraldDeep: "#0b9f7a", // Emerald for graphics on light surfaces (3.3:1 on white); the primary chart series
  emeraldInk: "#0a6b50",  // Emerald for text on light surfaces (6:1 on white): ticks, "delivered"
};

/** Dalmia Bharat logo accents. Marks, rules and annotations only: never a Health Index state, never body text on white. */
export const dalmia = {
  blue: "#0054a6",
  green: "#00923f",
  orange: "#f39500",
  grey: "#959c98",
};

/** Semantic roles, so components say what a colour is for rather than which green it is. */
export const semantic = {
  pageBackground: colors.lichen,
  surface: "#ffffff",
  surfaceRaised: "#ffffff",
  surfaceSoft: "#f3f9f6",   // insets inside a card
  surfaceStrong: colors.polar,
  textPrimary: colors.deepForest, // headings and numbers on light
  textBody: "#2b3d35",
  textSecondary: "#34463f",
  textMuted: "#566b62",     // 5.7:1 on white, 5.0:1 on the canvas
  textFaint: "#8aa095",     // decorative icons only, never text
  border: "#d9e6df",
  borderStrong: "#bcd0c5",
  grid: "#e5eee9",
  accent: colors.emerald,
  selected: colors.emerald,
  normal: colors.emeraldDeep,
  watch: "#c28700",         // 3.1:1 on white (graphics); labels on it are Deep Forest (4.65:1)
  warning: "#c4511a",
  gap: "#7f8d96",           // neutral slate: missing data is never a process colour
  white: "#ffffff",
  clear: "rgba(0,0,0,0)",
  // Fills used by charts
  heatLow: "#eef7f3",
  hoverFill: "rgba(12,65,55,0.06)",
  periodFill: "rgba(15,47,36,0.07)",
  periodEdge: "rgba(15,47,36,0.30)",
  gapFill: "rgba(127,141,150,0.18)",
  zoomFill: "rgba(11,159,122,0.14)",
  overlay: "rgba(15,47,36,0.60)",
};

/**
 * Gradients stay few and purposeful: depth, hierarchy, focus. Never decoration on every card.
 *
 * All of them travel the same ladder — Abyss → Deep Forest → Brunswick → an Emerald light — and all of them
 * are radial first: a flat linear wash reads as a recoloured template, radial light reads as atmosphere.
 * Strength is a hierarchy, not a default: hero and header strongest, deck and sidebar medium, canvas a whisper,
 * ordinary cards none at all. Emerald is the light source (≤ 0.34 alpha, always off-centre), never a paint layer.
 */
export const gradient = {
  /** 1. Hero bands: an Emerald sun off the top-right, a low Emerald pool bottom-left, and dark Abyss corners. */
  hero: `radial-gradient(1120px 560px at 79% -26%, rgba(6,214,160,0.34), transparent 60%), radial-gradient(780px 460px at 3% 124%, rgba(6,214,160,0.15), transparent 62%), radial-gradient(900px 420px at 48% 56%, rgba(31,77,58,0.55), transparent 72%), radial-gradient(560px 240px at 44% -10%, rgba(230,251,246,0.07), transparent 70%), linear-gradient(135deg, ${colors.abyss} 0%, ${colors.deepForest} 36%, ${colors.brunswick} 74%, ${colors.abyss} 100%)`,
  /** Header: the Emerald light sits directly behind the product name, so the title emerges out of the atmosphere. */
  header: `radial-gradient(660px 240px at 24% 58%, rgba(6,214,160,0.30), transparent 72%), radial-gradient(420px 190px at 1% -30%, rgba(6,214,160,0.10), transparent 70%), radial-gradient(540px 220px at 99% 128%, rgba(31,77,58,0.92), transparent 72%), linear-gradient(100deg, ${colors.abyss} 0%, ${colors.deepForest} 44%, ${colors.brunswick} 100%)`,
  /** 1. Brunswick → Deep Forest → Abyss, vertical, with a low Emerald glow at the foot: the sidebar. */
  sidebar: `radial-gradient(300px 380px at 0% 100%, rgba(6,214,160,0.17), transparent 70%), linear-gradient(180deg, ${colors.brunswick} 0%, ${colors.deepForest} 60%, ${colors.abyss} 100%)`,
  /** 4. The console deck: lit from the top-right corner and, softly, from behind the timeline it contains. */
  deck: `radial-gradient(780px 340px at 93% -30%, rgba(6,214,160,0.30), transparent 62%), radial-gradient(940px 320px at 44% 60%, rgba(6,214,160,0.13), transparent 68%), radial-gradient(620px 420px at 1% 112%, rgba(6,214,160,0.08), transparent 66%), linear-gradient(158deg, ${colors.brunswick} 0%, ${colors.deepForest} 52%, ${colors.abyss} 100%)`,
  /** 4b. The timeline well, recessed into the deck: Abyss floor with one Emerald light rising from under the track. */
  track: `radial-gradient(520px 150px at 50% 128%, rgba(6,214,160,0.18), transparent 72%), linear-gradient(180deg, ${colors.abyss} 0%, ${colors.deepForest} 100%)`,
  /** 2. Brunswick → Emerald: accent rules and the active-state bar. */
  accent: `linear-gradient(180deg, ${colors.emerald} 0%, ${colors.brunswick} 100%)`,
  /** 3. Emerald → translucent Brunswick: a fading rule under hero eyebrows. */
  rule: `linear-gradient(90deg, ${colors.emerald} 0%, rgba(12,65,55,0) 100%)`,
  /** 5. The light canvas, lit from the dark band above it: a green descent that is gone by the first card row. */
  canvas: `radial-gradient(1200px 620px at 88% -150px, rgba(6,214,160,0.22), transparent 60%), radial-gradient(1000px 560px at -8% 10%, rgba(12,65,55,0.16), transparent 62%), linear-gradient(180deg, rgba(12,65,55,0.20) 0, rgba(231,241,236,0) 720px)`,
  surface: `linear-gradient(180deg, #ffffff 0%, #f7fbf9 100%)`,
};

export type Zone = "N" | "W" | "A";

// Status colours are reserved for Health Index states and always ship with the word. They describe
// historical analytical states, not an alarm system. Missing data (C / gap) is neutral grey.
export const status = {
  N: { fill: "#087f62", ink: colors.emeraldInk, band: "rgba(6,214,160,0.09)" },
  W: { fill: semantic.watch, ink: "#8a6100", band: "rgba(217,154,0,0.10)" },
  A: { fill: semantic.warning, ink: "#b04515", band: "rgba(196,81,26,0.08)" },
  C: { fill: "#8a8f98", ink: "#5f6368", band: "rgba(138,143,152,0.10)" },
} as const;

/** The replay timeline sits on a dark deck, so its state fills are tuned for dark: Normal is a restrained
 *  Eucalyptus (the Emerald selection marker must stay brighter than any state), Watch muted amber,
 *  Warning a deeper warm tone, Gap a neutral slate. */
export const track = {
  N: colors.eucalyptus,
  W: "#d9a21b",
  A: "#d8642b",
  gap: semantic.gap,
  high: dalmia.orange,
  other: colors.sage,
};

// Fixed categorical order for the five process systems (never cycled, never status hues). Greens are
// kept for brand and Normal; the systems use cool/violet/rose and one eucalyptus so they stay tellable apart.
export const systemColor: Record<string, string> = {
  EFFICIENCY: "#1d6f8c",
  COMBUSTION: "#7b61a8",
  THERMAL: "#a64f77",
  DRAFT_PRESSURE: "#6b7a2e",
  STABILITY: "#5f6f7a",
  BREADTH_PERSISTENCE: "#9aa8a0",
};
/** Text colour that stays readable on a system's fill (white on the darker ones, ink on the light ones). */
export const systemLabel: Record<string, string> = {
  EFFICIENCY: semantic.white, COMBUSTION: semantic.white, THERMAL: semantic.white,
  DRAFT_PRESSURE: semantic.white, STABILITY: semantic.white, BREADTH_PERSISTENCE: colors.deepForest,
};

// Magnitude, not alarm: period severity and data-issue severity use a Deep Forest → Sage ramp, never the status palette.
export const severityColor: Record<string, string> = { HIGH: colors.deepForest, MODERATE: "#3f7f68", LOW: colors.sage };
export const issueColor: Record<string, string> = { critical: colors.deepForest, high: colors.brunswick, medium: "#3f7f68", low: colors.sage, info: "#cfe3d9" };

/** Elevation: 1 px border first, then a soft shadow. Nothing heavier than `drawer`. */
export const elevation = {
  card: "0 1px 2px rgba(15,47,36,.05)",
  raised: "0 2px 4px rgba(15,47,36,.06), 0 10px 28px rgba(15,47,36,.10)",
  drawer: "-12px 0 40px rgba(15,47,36,.30)",
  glow: "0 0 14px rgba(6,214,160,.45)",
  dark: "0 8px 30px rgba(15,47,36,.35)",
  /** The timeline well, cut into the deck: a lit top edge, then depth falling away from it. */
  inset: "inset 0 1px 0 rgba(197,221,210,.12), inset 0 12px 28px rgba(8,32,26,.55), inset 0 0 34px rgba(6,214,160,.05)",
  /** The track itself, recessed one step further than the well around it. */
  well: "inset 0 1px 0 rgba(197,221,210,.09), inset 0 2px 10px rgba(8,32,26,.70)",
};

/** Durations in ms. 120 hover/press, 180 page and panel, 240 drawer. Honour prefers-reduced-motion (index.css). */
export const motion = { fast: 120, normal: 180, slow: 240, ease: "cubic-bezier(.2,.8,.2,1)" };

/** Two families only: Inter for UI and numbers, JetBrains Mono for eyebrows and technical metadata. */
export const font = {
  sans: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
};

/** Chart environment: green-grey axes, whisper grid, Emerald primary, Moss comparison, orange for annotation only. */
export const chart = {
  axis: "#4b6158",
  axisLine: semantic.borderStrong,
  grid: semantic.grid,
  primary: colors.emeraldDeep,
  compare: colors.moss,
  reference: colors.sage,
  annotation: dalmia.orange,
  annotationInk: "#9a5a00",
  pointer: colors.eucalyptus,
  tooltip: {
    bg: colors.deepForest, border: "rgba(159,195,178,0.38)", title: semantic.white, text: colors.mist, rule: "rgba(159,195,178,0.24)",
    shadow: "0 10px 30px rgba(15,47,36,.40)",
  },
};

const axisLabel = { color: chart.axis, fontSize: 12 };

export const echartsTheme = {
  color: [chart.primary, systemColor.EFFICIENCY, systemColor.COMBUSTION, systemColor.THERMAL, systemColor.STABILITY],
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
  // Dark Deep Forest tooltip shell; the content comes from charts/tooltip.ts.
  tooltip: {
    backgroundColor: chart.tooltip.bg,
    borderColor: chart.tooltip.border,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: chart.tooltip.text, fontSize: 12, fontFamily: font.sans },
    extraCssText: `box-shadow: ${chart.tooltip.shadow}; border-radius: 8px; min-width: 176px;`,
  },
};
