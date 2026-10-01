# Kiln Intelligence dashboard (pitch build)

A static, eight-page product demo for Dalmia Cement, Ariyalur. The navigation is grouped:

- **Intelligence:** Executive Summary, Kiln Health Console (historical replay), Efficiency Story, Abnormal Periods, Alternative Fuel.
- **Evidence:** Data Readiness, How we validated.
- **Roadmap:** Roadmap & Value.

Everything shown is a historical analysis of June–August 2025 data. Nothing is connected to the plant.

Stack: Vite + React 18 + TypeScript, Tailwind CSS 3, Apache ECharts (`echarts/core`), HashRouter. There is no backend. The browser only formats, filters and draws the JSON in `public/data/`.

## Run

```bash
cd dashboard
npm install
npm run dev          # http://localhost:5173/
```

Presentation mode: press `Shift+P` or open `/?present=1#/`. Use ← → to step through the pages in pitch order, and `Esc` to exit.

## Design and review docs

- [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md): tokens, type scale, card hierarchy, components, chart and motion rules.
- [UI_UX_AUDIT.md](UI_UX_AUDIT.md): per-page scores (before → after), stakeholder read, gate results.
- [REVIEW_LOG.md](REVIEW_LOG.md): every review finding and its disposition.
- `screenshots/`: final 1280×720 captures of every page and the period drawer.

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
src/theme.ts             the only colour source (Tailwind imports it), status and system palettes, ECharts theme
src/lib/                 format.ts (dates, ₹), value.ts (ROI model)
src/components/          Shell, ui blocks (KpiTile, Badge, Lead, …), ChartCard, StatusGauge, Drawer
src/charts/              Chart wrapper, tooltip.ts (escaped tooltip layout), option builders (zone line, bars, Gantt, heatmap)
src/pages/               one file per page
tests/                   vitest suites
```
