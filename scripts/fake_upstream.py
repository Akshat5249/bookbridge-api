"""Local-only fixture server with controlled failures; never imported by the app."""

import argparse
import json
import re
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

SITE = Path(__file__).resolve().parents[1] / "tests/fixtures/site"
DETAIL = re.compile(r"/catalogue/[a-z0-9][a-z0-9-]*_\d+/index\.html$")


class FixtureServer(ThreadingHTTPServer):
    """Thread-safe failure controls and request-start counters."""

    daemon_threads = True

    def __init__(self, port: int, root: Path = SITE) -> None:
        self.root = root.resolve()
        self.mode: dict[str, str] = {"mode": "normal", "scope": "all"}
        self.hits: Counter[str] = Counter()
        self.lock = threading.Lock()
        super().__init__(("127.0.0.1", port), FixtureHandler)


class FixtureHandler(BaseHTTPRequestHandler):
    """Serve GET-only static fixtures and local evaluator controls."""

    server: FixtureServer

    def log_message(self, format: str, *args: object) -> None:
        """Keep standalone evaluator output concise."""

    def _send(
        self, status: int, content: bytes, content_type: str = "text/html; charset=utf-8"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if status == 429:
            self.send_header("Retry-After", "60")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Expected when the evaluator deliberately times out.

    def _json(self, payload: object, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:
        """Switch test modes, read counters, or serve confined fixture files."""
        parts = urlsplit(self.path)
        params = {k: v[-1] for k, v in parse_qs(parts.query).items()}
        if parts.path == "/__control":
            if params.get("mode", "normal") not in {
                "normal",
                "status",
                "delay",
                "garbage",
            } or params.get("scope", "all") not in {"all", "detail"}:
                self._json({"error": "invalid mode"}, 400)
                return
            try:
                code = int(params.get("code", "500"))
                delay = float(params.get("delay", "0"))
                if not 100 <= code <= 599 or not 0 <= delay <= 5:
                    raise ValueError()
            except ValueError:
                self._json({"error": "invalid code or delay"}, 400)
                return
            with self.server.lock:
                self.server.mode = params
            self._json({"mode": params})
            return
        if parts.path == "/__stats":
            with self.server.lock:
                if params.get("reset") == "1":
                    self.server.hits.clear()
                payload = {
                    kind: self.server.hits[kind] for kind in ("home", "category", "detail", "other")
                }
            self._json(payload)
            return
        path = unquote(parts.path)
        kind = (
            "detail"
            if DETAIL.fullmatch(path)
            else (
                "category"
                if "/category/" in path
                else ("home" if path in {"/", "/index.html"} else "other")
            )
        )
        with self.server.lock:
            self.server.hits[kind] += 1
            mode = self.server.mode.copy()
        if mode.get("scope", "all") == "all" or kind == "detail":
            if mode.get("delay") or mode.get("mode") == "delay":
                time.sleep(float(mode.get("delay", "3")))
            if mode.get("mode") == "status":
                self._send(int(mode.get("code", "500")), b"Controlled failure")
                return
            if mode.get("garbage") == "1" or mode.get("mode") == "garbage":
                self._send(200, b"<html><h1>Maintenance</h1></html>")
                return
        target = (self.server.root / path.lstrip("/")).resolve()
        if not target.is_relative_to(self.server.root):
            self._send(404, b"Not found")
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send(404, b"Not found")
            return
        self._send(
            200,
            target.read_bytes(),
            "text/plain" if target.suffix == ".txt" else "text/html; charset=utf-8",
        )


def main() -> None:
    """Run only on loopback; Ctrl-C terminates the fixture server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with FixtureServer(args.port) as server:
        print(f"Fixture upstream: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
