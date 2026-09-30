# Dashboard architecture (v2)

v2 rebuilds the page layer of the Phase 10 dashboard. The stack is unchanged: plain HTML, CSS and ES modules, served by stdlib `serve.py`, with inline SVG charts, no build step and no runtime dependency. Phase 9 has no static file serving and its route table is frozen, so Phase 10 does not edit Phase 9.

## Modes

| Mode | Detected by | Data | Writes |
|---|---|---|---|
| Local | any host except `*.github.io` | `serve.py` proxies `/api`, `/health` and `/ready` to Phase 9 on `127.0.0.1:8009` | annotation create / edit / withdraw |
| Hosted (GitHub Pages) | `location.hostname` ends in `github.io` | `public/snapshot/*.json` via `snapshot.js` | refused (405); write buttons are disabled and show the reason |

Hosted mode uses hash routes (`/Dalmia-Kiln-POC/#/history?from=…`), because Pages cannot rewrite paths. `404.html` turns a deep path into the hash form. An inline script in `index.html` sets `<base>` (`/` locally, `/Dalmia-Kiln-POC/` on Pages), so relative assets load from nested routes such as `/abnormal-periods/P6-020`.

## Routes and deep links

| Route | Page | URL state |
|---|---|---|
| `/` | Overview | – |
| `/history` | Historical score | `from`, `to`, `period`, `overlay=o2_excluded` |
| `/abnormal-periods`, `/abnormal-periods/P6-xxx` | Periods list, then the detail panel | – |
| `/events`, `/events/new`, `/events/<uuid>`, `/events/<uuid>/edit` | Annotations | `/new` takes `start`, `end`, `ref` |
| `/validation` | Validation | anchors `#primary`, `#o2`, `#censoring`, `#controls`, `#F1`…`#F20` |
| `/data-quality` | Data quality | anchors `#L01`…`#L13`, `#<dataset>-<yyyy-mm>` |
| `/methodology` | Methodology | anchors `#score`, `#periods`, `#validation`, `#o2`, `#annotations`, `#data` |

`pure/route.js` parses and builds every URL, in both modes. `app.js` intercepts same-origin link clicks, uses `pushState`, and re-renders on `popstate`. After rendering, it scrolls to and focuses the anchor target, or the page `h1` if there is no anchor. URL state survives reload and back/forward. `serve.py` returns `index.html` for every route pattern above.

## Data flow

```
api.js ──(hosted)──> snapshot.js ──> snapshot/*.json
   │
   └─(local)──> /api/v1/* (serve.py proxy) ──> Phase 9
        │
pages/*.js ── pure/present.js (enum → plain English, served-row counts)
        │   └─ copy.js (all client-authored words)
        ├─ ui.js (hero, KPI card, insight, advisory, next steps, action bar, table toggle, toast)
        └─ chart.js (trend + bands + gaps + diamonds + drag-to-zoom, timeline, bars, dot-and-CI)
```

There is one fetch layer and no state library. Each render gets an `AbortController`, so navigating cancels in-flight requests.

**Score series:** charts read `/risk-scores/variant-comparison`. Its rows are `{timestamp, primary_empirical_risk_score, o2_excluded_empirical_risk_score}`, about 0.6 MB per 5,000 rows. `/risk-scores` rows carry full components, about 14 MB per 5,000. The primary value is the same served primary score. The O₂ column is drawn only when the sensitivity overlay is on. Gaps come from `data_extent.gaps_in_page` and are never interpolated.

## Endpoints per page

| Page | Endpoints |
|---|---|
| Overview | `metadata/status`, `abnormal-periods`, `risk-scores?limit=1` (extent and total), `findings`, `metadata/limitations`, `metadata/data-requirements`, `validation/early-warning-historical`, then `variant-comparison` (trend strip) |
| History | `variant-comparison`, `abnormal-periods`, `events`, `findings`, `metadata/limitations`, `metadata/data-requirements` |
| Abnormal periods | `abnormal-periods`, `validation/…` (censoring), `findings`, `metadata/limitations`, `metadata/data-requirements` |
| Events | `events`, `events/{id}`, `events/{id}/audit`, POST / PATCH / DELETE `events`, `metadata/status`, `abnormal-periods`, `findings`, `metadata/limitations`, `metadata/data-requirements` |
| Validation | `validation/early-warning-historical`, `findings`, `metadata/limitations`, `metadata/data-requirements` |
| Data quality | `metadata/limitations`, `metadata`, `metadata/methodology`, `metadata/data-requirements`, `risk-scores?limit=1`, `metadata/provenance` |
| Methodology | `metadata/methodology`, `metadata`, `findings`, `metadata/limitations`, `metadata/data-requirements` |

## Writes

Plant annotations go to `POST` / `PATCH` / `DELETE /api/v1/events`. `X-Actor` is sent as attribution only, not authentication. `expected_version` is sent on update and withdraw. A 409 reloads the record instead of overwriting it. The `ref=P6-xxx` on `/events/new` is shown as context only and is never stored: Phase 9 computes the period overlap on read.

## Rules the code enforces

- Counting served rows is allowed. The client computes no statistic (`tests/honesty.test.mjs`).
- API text is inserted as text nodes only (`dom.js` ignores `innerHTML`).
- `evidenceForDisplay` removes withheld figures (AUC, lead time, coverage). The five F3 warning-rule findings appear as one grouped row with no rule names.
- The O₂ overlay is off by default, drawn dashed in grey, and labelled "Sensitivity analysis — not preferred".
- Score bands and severity never use brand colour, red or amber. Severity is encoded by pattern, weight and a text label.

## v1 modules

| Module | v2 |
|---|---|
| `api.js`, `snapshot.js`, `dom.js`, `pure/series.js`, `pure/query.js`, `pure/form.js` | reused (`api.js` gains a plain message for the 503 artifact mismatch) |
| `pure/present.js` | extended (plain-English presenters, row counts) |
| `chart.js` | extended (clickable bands and diamonds, drag-to-zoom, timeline, bars, dot-and-CI) |
| `ui.js`, `app.js`, `index.html`, `css/app.css` | rewritten |
| `pages/*.js` | rewritten to the hero → KPI → graph → insights → advisory → next steps → actions rhythm |
| `state.js` | reduced to the actor name; the score window now lives in the URL |
| `copy.js`, `pure/route.js` | new |
