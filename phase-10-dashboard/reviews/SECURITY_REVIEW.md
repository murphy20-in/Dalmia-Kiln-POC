# Security review

Checked against the Phase 10 event path and the dashboard server.

| Check | Result |
|---|---|
| Description `<script>alert(1)</script><img src=x onerror=alert(1)>` | Rendered as a text node. Page script count stayed 1. Image count stayed 0 |
| `innerHTML` assignment | Absent. `dom.js` ignores an `innerHTML` property |
| Query parameters | Built with `encodeURIComponent`. Unknown API parameters are rejected by Phase 9 |
| `X-Actor` | Labelled attribution, not authentication. Header is forwarded only to the fixed upstream |
| CORS | No `Access-Control-Allow-Origin` added. Browser talks only to the dashboard origin |
| Proxy | Upstream host is the env default `127.0.0.1:8009`. Paths outside `/api`, `/health`, `/ready` are not proxied |
| Static files | `..` is rejected. Files must stay under `public/` |
| Error text | Traceback, home path, sqlite, and parquet mentions are replaced before display |
| Secrets | None in the frontend |

The local event store now contains one soft-deleted test annotation from this review. It is gitignored plant data.
