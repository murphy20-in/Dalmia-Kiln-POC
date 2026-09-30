# Phase 10 — Analytical dashboard

Retrospective multi-page dashboard for the Ariyalur kiln POC. It reads the frozen Phase 9 API. It does not recompute scores, and it does not modify Phase 9.

## Run

Phase 9 must already be listening on `127.0.0.1:8009`.

```bash
cd phase-10-dashboard
../.venv/bin/python serve.py
```

Open `http://127.0.0.1:8010/`.

The hosted copy is `https://murphy20-in.github.io/Dalmia-Kiln-POC/`. It reads an export of the Phase 9 responses and does not save plant annotations. Regenerate that export with Phase 9 running: `../.venv/bin/python scripts/export_snapshot.py`.

`serve.py` serves `public/` and proxies `/api/`, `/health`, and `/ready` to Phase 9 (`DALMIA_KILN_API_UPSTREAM`). The browser stays same-origin. Phase 9 CORS is unchanged.

## Pages

`/`, `/history`, `/abnormal-periods`, `/events`, `/validation`, `/data-quality`, `/methodology`

## Tests

```bash
cd phase-10-dashboard
node --test tests/*.mjs
```

The contract test calls Phase 9 on port 8009.

## Stack

Plain HTML, CSS, and ES modules. Charts are SVG. No npm application dependency. See `docs/`.
