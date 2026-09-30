"""Phase 10 dashboard server: static files + same-origin proxy to the frozen Phase 9 API.

The browser never talks to Phase 9 directly, so Phase 9 CORS stays closed and Phase 9 code stays unchanged.
Upstream is fixed (DALMIA_KILN_API_UPSTREAM, default http://127.0.0.1:8009). No other host can be requested.

    ../.venv/bin/python serve.py
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PUBLIC = Path(__file__).resolve().parent / "public"
UPSTREAM = os.environ.get("DALMIA_KILN_API_UPSTREAM", "http://127.0.0.1:8009").rstrip("/")
HOST = os.environ.get("DALMIA_KILN_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DALMIA_KILN_DASHBOARD_PORT", "8010"))
PAGES = {"/", "/history", "/abnormal-periods", "/events", "/validation", "/data-quality", "/methodology"}
# Deep links the client router owns (public/js/pure/route.js).
DEEP = re.compile(r"/abnormal-periods/P6-\d{3}|/events/new|/events/[0-9a-f-]{36}(/edit)?", re.ASCII)
MAX_BODY = 16384
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".webp": "image/webp", ".json": "application/json"}
HOP = {"host", "content-length", "connection", "transfer-encoding", "keep-alive"}
# DNS rebinding: a hostile page that rebinds its name to this address is same-origin to the browser, so the Host
# header is the only thing that tells it apart.
ALLOWED_HOSTS = {f"{HOST}:{PORT}", f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS}


def _csp() -> str:
    """The shell's inline bootstrap script is allowed by hash, so script-src needs no 'unsafe-inline'."""
    html = (PUBLIC / "index.html").read_text(encoding="utf-8")
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'"
                      for s in re.findall(r"<script>(.*?)</script>", html, re.S))
    return (f"default-src 'self'; script-src 'self' {hashes}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")


CSP = _csp()


def _safe_file(url_path: str) -> Path | None:
    rel = url_path.lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    try:
        path = (PUBLIC / rel).resolve()
        if path != PUBLIC and PUBLIC not in path.parents:
            return None
        return path if path.is_file() else None
    except (ValueError, OSError):
        return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if len(args) < 2 or str(args[1]).startswith("5"):
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
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self.close_connection = True
            self._json(421, '{"error":{"code":"MISDIRECTED_REQUEST","message":"Unknown host."}}')
            return
        if self.command != "GET" and self.headers.get("Origin") not in (None, *ALLOWED_ORIGINS):
            self.close_connection = True
            self._json(403, '{"error":{"code":"FORBIDDEN_ORIGIN","message":"Writes are accepted from this dashboard only."}}')
            return
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/") or path in ("/health", "/ready"):
            self._proxy()
            return
        if path in PAGES or DEEP.fullmatch(path):
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
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self.close_connection = True  # the unread body must not be parsed as the next request
            if length > MAX_BODY:
                self._json(413, '{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request body is too large."}}')
            else:
                self._json(400, '{"error":{"code":"BAD_REQUEST","message":"Invalid Content-Length."}}')
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
        except ValueError:  # InvalidURL / UnicodeError: control or non-ASCII characters in the path or a header
            self.close_connection = True
            self._json(400, '{"error":{"code":"BAD_REQUEST","message":"Malformed request."}}')
            return
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
