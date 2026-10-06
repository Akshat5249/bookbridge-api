# DESIGN DECISIONS — BookBridge API

*Resolutions for gaps and ambiguities in documents 01-08*

## Purpose and Precedence

The original pack leaves several implementation questions open (what list items contain, how filtering works over a site that only shows 20 books per page, how validation errors are shaped, how failures are exercised by the evaluator). This document resolves them. Where it is silent, SPEC and CODEX apply. Where it contradicts SPEC or CODEX, SPEC and CODEX win and the discrepancy must be noted in the final report.

Precedence: SPEC > CODEX > this document > API Contract > Upstream Site Notes > Evaluator Spec > Architecture > Test Plan > Repo Layout > Limitations > README > Initial Prompt (superseded by the Master Prompt).

## D1. Schemas

- `BookSummary` (list, search, category endpoints): id, title, price, currency, rating, availability, category, image_url, product_url.
- `BookDetail` (detail endpoint) is exactly the SPEC Normalized Book Schema: BookSummary fields plus stock_count, upc, description.
- Reason: listing pages do not expose UPC, description or stock count, and fetching 1,000 detail pages to fill them would be abusive. BookSummary is a strict subset of BookDetail with identical field names and types.
- `availability` is the enum `in_stock | out_of_stock | unknown`. `stock_count` is null if it cannot be parsed. `description` is null when the page has none.
- Detail response envelope: `{ "data": { ... } }`. List responses: `{ "data": [...], "pagination": {...} }`. Categories: `{ "data": [ {"name": "Poetry", "slug": "poetry"} ] }`.

## D2. Catalogue Index Strategy

The site shows 20 books per page, shows no category on listing pages, and has no filter or search. Filtering by price/rating, searching by title and arbitrary page_size therefore need the whole catalogue. Decision: build an in-memory catalogue index lazily.

- Index source: the home page (for the category list) plus every category page and its pagination (about 70 requests in total). This yields category, price, rating, availability, image and URL for every book.
- Index is an immutable snapshot (tuple of BookSummary sorted by numeric id descending, dict by id, category list, built_at). Replaced atomically on refresh.
- Built on first need with single-flight semantics (one `asyncio.Lock`; concurrent callers await the same build). Bounded concurrency (D10).
- Refreshed after `INDEX_TTL_SECONDS` (default 900). If a refresh fails and a previous snapshot exists, keep serving it, log a warning and report `stale: true` in /health (stale-if-error). If no snapshot exists, the failure maps to 502/504.
- Optional background warm-up on startup (`INDEX_WARMUP_ON_STARTUP`, default false, always false in tests). It must never block startup or fail the app.
- `/health` never triggers an upstream request.
- Default order for every list: numeric id descending (matches the site's natural order, so 'A Light in the Attic' is first). No sort parameter in v1.

## D3. Book Detail

- Validate the id against `^[a-z0-9][a-z0-9-]*_[0-9]+$` before any upstream call. A malformed id returns 404 NOT_FOUND (never build an upstream URL from unvalidated input).
- Fetch `/catalogue/{id}/index.html` on demand; parse into BookDetail; cache by id for `DETAIL_CACHE_TTL_SECONDS` (default 300). Upstream 404 -> 404 NOT_FOUND.
- Category for the detail comes from the breadcrumb on the detail page.

## D4. Categories

- Public slug = slugified category name (see doc 09). The service maps slug -> upstream folder from the parsed home page. Unknown slug -> 404 without any upstream guess.
- `GET /api/v1/categories/{slug}/books` serves from the index (filter by category), with page and page_size only.
- Categories are returned in the sidebar order, excluding the top-level 'Books' node.

## D5. Pagination

- Defaults: page=1, page_size=20. `total` is the number of items after filters. `has_next = page * page_size < total`.
- A page past the end returns 200 with `data: []` (not 404) and `has_next: false`.

## D6. Filters

- `min_price` and `max_price` are inclusive and optional; each >= 0; `min_price > max_price` -> 422. `rating` is an exact match 1..5. All filters combine with AND.
- Compare prices as `Decimal` (convert the query float with `Decimal(str(value))`) to avoid binary floating-point surprises at the boundaries. Serialize price in JSON as a number with two decimals.

## D7. Search

- `q` is stripped; length 1..100 after stripping; empty, missing or whitespace-only -> 422.
- Case-insensitive (`casefold`) substring match on title over the index; same pagination, same default order. No match -> 200 with empty data and total 0.

## D8. Error Envelope and Mapping

Every non-2xx response, including framework-generated ones, uses one envelope:

```
{ "error": { "code": "VALIDATION_ERROR",
             "message": "Invalid request parameters.",
             "details": [ { "field": "page", "message": "must be >= 1" } ] } }
```

| Situation | HTTP | code |
| --- | --- | --- |
| Invalid query/path input (incl. min_price > max_price) | 422 | VALIDATION_ERROR |
| Unknown book, malformed book id, unknown category, unknown route | 404 | NOT_FOUND |
| Method not allowed | 405 | METHOD_NOT_ALLOWED |
| Upstream timeout after bounded retries | 504 | UPSTREAM_TIMEOUT |
| Upstream unreachable, 5xx, 403, 429, unusable HTML | 502 | UPSTREAM_UNAVAILABLE |
| Anything unexpected | 500 | INTERNAL_ERROR |

- Register handlers for `RequestValidationError`, Starlette `HTTPException`, the domain exceptions and a catch-all `Exception` in `src/api/errors.py`. Routes never build error JSON by hand.
- Never leak stack traces, upstream URLs with credentials or internal paths. `details` is null for non-validation errors.
- Every response carries `X-Request-ID` (echo a sane incoming value, otherwise a new uuid4). Log it with each error.

## D9. Upstream Failure Semantics

| Condition | Exception | HTTP |
| --- | --- | --- |
| Connect or read timeout after retries | UpstreamTimeout | 504 |
| Connection error after retries | UpstreamUnavailable | 502 |
| Upstream 500/502/503/504 after retries | UpstreamUnavailable | 502 |
| Upstream 403 or 429 (access restriction) | UpstreamUnavailable, no retry | 502 |
| Upstream 404 on a detail page | NotFound | 404 |
| Upstream 404 on index/category pages | UpstreamUnavailable (structure changed) | 502 |
| HTTP 200 but critical fields (id, title, price) unparseable, or zero product cards where cards are expected | UpstreamParseError (subclass of UpstreamUnavailable) | 502 |
| Non-critical field missing (description, image, stock) | none: value becomes null, log a warning | 200 |

- Retries apply to GET only: at most `MAX_RETRIES` (default 2, i.e. 3 attempts) on timeouts, connection errors and 500/502/503/504, with exponential backoff (0.5 s x 2^n) plus up to 0.1 s jitter. Never retry 403, 429 or 404. Never try to work around a restriction.
- One malformed card on a listing page is skipped with a warning; zero parseable cards on a page that should contain cards is a critical parse failure.

## D10. Politeness and Safety

- User-Agent: descriptive and honest, configurable, e.g. `BookBridgeAPI/1.0 (educational demo; contact: you@example.com)`.
- Global `asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)` (default 4) plus a minimum interval between request starts (`MIN_REQUEST_INTERVAL_SECONDS`, default 0.1).
- If `RESPECT_ROBOTS_TXT` is true (default), fetch robots.txt once with `urllib.robotparser`; 404 or unreachable robots.txt means allowed; a Disallow for a needed path -> UpstreamUnavailable.
- Follow at most 3 redirects and only to the same host as `UPSTREAM_BASE_URL`; reject anything else. Do not persist cookies (use a cookie policy that rejects all cookies).
- No user-supplied value is ever interpolated into an upstream URL except the validated book id and mapped category folder. This prevents SSRF and path traversal.

## D11. Money and Parsing

- Use `Decimal` internally. Currency map: '£' and the mojibake 'Â£' -> GBP. If no recognizable number is found the field is critical (D9).
- Rating words One..Five map to 1..5; anything else is a critical parse failure for that card.
- Parser functions are pure: input is an HTML string plus the page URL; output is Pydantic models or plain dicts. No network, no clock, no randomness.

## D12. Application Wiring

- App factory `create_app(settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> FastAPI` and a module-level `app = create_app()` so `uvicorn src.main:app` works.
- A single shared `httpx.AsyncClient` is created in the FastAPI lifespan and closed on shutdown. Services receive the client via dependency injection (`app.state`), so tests can substitute a mocked client.
- Every package directory has an `__init__.py`; pytest config sets `pythonpath = .` and `asyncio_mode = auto`.

## D13. Observability

- Standard `logging` with a request-id field; log upstream request method, path, status, duration and attempt number at INFO/DEBUG; warnings for skipped cards and stale index use.
- `GET /health` returns `{ "status": "ok", "service": "bookbridge-api", "version": "1.0.0", "index": { "loaded": false, "stale": false, "age_seconds": null, "books": 0 } }`.

## D14. OpenAPI Quality

- Tags per resource, summaries, response models, examples, and documented error responses (404, 422, 502, 504 using the ErrorResponse model) on each route.
- The API description states: data is scraped from a public sandbox site, may be stale, and this is an educational demonstration.

## D15. Failure Testing Without Back Doors

The application contains no debug headers, fault-injection flags or test-only endpoints. Controlled upstream failures are exercised in two places: pytest (respx mocks) and the standalone evaluator, which starts a local fake upstream and a second app instance pointed at it (see Evaluator Spec).

## D16. Documentation Deliverables

- `LIMITATIONS.md` must be a short note (about one page, 350 words max) with the primary limitation and the appropriate long-term fix, as the assignment requires. Doc 07 is the long form.
- `REVERSE_ENGINEERING_NOTES.md` summarizes doc 09 and how the structure was discovered.
- README commands must be exactly the commands that were run and verified.

---
BookBridge API • Razorpay Reverse-Engineering Assignment
