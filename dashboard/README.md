# Kiln Intelligence dashboard (pitch build)

A static, eight-page product demo for Dalmia Cement, Ariyalur: Executive Summary, Kiln Health Console (historical replay), Efficiency Story, Abnormal Periods, Alternative Fuel, Data Readiness, Roadmap & Value, and How we validated.

Stack: Vite + React 18 + TypeScript, Tailwind CSS 3, Apache ECharts (`echarts/core`), HashRouter. There is no backend. The browser only formats, filters and draws the JSON in `public/data/`.

## Run

```bash
cd dashboard
npm install
npm run dev          # http://localhost:5173/
```

Presentation mode: press `P` or open `/?present=1#/`. Use ← → to step through the pages in pitch order, and `Esc` to exit.

## Regenerate the data

`scripts/export_data.py` reads the frozen Phase 1–9 outputs (read-only) and writes `public/data/*.json`. Each file carries a `_sources` map from field to repo path. Output is deterministic: two runs are byte-identical.

```bash
cd dashboard && npm run data     # = ../.venv/bin/python -B dashboard/scripts/export_data.py
```

## Test and build

```bash
npm test             # vitest: data contract, wording scan, value model
npm run typecheck
npm run build        # dist/, base "./" (works from any sub-path)
npm run preview      # serve dist/ locally
```

`tests/wording.test.ts` fails on overclaiming or internal wording (for example "predict", "forecast", "lead time", "accuracy", tag IDs, phase numbers). Present-time monitoring words are allowed only in the Console ribbon and the Roadmap's future stages.

## Deploy

`.github/workflows/pages.yml` builds `dashboard/` and publishes `dist/` to GitHub Pages on push to `pitch-dashboard` or `main`. It needs the repo's Pages source set to "GitHub Actions".

## Layout

```
scripts/export_data.py   frozen outputs → public/data/*.json
src/copy.ts              every user-facing string
src/data.ts              typed loaders for each JSON file
src/theme.ts             tokens, status and system palettes, ECharts theme
src/lib/                 format.ts (dates, ₹), value.ts (ROI model)
src/components/          Shell, ui blocks, ChartCard, StatusGauge, Drawer
src/charts/              Chart wrapper + option builders (zone line, bars, Gantt, heatmap)
src/pages/               one file per page
tests/                   vitest suites
```
