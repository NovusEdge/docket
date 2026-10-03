"""The localhost server behind `docket graph --web`.

Routes are a fixed table, so no part of a URL is ever joined onto a
filesystem path.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent
ASSETS = {"/": "index.html", "/viz-global.js": "vendor/viz-global.js"}
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8"}


def make_server(payload: Callable[[], bytes], port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            bound = self.server.server_address[1]
            # A page on another origin can rebind its own hostname to
            # 127.0.0.1; the Host header is what still names that origin.
            if self.headers.get("Host") not in (f"127.0.0.1:{bound}", f"localhost:{bound}"):
                self._send(403, b"forbidden", "text/plain")
                return
            path = self.path.split("?", 1)[0]
            if path == "/api/graph":
                self._graph()
            elif path in ASSETS:
                file = WEB_ROOT / ASSETS[path]
                cache = "max-age=86400" if path != "/" else "no-cache"
                self._send(200, file.read_bytes(), _TYPES[file.suffix], cache)
            else:
                self._send(404, b"not found", "text/plain")

        def _graph(self) -> None:
            try:
                body = payload()
            except Exception as exc:
                print(f"docket: web: {exc}", file=sys.stderr)
                self._send(500, f"docket: {exc}".encode(), "text/plain")
                return
            etag = '"' + hashlib.sha256(body).hexdigest()[:16] + '"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            self._send(200, body, "application/json", "no-cache", etag)

        def _send(self, status, body, ctype, cache="no-cache", etag=None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            if etag:
                self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args) -> None:
            pass

        def log_error(self, format, *args) -> None:
            print("docket: web: " + format % args, file=sys.stderr)

    try:
        return ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        return ThreadingHTTPServer(("127.0.0.1", 0), Handler)
