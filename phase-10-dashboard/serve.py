"""Phase 10 dashboard server: static files + same-origin proxy to the frozen Phase 9 API.

The browser never talks to Phase 9 directly, so Phase 9 CORS stays closed and Phase 9 code stays unchanged.
Upstream is fixed (DALMIA_KILN_API_UPSTREAM, default http://127.0.0.1:8009). No other host can be requested.

    ../.venv/bin/python serve.py
"""
from __future__ import annotations

import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PUBLIC = Path(__file__).resolve().parent / "public"
UPSTREAM = os.environ.get("DALMIA_KILN_API_UPSTREAM", "http://127.0.0.1:8009").rstrip("/")
HOST = os.environ.get("DALMIA_KILN_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DALMIA_KILN_DASHBOARD_PORT", "8010"))
PAGES = {"/", "/history", "/abnormal-periods", "/events", "/validation", "/data-quality", "/methodology"}
PROXY_PREFIXES = ("/api/", "/health", "/ready")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".webp": "image/webp"}
HOP = {"host", "content-length", "connection", "transfer-encoding", "keep-alive"}


def _safe_file(url_path: str) -> Path | None:
    rel = url_path.lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    path = (PUBLIC / rel).resolve()
    if path != PUBLIC and PUBLIC not in path.parents:
        return None
    return path if path.is_file() else None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if args and str(args[1]).startswith("5"):
            super().log_message(fmt, *args)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PATCH(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def _handle(self):
        path = self.path.split("?", 1)[0]
        if path.startswith(PROXY_PREFIXES) or path in ("/health", "/ready"):
            self._proxy()
            return
        if path in PAGES:
            self._file(PUBLIC / "index.html")
            return
        target = _safe_file(path)
        if target is None:
            self.send_error(404)
            return
        self._file(target)

    def _file(self, path: Path):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 16384:
            self._json(413, '{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request body is too large."}}')
            return
        body = self.rfile.read(length) if length else None
        url = UPSTREAM + self.path
        headers = {}
        if self.headers.get("Content-Type"):
            headers["Content-Type"] = self.headers["Content-Type"]
        if self.headers.get("X-Actor"):
            headers["X-Actor"] = self.headers["X-Actor"]
        req = Request(url, data=body, headers=headers, method=self.command)
        try:
            with urlopen(req, timeout=120) as resp:
                payload, status, reason, hdrs = resp.read(), resp.status, resp.reason, resp.headers
        except HTTPError as e:
            payload, status, reason, hdrs = e.read(), e.code, e.reason, e.headers
        except URLError:
            self._json(503, '{"error":{"code":"ANALYTICAL_SERVICE_UNAVAILABLE",'
                            '"message":"Analytical service unavailable"}}')
            return
        self.send_response(status, reason)
        for key in ("Content-Type", "Allow", "X-Request-ID"):
            if hdrs.get(key):
                self.send_header(key, hdrs[key])
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, text: str):
        raw = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"dashboard http://{HOST}:{PORT}  upstream {UPSTREAM}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
