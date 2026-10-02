import type { Config } from "tailwindcss";
import { colors, dalmia, elevation, font, gradient, motion, semantic, status, track } from "./src/theme";

// Design tokens: see DESIGN_SYSTEM.md. Everything comes from src/theme.ts so CSS and ECharts never drift.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // The green scale (theme.ts → colors)
        abyss: colors.abyss, forest: colors.deepForest, brunswick: colors.brunswick, moss: colors.moss, eucalyptus: colors.eucalyptus,
        sage: colors.sage, lichen: colors.lichen, polar: colors.polar, mist: colors.mist,
        emerald: { DEFAULT: colors.emerald, deep: colors.emeraldDeep, ink: colors.emeraldInk },
        slate: semantic.gap,
        dalmia: { blue: dalmia.blue, green: dalmia.green, orange: dalmia.orange, grey: dalmia.grey },
        // Semantic roles (theme.ts → semantic)
        ink: { DEFAULT: semantic.textPrimary, body: semantic.textBody, muted: semantic.textMuted, faint: semantic.textFaint },
        page: semantic.pageBackground,
        subtle: semantic.surfaceSoft,
        line: { DEFAULT: semantic.border, strong: semantic.borderStrong },
        normal: { DEFAULT: status.N.fill, ink: status.N.ink },
        watch: { DEFAULT: status.W.fill, ink: status.W.ink },
        warning: { DEFAULT: status.A.fill, ink: status.A.ink },
        critical: status.C.fill,
        // Replay timeline states, tuned for the dark deck
        track: { normal: track.N, watch: track.W, warning: track.A, gap: track.gap, high: track.high, other: track.other },
      },
      fontFamily: { sans: font.sans.split(", "), mono: font.mono.split(", ") },
      // One type scale for every page: [size, { lineHeight, letterSpacing }].
      fontSize: {
        eyebrow: ["11px", { lineHeight: "16px", letterSpacing: "0.14em" }],
        caption: ["12px", { lineHeight: "16px" }],
        label: ["13px", { lineHeight: "18px" }],
        body: ["15px", { lineHeight: "23px" }],
        card: ["16px", { lineHeight: "22px", letterSpacing: "-0.005em" }],
        section: ["18px", { lineHeight: "25px", letterSpacing: "-0.01em" }],
        lead: ["22px", { lineHeight: "30px", letterSpacing: "-0.015em" }],
        title: ["28px", { lineHeight: "34px", letterSpacing: "-0.022em" }],
        display: ["34px", { lineHeight: "40px", letterSpacing: "-0.025em" }],
        hero: ["46px", { lineHeight: "50px", letterSpacing: "-0.032em" }],
        masthead: ["68px", { lineHeight: "64px", letterSpacing: "-0.045em" }], // the product name on the Executive Summary
        kpi: ["38px", { lineHeight: "42px", letterSpacing: "-0.03em" }],
        numeral: ["56px", { lineHeight: "56px", letterSpacing: "-0.04em" }],
      },
      borderRadius: { card: "10px", panel: "8px", shell: "18px" },
      boxShadow: { card: elevation.card, raised: elevation.raised, drawer: elevation.drawer, glow: elevation.glow, dark: elevation.dark, inset: elevation.inset, well: elevation.well },
      backgroundImage: { hero: gradient.hero, header: gradient.header, sidebar: gradient.sidebar, deck: gradient.deck, track: gradient.track, surface: gradient.surface, accent: gradient.accent, rule: gradient.rule, canvas: gradient.canvas },
      transitionDuration: { DEFAULT: `${motion.normal}ms`, fast: `${motion.fast}ms`, normal: `${motion.normal}ms`, slow: `${motion.slow}ms` },
      transitionTimingFunction: { DEFAULT: motion.ease },
      maxWidth: { page: "1280px", prose: "68ch" },
    },
  },
} satisfies Config;
