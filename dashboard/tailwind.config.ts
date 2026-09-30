import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#2a469c", deep: "#233d8e", ink: "#1b2c63", tint: "#eef1f8" },
        cyan: { DEFAULT: "#00a8ce", soft: "#7fd6ec" },
        ink: { DEFAULT: "#414142", muted: "#5f6368", faint: "#8a8f98" },
        page: "#f5f6f8",
        line: "#e3e6ec",
        normal: { DEFAULT: "#1f8a70", ink: "#177058" },
        watch: { DEFAULT: "#d99a00", ink: "#8a6100" },
        warning: { DEFAULT: "#c4511a", ink: "#b04515" },
        critical: "#8a8f98",
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      borderRadius: { card: "12px" },
      boxShadow: { card: "0 1px 2px rgba(20,30,60,.06), 0 4px 16px rgba(20,30,60,.06)" },
      maxWidth: { page: "1280px" },
    },
  },
} satisfies Config;
