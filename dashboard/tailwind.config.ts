import type { Config } from "tailwindcss";
import { brand, status } from "./src/theme";

// Design tokens: see DESIGN_SYSTEM.md. Colours come from src/theme.ts so CSS and ECharts never drift.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: brand.navy, deep: brand.navyDeep, ink: brand.navyInk, tint: brand.navyTint, line: brand.navyLine },
        cyan: { DEFAULT: brand.cyan, soft: brand.cyanSoft, ink: brand.cyanInk },
        ink: { DEFAULT: brand.heading, body: brand.ink, muted: brand.muted, faint: brand.faint },
        page: brand.page,
        line: { DEFAULT: brand.line, strong: brand.lineStrong },
        normal: { DEFAULT: status.N.fill, ink: status.N.ink },
        watch: { DEFAULT: status.W.fill, ink: status.W.ink },
        warning: { DEFAULT: status.A.fill, ink: status.A.ink },
        critical: status.C.fill,
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      // One type scale for every page: [size, { lineHeight, letterSpacing }].
      fontSize: {
        caption: ["12px", { lineHeight: "16px" }],
        label: ["13px", { lineHeight: "18px" }],
        body: ["15px", { lineHeight: "23px" }],
        card: ["16px", { lineHeight: "22px", letterSpacing: "-0.005em" }],
        section: ["18px", { lineHeight: "25px", letterSpacing: "-0.01em" }],
        lead: ["22px", { lineHeight: "30px", letterSpacing: "-0.015em" }],
        title: ["26px", { lineHeight: "32px", letterSpacing: "-0.02em" }],
        display: ["34px", { lineHeight: "40px", letterSpacing: "-0.025em" }],
        kpi: ["36px", { lineHeight: "40px", letterSpacing: "-0.03em" }],
      },
      borderRadius: { card: "10px", panel: "8px" },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04)",
        raised: "0 2px 4px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.08)",
        drawer: "-12px 0 40px rgba(16,24,40,.18)",
      },
      transitionDuration: { DEFAULT: "160ms" },
      maxWidth: { page: "1280px", prose: "68ch" },
    },
  },
} satisfies Config;
