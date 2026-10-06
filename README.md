# BookBridge API

BookBridge exposes Books to Scrape’s public HTML as a read-only FastAPI JSON service.
It supports catalogue filtering, title search, categories and full book details.
Only public, unauthenticated GET pages are fetched with a descriptive User-Agent,
robots checks, bounded retries and conservative pacing. No private data, forms,
access-control bypass or rate-limit evasion is used. This is an educational sandbox
integration; its fictional data may be stale.

## Quick start

From the repository root, with Python 3.12+:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn src.main:app --reload
```

The app starts without `.env`. Open [Swagger](http://localhost:8000/docs),
[ReDoc](http://localhost:8000/redoc), or [OpenAPI](http://localhost:8000/openapi.json).
The first catalogue request builds the index; `/health` never calls upstream.
For runtime-only installation use `requirements.txt` in place of the dev file.
The requirements pin the exact tested runtime and development dependency versions.

## Fully offline demonstration

After installation, activate the same venv in each terminal. Start the fixture
server in terminal one:

```bash
python scripts/fake_upstream.py --port 8765
```

Start the API in terminal two:

```bash
BOOKBRIDGE_UPSTREAM_BASE_URL=http://127.0.0.1:8765 uvicorn src.main:app --reload
```

The synthetic fixture catalogue has 60 books, 40 categories, pagination, all five
ratings, price boundaries, optional-field gaps and the golden detail record.
Three separately saved public HTML pages provide additional parser regressions.
The fixture server listens only on loopback; its control/stats endpoints belong
to the standalone test infrastructure and are absent from the application.

## Endpoints

| Method | Endpoint | Behaviour |
| --- | --- | --- |
| GET | `/health` | Local readiness and index age/staleness |
| GET | `/api/v1/books` | Inclusive price filters, exact rating; AND semantics |
| GET | `/api/v1/books/{id}` | Cached full details; malformed/unknown ID → 404 |
| GET | `/api/v1/search?q=light` | Trimmed, case-insensitive title substring |
| GET | `/api/v1/categories` | Sidebar order; exclude the top-level Books node |
| GET | `/api/v1/categories/{slug}/books` | Category books; unknown slug → 404 |

All lists support `page` (default 1, minimum 1) and `page_size` (default 20,
range 1–50). Books additionally supports nonnegative `min_price` and `max_price`
with `max_price >= min_price`, and `rating` 1–5. Search `q` must contain 1–100
characters after trimming. A page past the end returns 200 with empty data.
Categories itself is an unpaginated category envelope.

```bash
curl -sS http://localhost:8000/health
curl -sS 'http://localhost:8000/api/v1/books?min_price=10&max_price=40&rating=5'
curl -sS http://localhost:8000/api/v1/books/a-light-in-the-attic_1000
curl -sS 'http://localhost:8000/api/v1/search?q=light'
curl -sS http://localhost:8000/api/v1/categories
curl -sS 'http://localhost:8000/api/v1/categories/poetry/books?page_size=1'
```

A one-item fixture response (URLs reflect the configured source):

```json
{
  "data": [{
    "id": "a-light-in-the-attic_1000",
    "title": "A Light in the Attic",
    "price": 51.77,
    "currency": "GBP",
    "rating": 3,
    "availability": "in_stock",
    "category": "Poetry",
    "image_url": "http://127.0.0.1:8765/media/cache/demo.jpg",
    "product_url": "http://127.0.0.1:8765/catalogue/a-light-in-the-attic_1000/index.html"
  }],
  "pagination": {"page": 1, "page_size": 1, "total": 21, "has_next": true}
}
```

Details add nullable `stock_count`, `upc`, and `description` and use
`{"data": {...}}`. Categories use `{"data": [{"name": "Poetry", "slug": "poetry"}]}`.
Prices use Decimal internally and serialize as JSON numbers. JSON consumers
should format two decimal places for display; trailing zeros are not guaranteed.
Every response includes `X-Request-ID`; sane incoming IDs are echoed.

## Errors

```json
{"error":{"code":"VALIDATION_ERROR","message":"Invalid request parameters.","details":[{"field":"max_price","message":"must be >= min_price"}]}}
```

| HTTP | Code | Meaning |
| --- | --- | --- |
| 422 | `VALIDATION_ERROR` | Invalid parameters; details list contains field/message |
| 404 | `NOT_FOUND` | Unknown resource, route, or malformed book ID |
| 405 | `METHOD_NOT_ALLOWED` | Unsupported method |
| 502 | `UPSTREAM_UNAVAILABLE` | Source denied access, failed or returned unusable HTML |
| 504 | `UPSTREAM_TIMEOUT` | Timeout after bounded retries |
| 500 | `INTERNAL_ERROR` | Fixed safe message; internal error is logged |

Non-validation errors have `details: null`. Framework errors share this envelope.
Trailing-slash routes also return JSON 404 rather than redirects. Responses do
not expose stack traces or internal exception text.

## Configuration

All variables are optional, prefixed with `BOOKBRIDGE_`. The supplied
[.env.example](.env.example) lists defaults; `.env` is ignored by Git.

| Suffix | Default | Purpose |
| --- | --- | --- |
| `UPSTREAM_BASE_URL` | `https://books.toscrape.com` | HTTP(S) origin; fixture override supported |
| `USER_AGENT` | `BookBridgeAPI/1.0 (educational demo; contact: akshattayal8622@gmail.com)` | Descriptive honest identity |
| `CONNECT_TIMEOUT_SECONDS` | 3 | Connection timeout |
| `READ_TIMEOUT_SECONDS` | 8 | Read/write/pool timeout |
| `MAX_RETRIES` | 2 | Retries after initial attempt, maximum 5 |
| `RETRY_BACKOFF_SECONDS` | 0.5 | Exponential base; up to 0.1 seconds jitter |
| `MAX_CONCURRENT_REQUESTS` | 4 | Shared concurrency cap, range 1–4 |
| `MIN_REQUEST_INTERVAL_SECONDS` | 0.1 | Minimum time between request starts |
| `DETAIL_CACHE_TTL_SECONDS` | 300 | Successful detail cache, maximum 256 entries |
| `INDEX_TTL_SECONDS` | 900 | Whole-catalogue snapshot lifetime |
| `INDEX_WARMUP_ON_STARTUP` | false | Optional background build |
| `RESPECT_ROBOTS_TXT` | true | Fetch once and obey Disallow |
| `LOG_LEVEL` | INFO | Standard logging level |

The client ignores environment proxies, refuses cookies and allows only the
configured origin, with at most three redirects. Timeouts, connection failures
and 500/502/503/504 can retry; 403/429/404 never retry. Robots 404/network failures
mean allowed per the assignment; robots access restrictions and unsafe redirects
fail closed. For public use keep robots checking enabled.

## Verification

Unit and API tests block outbound sockets and require all upstream HTTPX requests
to be mocked with respx. They never touch the live site:

```bash
pytest -q
ruff check .
ruff format --check .
```

With the API running, run the standard-library evaluator:

```bash
python scripts/test_api.py --base-url http://localhost:8000
python scripts/test_api.py --base-url http://localhost:8000 --skip-fault-scenarios
python scripts/test_api.py --json
```

The evaluator exercises L01–L18, H01, V01–V12 and N01–N05 against the supplied
base URL, then starts a separate fake upstream and disposable Uvicorn instance
for F01–F10. It tests failures, recovery, access restrictions and retry counters.
The only POST targets the local API to verify 405. Child processes are always
terminated. Exit codes: 0 passes, 1 contract failure, 2 unreachable service.
`--timeout` defaults to 30 seconds and `--warmup-timeout` to 120 seconds;
`--skip-golden` omits source-specific golden values and `--verbose` prints excerpts.
Explicit skips are reported separately, so a run with skips is not full verification.
The script itself needs no third-party imports; fault instances require the app’s
installed dependencies in the interpreter used to run it.

Latest verified results: 80 offline tests; all 46 offline evaluator scenarios;
36 live scenarios (faults separately verified offline); deliberate evaluator
exit-1 and exit-2 checks. See [verification evidence](docs/VERIFICATION.md).

## Docker and tooling

The Dockerfile uses `python:3.12-slim`, pinned requirements, only application
source, an unprivileged user and a Python `/health` HEALTHCHECK. Build with
`make docker-build`, then run with `make docker-run` when Docker is running.
Docker build and run were verified on the user's machine. The container's
`/health` endpoint works, its HEALTHCHECK reports `healthy`, and it runs as the
non-root user `bookbridge`. The evaluator also passed against the container.

Make targets: `install`, `run`, `test`, `lint`, `evaluate`, `docker-build`,
`docker-run`. GitHub Actions installs on Python 3.12, runs lint, format, socket-blocked
pytest, the offline evaluator and a Docker build. CI never calls the public site.
The workflow itself has not yet been executed by GitHub Actions.

## Design and layout

- `src/api`: thin routes, typed dependencies, central errors and request IDs.
- `src/clients/catalogue.py`: all upstream HTTP, robots, retries, pacing and safety.
- `src/parsers`: pure BeautifulSoup extraction with the built-in `html.parser`.
- `src/services`: single-flight immutable index, filter/search/pagination and details.
- `src/schemas`: frozen normalized books and Pydantic response envelopes.
- `src/config.py`, `src/cache.py`: validated settings and bounded injectable-clock TTL cache.
- `tests/fixtures/site`: synthetic mini-site; `reference`: saved public HTML regressions.
- `scripts`: standard-library evaluator and isolated local fault server.

The index reads the home sidebar and every category’s linked pages (about 70
requests), assigning category without fetching every book detail. It de-duplicates
IDs, sorts by descending numeric suffix and atomically publishes a complete snapshot.
Concurrent callers share a build, including its failure. An expired index refresh
that fails preserves the previous snapshot and waits 30 seconds before another
refresh; health exposes staleness. Details are fetched only on demand and cached
for five minutes; failures are never cached. Each process owns its cache/index,
so a single worker is the recommended demo configuration.

See [LIMITATIONS.md](LIMITATIONS.md) for the short limitations and authorized
long-term fix, [REVERSE_ENGINEERING_NOTES.md](REVERSE_ENGINEERING_NOTES.md) for
observed HTML structure, and [implementation decisions](docs/IMPLEMENTATION_NOTES.md).
The original spec pack and `.env.example` remain unchanged.
