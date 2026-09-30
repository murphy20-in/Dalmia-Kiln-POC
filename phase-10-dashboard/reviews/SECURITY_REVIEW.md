# Security review (v2)

The `security-reviewer` found no HIGH issues, 1 MEDIUM and 5 LOW. All eight required checks pass. The findings are listed in `REVIEW_LOG.md` §3 (S1–S6) and the Python review in §6.

| Check | Result |
|---|---|
| Plant text | Rendered as text nodes only. There is no `innerHTML`, `insertAdjacentHTML` or `document.write`. `h()` and chart `el()` drop string `on*` values and refuse `javascript:`, `data:` and `vbscript:` URLs |
| `X-Actor` | Attribution, not authentication. It is validated on the client and by Phase 9, and forwarded only to the fixed upstream |
| DNS rebinding | A Host outside `127.0.0.1:8010` or `localhost:8010` gets 421. A write whose `Origin` is not allowed gets 403 |
| Proxy | Only `/api/…` plus exact `/health` and `/ready` are proxied, to `127.0.0.1:8009`. A malformed `Content-Length` gets 400, over 16 KB gets 413, and the connection is closed |
| Headers | CSP with the inline script's sha256, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `nosniff`. The pages render with no CSP violation |
| CORS | No `Access-Control-*` header is sent |
| Static files | `..` is rejected, the resolved path must stay under `public/`, and a NUL byte gets 404 |
| Clipboard | Plain text only |
| Snapshot | No secrets or absolute paths. Test annotations (`e2e.journey`, `poc.analyst`) are excluded by `export_snapshot.py` |
| GitHub Pages | Writes are refused with 405 and the controls are `aria-disabled` with their reason. No `<meta>` CSP (accepted, S3) |

The local, gitignored event store holds withdrawn test annotations from the browser journeys. None of them reaches the snapshot.
