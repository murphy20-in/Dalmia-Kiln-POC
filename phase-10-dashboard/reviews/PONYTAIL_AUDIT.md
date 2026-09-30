# Ponytail audit (v2)

| Item | Finding |
|---|---|
| Second analytical server | Not added. One stdlib process serves `public/` and proxies Phase 9 |
| Chart library, npm | Not added. Charts are inline SVG. Tests use `node --test`. The capture script drives the system Chrome over CDP with Node's built-in WebSocket |
| Score formula or statistics in JS | Not present. `tests/honesty.test.mjs` checks for them |
| New database, Phase 9 edits | None |
| Dead exports | Removed: `GAP_SECONDS`, `logClientError`, `stepItem`, `dom.js` `clear`/`text`, `setQuery`, and the `loadSeries(range)` branch |
| Duplicated copy | Client wording lives in `copy.js`. A test ties the static shell's disclaimer and banner text to it |
| Capture tooling | One script, `tests/e2e/capture.mjs`, for screenshots, rendered-text fixtures and the hosted-mode check. It replaced the Playwright-MCP snippet |
| Alarm colours | None. There is no red, amber or orange, and the stylesheet is checked by test |

No critical or high finding is left open (`REVIEW_LOG.md` §7).

Ceiling: a long score window is thinned to about 900 points for drawing. The table and slider state how many points are plotted. Upgrade path: plot every point when a window has to be inspected bucket by bucket.
