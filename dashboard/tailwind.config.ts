import type { Config } from "tailwindcss";
import { background, brand, dalmia, elevation, font, gradient, motion, status } from "./src/theme";

// Design tokens: see DESIGN_SYSTEM.md. Everything comes from src/theme.ts so CSS and ECharts never drift.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: brand.navy, deep: brand.navyDeep, ink: brand.navyInk, tint: brand.navyTint, line: brand.navyLine },
        night: brand.night, midnight: brand.midnight, steel: brand.steel,
        slate: brand.slate, haze: brand.haze, mist: brand.mist, fog: brand.fog,
        indigo: brand.indigo,
        sky: { DEFAULT: brand.sky, soft: brand.skySoft },
        dalmia: { blue: dalmia.blue, green: dalmia.green, orange: dalmia.orange, grey: dalmia.grey },
        ink: { DEFAULT: brand.heading, body: brand.ink, muted: brand.muted, faint: brand.faint },
        page: background.canvas,
        subtle: background.subtle,
        line: { DEFAULT: brand.line, strong: brand.lineStrong },
        normal: { DEFAULT: status.N.fill, ink: status.N.ink },
        watch: { DEFAULT: status.W.fill, ink: status.W.ink },
        warning: { DEFAULT: status.A.fill, ink: status.A.ink },
        critical: status.C.fill,
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
        kpi: ["38px", { lineHeight: "42px", letterSpacing: "-0.03em" }],
        numeral: ["56px", { lineHeight: "56px", letterSpacing: "-0.04em" }],
      },
      borderRadius: { card: "10px", panel: "8px" },
      boxShadow: { card: elevation.card, raised: elevation.raised, drawer: elevation.drawer, glow: elevation.glow, dark: elevation.dark },
      backgroundImage: { hero: gradient.hero, sidebar: gradient.sidebar, surface: gradient.surface, accent: gradient.accent, canvas: gradient.canvas },
      transitionDuration: { DEFAULT: `${motion.normal}ms`, fast: `${motion.fast}ms`, normal: `${motion.normal}ms`, slow: `${motion.slow}ms` },
      transitionTimingFunction: { DEFAULT: motion.ease },
      maxWidth: { page: "1280px", prose: "68ch" },
    },
  },
} satisfies Config;
