# EVALUATOR SPEC — BookBridge API

*Design of scripts/test_api.py and scripts/fake_upstream.py*

## Purpose

The assignment requires a working script that tests the relevant cases. This document specifies it. The evaluator has two groups of scenarios: live scenarios against a running instance (`--base-url`) and fault scenarios that start their own throwaway app instance pointed at a local fake upstream, so timeouts and 5xx errors can be demonstrated without any back door in the application.

## Invocation

```
python scripts/test_api.py --base-url http://localhost:8000
python scripts/test_api.py --base-url http://localhost:8000 --skip-fault-scenarios
python scripts/test_api.py --json   # machine-readable summary
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--base-url` | `http://localhost:8000` | Running BookBridge instance for live scenarios. |
| `--timeout` | 30 | Per-request timeout in seconds. |
| `--warmup-timeout` | 120 | Timeout for the first catalogue request (builds the index, about 70 polite upstream requests). |
| `--skip-fault-scenarios` | off | Skip the self-managed fault scenarios. |
| `--skip-golden` | off | Skip data-specific checks for the known record, in case the source data changes. |
| `--json` | off | Print a JSON summary after the human-readable lines. |
| `--verbose` | off | Print request/response excerpts for passing scenarios too. |

## Constraints

- Python 3.12, standard library only (`urllib.request`, `json`, `subprocess`, `http.server`, `threading`, `argparse`). No pip install needed to run it.
- Only GET requests to the local API for live scenarios, plus one POST to prove 405. At most about 60 requests to the running service. The one-time index build is the only heavy step and is triggered by the first catalogue call.
- Deterministic order, short per-scenario output, never hangs: every socket operation has a timeout; subprocesses are always terminated in a `finally` block.
- Exit code 0 only if every required scenario passes; 1 if any fails; 2 if the service is unreachable (print a hint to start it).

## Output Format

```
PASS  L01 health returns 200 and status ok                       (12 ms)
PASS  L03 books list returns envelope and 20 items             (4210 ms)
FAIL  V05 page_size=1000 returns 422
      expected: HTTP 422 with error.code=VALIDATION_ERROR
      actual:   HTTP 200, body: {"data": [...
SKIP  L11 golden record (--skip-golden)
----------------------------------------------------------------
Passed 41  Failed 1  Skipped 1   -> EXIT 1
```

## Live Scenarios (against --base-url)

| ID | Request | Expectation |
| --- | --- | --- |
| L01 | GET /health | 200; status 'ok'. |
| L02 | GET /openapi.json | 200; contains all six documented paths. |
| L03 | GET /api/v1/books (warm-up) | 200; 20 items; pagination has page, page_size, total, has_next; total >= 20; has_next true. |
| L04 | GET /api/v1/books?page_size=50 | 200; exactly 50 items. |
| L05 | page=1 vs page=2 (page_size=20) | No overlapping ids. |
| L06 | rating=5 | Every item has rating 5. |
| L07 | min_price=10&max_price=40 | Every price within [10, 40]. |
| L08 | min_price=p&max_price=p, p taken from an L03 item | Result includes that item (inclusive bounds). |
| L09 | rating=3&min_price=10&max_price=60 | Every item satisfies all three. |
| L10 | GET /api/v1/books/{first id from L03} | 200; BookDetail fields present with correct types; id matches. |
| L11 | GET /api/v1/books/a-light-in-the-attic_1000 (golden) | price 51.77, currency GBP, rating 3, category Poetry, upc a897fe39b1053632, stock_count integer. |
| L12 | GET /api/v1/search?q=light | At least 1 result; every title contains 'light' case-insensitively. |
| L13 | q=LIGHT vs q=light | Same total. |
| L14 | q=zzzxqjkw | 200; data []; total 0; has_next false. |
| L15 | q=a&page_size=1&page=2 | 200; exactly 1 item. |
| L16 | GET /api/v1/categories | At least 40 entries with name and slug; includes slug 'poetry'; no 'books' entry. |
| L17 | GET /api/v1/categories/poetry/books | 200; all items have category 'Poetry'; total >= 1. |
| L18 | GET /api/v1/categories/poetry/books?page=999 | 200; empty data. |
| H01 | Any response | Has an X-Request-ID header. |

### Validation (all expect 422 with error.code VALIDATION_ERROR and a string message)

| ID | Request |
| --- | --- |
| V01 | /api/v1/books?page=0 |
| V02 | /api/v1/books?page=-1 |
| V03 | /api/v1/books?page=abc |
| V04 | /api/v1/books?page_size=0 |
| V05 | /api/v1/books?page_size=1000 |
| V06 | /api/v1/books?rating=0 |
| V07 | /api/v1/books?rating=6 |
| V08 | /api/v1/books?min_price=-1 |
| V09 | /api/v1/books?min_price=50&max_price=10 |
| V10 | /api/v1/search?q= |
| V11 | /api/v1/search (q missing) |
| V12 | /api/v1/search?q=%20%20 (whitespace only) |

### Not found and method errors (JSON error envelope)

| ID | Request | Expectation |
| --- | --- | --- |
| N01 | GET /api/v1/books/does-not-exist_0 | 404 NOT_FOUND. |
| N02 | GET /api/v1/books/..%2f..%2fetc | 404 NOT_FOUND, no upstream traversal. |
| N03 | GET /api/v1/categories/no-such-category/books | 404 NOT_FOUND. |
| N04 | GET /api/v1/unknown | 404 with the same envelope. |
| N05 | POST /api/v1/books | 405 METHOD_NOT_ALLOWED with the same envelope. |

## Fault Scenarios (self-managed)

Procedure: (1) pick a free port and start `scripts/fake_upstream.py` in a thread or subprocess serving `tests/fixtures/site/`; (2) start the app with `python -m uvicorn src.main:app --port <free>` and environment overrides: `BOOKBRIDGE_UPSTREAM_BASE_URL` pointing at the fake upstream, `BOOKBRIDGE_CONNECT_TIMEOUT_SECONDS=1`, `BOOKBRIDGE_READ_TIMEOUT_SECONDS=1`, `BOOKBRIDGE_MAX_RETRIES=1`, `BOOKBRIDGE_RETRY_BACKOFF_SECONDS=0.05`, `BOOKBRIDGE_DETAIL_CACHE_TTL_SECONDS=0`, `BOOKBRIDGE_RESPECT_ROBOTS_TXT=false`; (3) wait for /health; (4) run the scenarios below by switching the fake upstream mode through its control endpoint; (5) terminate both processes in a `finally` block.

| ID | Fake upstream mode | Request | Expectation |
| --- | --- | --- | --- |
| F01 | status 500 (all paths) | GET /api/v1/books | 502 UPSTREAM_UNAVAILABLE; JSON envelope. |
| F02 | delay 3 s (all paths) | GET /api/v1/books | 504 UPSTREAM_TIMEOUT. |
| F03 | 200 with a maintenance page and no products | GET /api/v1/books | 502 UPSTREAM_UNAVAILABLE. |
| F04 | normal | GET /api/v1/books | 200: earlier failures were not cached. |
| F05 | normal, id absent from fixtures | GET /api/v1/books/unknown-book_1 | 404 NOT_FOUND. |
| F06 | delay 3 s (detail pages only) | GET /api/v1/books/{known id} | 504 UPSTREAM_TIMEOUT. |
| F07 | status 500 (detail pages only) | GET /api/v1/books/{known id} | 502. |
| F08 | status 403 (detail pages only) | GET /api/v1/books/{known id} | 502, and the fake saw exactly 1 request (no retry, no evasion). |
| F09 | status 429 + Retry-After (detail only) | GET /api/v1/books/{known id} | 502, and the fake saw exactly 1 request. |
| F10 | status 500 (detail only) | GET /api/v1/books/{known id} | Fake saw at most MAX_RETRIES + 1 requests (bounded retries). |

## scripts/fake_upstream.py

- Standard library `ThreadingHTTPServer` bound to 127.0.0.1 only. Serves files under `tests/fixtures/site/` using the real URL layout (a directory path maps to its `index.html`; `/` maps to `index.html`; unknown path -> 404).
- Control endpoint: `GET /__control?mode=normal|status&code=500&delay=3&garbage=1&scope=all|detail` sets the failure mode. Stats endpoint: `GET /__stats` returns JSON hit counters per path category (home, category, detail) and a reset option `?reset=1`.
- `scope=detail` applies the failure only to `/catalogue/{slug}_{n}/index.html` paths.
- Can run standalone (`python scripts/fake_upstream.py --port 8765`) so a reviewer can also run the whole API fully offline with `BOOKBRIDGE_UPSTREAM_BASE_URL=http://127.0.0.1:8765`.

---
BookBridge API • Razorpay Reverse-Engineering Assignment
