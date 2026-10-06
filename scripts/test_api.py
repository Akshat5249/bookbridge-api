"""Standard-library evaluator for live API contracts and isolated upstream faults."""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
OPENER = build_opener(ProxyHandler({}))
PATHS = {
    "/health",
    "/api/v1/books",
    "/api/v1/books/{id}",
    "/api/v1/search",
    "/api/v1/categories",
    "/api/v1/categories/{slug}/books",
}
SUMMARY_FIELDS = {
    "id",
    "title",
    "price",
    "currency",
    "rating",
    "availability",
    "category",
    "image_url",
    "product_url",
}
DETAIL_FIELDS = SUMMARY_FIELDS | {"stock_count", "upc", "description"}


@dataclass
class Result:
    """One observable scenario outcome."""

    id: str
    name: str
    status: str
    duration_ms: int = 0
    expected: str = ""
    actual: str = ""


class Evaluator:
    """Run scenarios independently and retain readable failure evidence."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.base = args.base_url.rstrip("/")
        self.results: list[Result] = []
        self.actual = "No response"
        self.first: dict[str, Any] | None = None
        self.first_page: dict[str, Any] | None = None

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        timeout: float | None = None,
        base: str | None = None,
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        """Read JSON with a socket timeout, retaining status/body for failures."""
        request = Request(
            (base or self.base) + path,
            method=method,
            headers={"User-Agent": "BookBridgeEvaluator/1.0 (local contract tests)"},
        )
        try:
            response = OPENER.open(request, timeout=timeout or self.args.timeout)
        except HTTPError as error:
            response = error
        with response:
            content = response.read().decode("utf-8")
            status = response.code
            headers = {k.lower(): v for k, v in response.headers.items()}
        self.actual = f"HTTP {status}, body: {content[:600]}"
        payload = json.loads(content)
        require(isinstance(payload, dict), "JSON object")
        require(bool(headers.get("x-request-id")) or base is not None, "X-Request-ID header")
        return status, payload, headers

    def run(
        self,
        ident: str,
        name: str,
        expected: str,
        function: Callable[[], None],
        *,
        skip: bool = False,
    ) -> None:
        """Print PASS/FAIL/SKIP and preserve expected-vs-actual evidence."""
        if skip:
            result = Result(ident, name, "SKIP")
        else:
            started = time.monotonic()
            self.actual = "No response"
            try:
                function()
            except (
                AssertionError,
                ValueError,
                KeyError,
                TypeError,
                IndexError,
                OSError,
                URLError,
            ) as exc:
                result = Result(
                    ident,
                    name,
                    "FAIL",
                    int((time.monotonic() - started) * 1000),
                    expected,
                    f"{self.actual}; {exc}",
                )
            else:
                result = Result(ident, name, "PASS", int((time.monotonic() - started) * 1000))
        self.results.append(result)
        print(f"{result.status:4}  {ident} {name} ({result.duration_ms} ms)", flush=True)
        if result.status == "FAIL":
            print(f"      expected: {result.expected}\n      actual:   {result.actual}", flush=True)
        elif self.args.verbose and result.status == "PASS":
            print(f"      {self.actual}", flush=True)

    def ok(self, path: str, *, timeout: float | None = None) -> dict[str, Any]:
        """Require a successful JSON response."""
        status, payload, _ = self.request(path, timeout=timeout)
        require(status == 200, "HTTP 200")
        return payload

    def books(self, path: str = "/api/v1/books", *, timeout: float | None = None) -> dict[str, Any]:
        """Validate the complete list envelope and summary field types."""
        payload = self.ok(path, timeout=timeout)
        require(set(payload) == {"data", "pagination"}, "list envelope")
        require(isinstance(payload["data"], list), "data list")
        paging = payload["pagination"]
        require(set(paging) == {"page", "page_size", "total", "has_next"}, "pagination fields")
        require(
            all(type(paging[key]) is int for key in ("page", "page_size", "total")),
            "integer pagination",
        )
        require(type(paging["has_next"]) is bool, "boolean has_next")
        for book in payload["data"]:
            validate_book(book, detail=False)
        return payload

    def error(self, path: str, status: int, code: str, *, method: str = "GET") -> None:
        """Require the same envelope for validation, framework and upstream errors."""
        actual, payload, _ = self.request(path, method=method)
        require(actual == status, f"HTTP {status}")
        require(set(payload) == {"error"}, "error envelope")
        error = payload["error"]
        require(set(error) == {"code", "message", "details"}, "error fields")
        require(error["code"] == code and isinstance(error["message"], str), f"error.code={code}")
        if code == "VALIDATION_ERROR":
            require(
                isinstance(error["details"], list) and bool(error["details"]), "validation details"
            )
            for item in error["details"]:
                require(
                    set(item) == {"field", "message"}
                    and all(isinstance(v, str) for v in item.values()),
                    "field/message details",
                )
        else:
            require(error["details"] is None, "null details")

    def live(self) -> None:
        """Run L01-L18, H01, V01-V12 and N01-N05 in deterministic order."""
        self.run(
            "L01",
            "health returns status ok",
            "200 status=ok",
            lambda: require(self.ok("/health")["status"] == "ok", "status ok"),
        )
        self.run(
            "L02",
            "all six OpenAPI paths",
            "six documented paths",
            lambda: require(PATHS <= set(self.ok("/openapi.json")["paths"]), "all paths"),
        )

        def warmup() -> None:
            payload = self.books(timeout=self.args.warmup_timeout)
            require(
                len(payload["data"]) == 20
                and payload["pagination"]["total"] >= 20
                and payload["pagination"]["has_next"],
                "20 items and next page",
            )
            self.first_page, self.first = payload, payload["data"][0]

        self.run("L03", "books list and warmup", "20 summaries and pagination", warmup)
        self.run(
            "L04",
            "50-item page",
            "exactly 50 items",
            lambda: require(
                len(self.books("/api/v1/books?page_size=50")["data"]) == 50, "50 items"
            ),
        )

        def pages() -> None:
            first = self.first_page or self.books()
            second = self.books("/api/v1/books?page=2")
            require(
                not {b["id"] for b in first["data"]} & {b["id"] for b in second["data"]},
                "no overlap",
            )

        self.run("L05", "pages do not overlap", "disjoint IDs", pages)
        self.run(
            "L06",
            "exact rating filter",
            "all ratings 5",
            lambda: self.filtered("/api/v1/books?rating=5", lambda b: b["rating"] == 5),
        )
        self.run(
            "L07",
            "inclusive price range",
            "prices in [10,40]",
            lambda: self.filtered(
                "/api/v1/books?min_price=10&max_price=40", lambda b: 10 <= b["price"] <= 40
            ),
        )

        def inclusive() -> None:
            require(self.first is not None, "warmup record available")
            book = self.first
            payload = self.books(
                "/api/v1/books?"
                + urlencode(
                    {"min_price": book["price"], "max_price": book["price"], "page_size": 50}
                )
            )
            require(book["id"] in {b["id"] for b in payload["data"]}, "includes equal-price item")

        self.run("L08", "equal price bounds", "includes boundary record", inclusive)
        self.run(
            "L09",
            "combined AND filters",
            "rating 3 and price [10,60]",
            lambda: self.filtered(
                "/api/v1/books?rating=3&min_price=10&max_price=60",
                lambda b: b["rating"] == 3 and 10 <= b["price"] <= 60,
            ),
        )

        def detail() -> None:
            require(self.first is not None, "warmup record available")
            book = self.ok("/api/v1/books/" + self.first["id"])["data"]
            validate_book(book, detail=True)
            require(book["id"] == self.first["id"], "matching ID")

        self.run("L10", "full book detail", "typed detail schema and matching ID", detail)

        def golden() -> None:
            book = self.ok("/api/v1/books/a-light-in-the-attic_1000")["data"]
            validate_book(book, detail=True)
            expected = {
                "price": 51.77,
                "currency": "GBP",
                "rating": 3,
                "category": "Poetry",
                "upc": "a897fe39b1053632",
            }
            require(
                all(book[k] == v for k, v in expected.items()) and type(book["stock_count"]) is int,
                "golden fields",
            )

        self.run(
            "L11", "golden record", "documented golden fields", golden, skip=self.args.skip_golden
        )
        self.run(
            "L12",
            "title substring search",
            "nonempty light matches",
            lambda: self.filtered(
                "/api/v1/search?q=light", lambda b: "light" in b["title"].casefold()
            ),
        )

        def casefold() -> None:
            lower = self.books("/api/v1/search?q=light")
            upper = self.books("/api/v1/search?q=LIGHT")
            require(lower["pagination"]["total"] == upper["pagination"]["total"], "same total")

        self.run("L13", "case-insensitive search", "same totals", casefold)

        def empty() -> None:
            result = self.books("/api/v1/search?q=zzzxqjkw")
            require(
                result["data"] == []
                and result["pagination"]["total"] == 0
                and not result["pagination"]["has_next"],
                "empty search",
            )

        self.run("L14", "search with no match", "empty result total 0", empty)
        self.run(
            "L15",
            "search pagination",
            "one item on page 2",
            lambda: require(
                len(self.books("/api/v1/search?q=a&page_size=1&page=2")["data"]) == 1, "one item"
            ),
        )

        def categories() -> None:
            result = self.ok("/api/v1/categories")["data"]
            require(len(result) >= 40, "at least 40 categories")
            require(
                all(
                    set(c) == {"name", "slug"} and all(isinstance(v, str) for v in c.values())
                    for c in result
                ),
                "category schema",
            )
            slugs = {c["slug"] for c in result}
            require("poetry" in slugs and "books" not in slugs, "poetry but no top-level books")

        self.run("L16", "sidebar categories", "40 categories with poetry", categories)
        self.run(
            "L17",
            "category books",
            "nonempty Poetry results",
            lambda: self.filtered(
                "/api/v1/categories/poetry/books", lambda b: b["category"] == "Poetry"
            ),
        )
        self.run(
            "L18",
            "category page past end",
            "200 empty data",
            lambda: require(
                self.books("/api/v1/categories/poetry/books?page=999")["data"] == [], "empty page"
            ),
        )

        def header() -> None:
            _, _, headers = self.request("/health")
            require(bool(headers.get("x-request-id")), "request ID")

        self.run("H01", "request ID header", "X-Request-ID", header)
        validations = [
            "/api/v1/books?page=0",
            "/api/v1/books?page=-1",
            "/api/v1/books?page=abc",
            "/api/v1/books?page_size=0",
            "/api/v1/books?page_size=1000",
            "/api/v1/books?rating=0",
            "/api/v1/books?rating=6",
            "/api/v1/books?min_price=-1",
            "/api/v1/books?min_price=50&max_price=10",
            "/api/v1/search?q=",
            "/api/v1/search",
            "/api/v1/search?q=%20%20",
        ]
        for index, path in enumerate(validations, 1):
            self.run(
                f"V{index:02}",
                path,
                "422 VALIDATION_ERROR",
                lambda path=path: self.error(path, 422, "VALIDATION_ERROR"),
            )
        not_found = [
            "/api/v1/books/does-not-exist_0",
            "/api/v1/books/..%2f..%2fetc",
            "/api/v1/categories/no-such-category/books",
            "/api/v1/unknown",
        ]
        for index, path in enumerate(not_found, 1):
            self.run(
                f"N{index:02}",
                path,
                "404 NOT_FOUND",
                lambda path=path: self.error(path, 404, "NOT_FOUND"),
            )
        self.run(
            "N05",
            "POST method rejected",
            "405 METHOD_NOT_ALLOWED",
            lambda: self.error("/api/v1/books", 405, "METHOD_NOT_ALLOWED", method="POST"),
        )

    def filtered(self, path: str, predicate: Callable[[dict[str, Any]], bool]) -> None:
        """Check a non-vacuous filtered result."""
        result = self.books(path)
        require(
            bool(result["data"]) and all(predicate(book) for book in result["data"]),
            "all results match",
        )

    def faults(self) -> None:
        """Start disposable loopback processes; no application test back doors."""
        if self.args.skip_fault_scenarios:
            for index in range(1, 11):
                self.run(
                    f"F{index:02}",
                    "fault scenario (--skip-fault-scenarios)",
                    "",
                    lambda: None,
                    skip=True,
                )
            return
        try:
            with fault_stack() as (base, upstream):
                saved = self.base
                self.base = base
                try:
                    detail = "/api/v1/books/a-light-in-the-attic_1000"
                    scenarios = [
                        ("status", 500, "all", "/api/v1/books", 502, "UPSTREAM_UNAVAILABLE"),
                        ("delay", 0, "all", "/api/v1/books", 504, "UPSTREAM_TIMEOUT"),
                        ("garbage", 0, "all", "/api/v1/books", 502, "UPSTREAM_UNAVAILABLE"),
                        ("normal", 0, "all", "/api/v1/books", 200, ""),
                        ("normal", 0, "all", "/api/v1/books/unknown-book_1", 404, "NOT_FOUND"),
                        ("delay", 0, "detail", detail, 504, "UPSTREAM_TIMEOUT"),
                        ("status", 500, "detail", detail, 502, "UPSTREAM_UNAVAILABLE"),
                        ("status", 403, "detail", detail, 502, "UPSTREAM_UNAVAILABLE"),
                        ("status", 429, "detail", detail, 502, "UPSTREAM_UNAVAILABLE"),
                        ("status", 500, "detail", detail, 502, "UPSTREAM_UNAVAILABLE"),
                    ]
                    for index, (mode, code, scope, path, status, error) in enumerate(scenarios, 1):

                        def scenario(
                            mode: str = mode,
                            code: int = code,
                            scope: str = scope,
                            path: str = path,
                            status: int = status,
                            error: str = error,
                            index: int = index,
                        ) -> None:
                            query = urlencode(
                                {
                                    "mode": mode,
                                    "code": code or 500,
                                    "scope": scope,
                                    "delay": 3 if mode == "delay" else 0,
                                    "garbage": int(mode == "garbage"),
                                }
                            )
                            self.request("/__control?" + query, base=upstream)
                            self.request("/__stats?reset=1", base=upstream)
                            if status == 200:
                                require(bool(self.books(path)["data"]), "successful recovery")
                            else:
                                self.error(path, status, error)
                            if index in {8, 9, 10}:
                                _, stats, _ = self.request("/__stats", base=upstream)
                                hits = stats["detail"]
                                require(
                                    hits == 1 if index in {8, 9} else 1 <= hits <= 2,
                                    f"bounded detail hits, got {hits}",
                                )

                        self.run(
                            f"F{index:02}",
                            f"{mode} {code or ''} scope={scope}".strip(),
                            f"HTTP {status} {error}; bounded retry counters",
                            scenario,
                        )
                finally:
                    self.base = saved
        except (OSError, RuntimeError, URLError) as exc:
            # A failed process stack is a failed required scenario, never an implicit skip.
            self.run(
                "F00",
                "fault stack startup",
                "ready local processes",
                lambda exc=exc: require(False, str(exc)),
            )

    def finish(self, override: int | None = None) -> int:
        """Print totals and optional machine-readable summary with the final exit code."""
        counts = {
            key: sum(result.status == key for result in self.results)
            for key in ("PASS", "FAIL", "SKIP")
        }
        code = override if override is not None else int(counts["FAIL"] > 0)
        print(
            f"Passed {counts['PASS']}  Failed {counts['FAIL']}  "
            f"Skipped {counts['SKIP']} -> EXIT {code}"
        )
        if self.args.json:
            from dataclasses import asdict

            print(
                json.dumps(
                    {
                        "passed": counts["PASS"],
                        "failed": counts["FAIL"],
                        "skipped": counts["SKIP"],
                        "exit_code": code,
                        "scenarios": [asdict(r) for r in self.results],
                    }
                )
            )
        return code


def require(condition: object, message: str) -> None:
    """Raise a readable test failure without relying on optimizable assert statements."""
    if not condition:
        raise AssertionError(message)


def validate_book(book: dict[str, Any], *, detail: bool) -> None:
    """Validate field sets and concrete JSON types for the public book contract."""
    require(set(book) == (DETAIL_FIELDS if detail else SUMMARY_FIELDS), "exact book fields")
    require(
        all(
            isinstance(book[key], str) and bool(book[key])
            for key in ("id", "title", "category", "product_url")
        ),
        "string fields",
    )
    require(type(book["price"]) in {int, float} and book["price"] >= 0, "numeric price")
    require(
        book["currency"] == "GBP" and type(book["rating"]) is int and 1 <= book["rating"] <= 5,
        "currency/rating",
    )
    require(book["availability"] in {"in_stock", "out_of_stock", "unknown"}, "availability enum")
    require(book["image_url"] is None or isinstance(book["image_url"], str), "image type")
    if detail:
        require(book["stock_count"] is None or type(book["stock_count"]) is int, "stock type")
        require(
            all(book[key] is None or isinstance(book[key], str) for key in ("description", "upc")),
            "optional metadata types",
        )


def free_port() -> int:
    """Choose a currently free loopback port for a disposable process."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(url: str, process: subprocess.Popen[bytes], log: Any) -> None:
    """Poll startup with a bounded deadline, short socket timeouts and log evidence."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            with OPENER.open(url, timeout=0.5) as response:
                if response.code == 200:
                    return
        except (URLError, OSError):
            time.sleep(0.05)
    log.seek(0)
    raise RuntimeError(
        f"Process did not become ready at {url}: {log.read().decode(errors='replace')[-1500:]}"
    )


@contextmanager
def fault_stack() -> Iterator[tuple[str, str]]:
    """Always terminate both children, including partial-startup and interrupt failures."""
    processes: list[subprocess.Popen[bytes]] = []
    with tempfile.TemporaryFile() as upstream_log, tempfile.TemporaryFile() as app_log:
        try:
            upstream_port, app_port = free_port(), free_port()
            while app_port == upstream_port:
                app_port = free_port()
            upstream = f"http://127.0.0.1:{upstream_port}"
            base = f"http://127.0.0.1:{app_port}"
            fake = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "scripts/fake_upstream.py"),
                    "--port",
                    str(upstream_port),
                ],
                cwd=ROOT,
                stdout=upstream_log,
                stderr=subprocess.STDOUT,
            )
            processes.append(fake)
            wait_ready(upstream + "/__stats", fake, upstream_log)
            env = {
                **os.environ,
                "BOOKBRIDGE_UPSTREAM_BASE_URL": upstream,
                "BOOKBRIDGE_CONNECT_TIMEOUT_SECONDS": "1",
                "BOOKBRIDGE_READ_TIMEOUT_SECONDS": "1",
                "BOOKBRIDGE_MAX_RETRIES": "1",
                "BOOKBRIDGE_RETRY_BACKOFF_SECONDS": "0.05",
                "BOOKBRIDGE_DETAIL_CACHE_TTL_SECONDS": "0",
                "BOOKBRIDGE_RESPECT_ROBOTS_TXT": "false",
                "BOOKBRIDGE_MIN_REQUEST_INTERVAL_SECONDS": "0.01",
                "BOOKBRIDGE_INDEX_WARMUP_ON_STARTUP": "false",
                "BOOKBRIDGE_INDEX_TTL_SECONDS": "900",
                "BOOKBRIDGE_LOG_LEVEL": "WARNING",
            }
            app = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(app_port),
                ],
                cwd=ROOT,
                env=env,
                stdout=app_log,
                stderr=subprocess.STDOUT,
            )
            processes.append(app)
            wait_ready(base + "/health", app, app_log)
            yield base, upstream
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


def main() -> int:
    """Exit 0 for success, 1 for contract failures, 2 for an unreachable service."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--warmup-timeout", type=float, default=120)
    parser.add_argument("--skip-fault-scenarios", action="store_true")
    parser.add_argument("--skip-golden", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0 or args.warmup_timeout <= 0:
        parser.error("timeouts must be positive")
    evaluator = Evaluator(args)
    try:
        # Reachability is separate from correctness of health and its JSON contract.
        with OPENER.open(args.base_url.rstrip("/") + "/health", timeout=args.timeout) as response:
            response.read()
    except HTTPError:
        pass
    except (URLError, OSError) as exc:
        print(f"Service unreachable: {exc}. Start uvicorn src.main:app first.")
        return evaluator.finish(override=2)
    evaluator.live()
    evaluator.faults()
    return evaluator.finish()


if __name__ == "__main__":
    raise SystemExit(main())
