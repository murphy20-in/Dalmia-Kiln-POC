# Dashboard architecture

Phase 9 has no static file serving, and its route table is frozen by `tests/test_contract.py`. Phase 10 therefore does not edit Phase 9.

```text
Browser
  → phase-10-dashboard/serve.py (stdlib HTTP)
       → public/           HTML, CSS, JS
       → proxy /api /health /ready
            → Phase 9 on 127.0.0.1:8009
                 → frozen artifacts and the plant annotation store
```

Routes are real paths. `serve.py` returns `index.html` for the seven pages. `public/js/app.js` reads `location.pathname` and calls one page module. There is no routing library.

The date window is stored in `sessionStorage` and mirrored on the query string (`start`, `end`). An invalid window is dropped, not applied.

Each page fetch uses `AbortController` so leaving the page cancels the request. Score windows are loaded with the API `limit`/`offset` parameters (max 12,000 rows). The browser never receives the raw historian extract.

Chart drawing (`public/js/chart.js`) only places API points. Gaps are breaks. Visual thinning keeps existing points; it does not average them.

Plant events go to `POST`/`PATCH`/`DELETE /api/v1/events`. `X-Actor` is sent as attribution. `expected_version` is sent on update and delete. HTTP 409 reloads the event instead of overwriting it.
