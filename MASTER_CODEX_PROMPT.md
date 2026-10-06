# MASTER PROMPT — BookBridge API (Razorpay Reverse-Engineering Assignment)

You are a senior backend engineer completing a take-home assignment end to end, autonomously, in this repository. Do not stop after scaffolding and do not ask me questions: make reasonable decisions, record any deviation in your final report, and deliver a runnable, tested, documented submission.

## 0. The assignment (verbatim intent)
"Reverse-engineer an API: choose a website that does not offer a public API and build a set of APIs for it. Submit a working script to test the relevant cases, along with a short note on the solution's limitations and the appropriate long-term fix. Use publicly accessible information only; do not bypass access controls or include private data."

Chosen site: Books to Scrape (https://books.toscrape.com/), a public sandbox site published for scraping practice. Product: **BookBridge API**, a read-only FastAPI service that turns its public HTML into a clean, stable JSON REST contract.

## 1. Your inputs and precedence
The specification pack is in `docs/spec-pack/` (Markdown). READ ALL 12 FILES FIRST, completely, before writing code. If the folder is missing, look for `docs_md/`.
Precedence when documents disagree: 02_SPEC > 03_CODEX > 10_DESIGN_DECISIONS > 04_API_CONTRACT > 09_UPSTREAM_SITE_NOTES > 11_EVALUATOR_SPEC > 05_ARCHITECTURE > 06_TEST_PLAN > 12_REPO_LAYOUT_AND_DELIVERABLES > 07_LIMITATIONS > 01_README. `08_INITIAL_CODEX_PROMPT` is superseded by this prompt. `.env.example` at the repo root is provided; keep it.
Do not edit the spec documents. List any conflict you resolved in the final report.

## 2. Hard boundaries (never violate, self-audit at the end)
- Public, unauthenticated pages an ordinary visitor can open. GET requests only. Never submit forms.
- Never bypass or work around authentication, paywalls, CAPTCHA, WAF/bot controls, robots.txt or rate limits.
- No proxy rotation, no spoofed browser identity or sessions, no cookie/credential harvesting, no stealth or headless-browser tricks, no private or undocumented endpoints.
- No private or user data. No secrets in the repo.
- If access is denied (403/429/robots), fail gracefully with a controlled error and document it. Do not retry around it.
- Be polite: descriptive User-Agent, low concurrency, short delays, caching. Normal tests and CI must never touch the live site.

## 3. What to build (summary; the docs have full detail)
Stack: Python 3.12+, FastAPI + Uvicorn, httpx AsyncClient, BeautifulSoup4 (`html.parser`), Pydantic v2 + pydantic-settings, pytest + pytest-asyncio + respx, ruff, Docker.

Endpoints (prefix `/api/v1`, JSON only, all documented in OpenAPI):
- `GET /health`: 200 status JSON; never calls upstream.
- `GET /api/v1/books`: params `page>=1` (default 1), `page_size` 1..50 (default 20), `min_price>=0`, `max_price>=min_price`, `rating` 1..5. Inclusive price bounds, exact rating, AND semantics.
- `GET /api/v1/books/{id}`: full BookDetail (id, title, price, currency, rating, availability, stock_count, category, upc, description, image_url, product_url) wrapped as `{ "data": ... }`; 404 if unknown or malformed id.
- `GET /api/v1/search?q=`: non-empty trimmed `q` (1..100), case-insensitive title substring, paginated.
- `GET /api/v1/categories`: `{ "data": [ {"name": "Poetry", "slug": "poetry"} ] }`, excluding the top-level "Books" node.
- `GET /api/v1/categories/{slug}/books`: paginated; 404 for unknown slug.
List envelope: `{ "data": [...], "pagination": { "page", "page_size", "total", "has_next" } }`. List items are `BookSummary` (no upc/description/stock_count); detail is `BookDetail`. A page past the end returns 200 with empty data.

Errors: ONE envelope everywhere (including framework 404/405/422): `{ "error": { "code", "message", "details" } }`. Mapping: 422 VALIDATION_ERROR (details = list of {field, message}); 404 NOT_FOUND; 405 METHOD_NOT_ALLOWED; 504 UPSTREAM_TIMEOUT; 502 UPSTREAM_UNAVAILABLE (5xx, connection errors, 403, 429, unusable HTML); 500 INTERNAL_ERROR. Every response has an `X-Request-ID` header. No stack traces in responses.

## 4. Reverse-engineering facts you must honour (details in doc 09)
- Book id = `{slug}_{number}` from `/catalogue/{slug}_{number}/index.html`. Detail pages give UPC (table), stock count ("In stock (22 available)"), category (breadcrumb), description (may be missing).
- Listing pages show no category and truncate titles in link text: use the `title` attribute. Prices look like "£51.77" (decode as UTF-8 explicitly; tolerate "Â£"). Rating is a CSS class (`star-rating Three`).
- Relative URLs differ per page depth: always `urljoin(page_url, href)`.
- Only 20 books per page and no filter/search: build a lazy, single-flight, TTL-refreshed in-memory catalogue index from the home page (category list) plus all category pages (~70 polite requests), sorted by numeric id descending (the site's natural order). List/filter/search/category endpoints read the index. Detail pages are fetched on demand and cached.
- Stale-if-error for the index; never cache failures.
- Never build an upstream URL from unvalidated user input (validate id regex; map category slug to the folder parsed from the home page).

## 5. Architecture (routes thin; one responsibility per layer)
`src/main.py` (app factory `create_app()` plus module-level `app`), `config.py`, `exceptions.py`, `cache.py` (small TTL cache with injectable clock, bounded size), `api/` (routes, deps, errors), `clients/catalogue.py` (the only place that does HTTP: timeouts, bounded retries with backoff and jitter on timeouts/connect errors/500/502/503/504 only, never on 403/429/404, global semaphore + minimum request interval, same-host redirects only, no cookies, robots.txt check), `parsers/` (pure, network-free, deterministic), `services/` (index + orchestration, filtering, search, pagination), `schemas/` (Pydantic response models incl. ErrorResponse). Every package has `__init__.py`. Routes never parse HTML; the parser never does I/O.

## 6. Tests (all offline)
- Fixtures in `tests/fixtures/site/` mirroring the real URL layout (see doc 09 "Fixture Mini-Site Coverage"). If you have network access you may fetch at most ~10 public pages once, politely, to save real fixtures; otherwise hand-write them from the templates in doc 09.
- `pytest -q` must pass with NO internet (use respx with `assert_all_mocked=True`; add a guard so an unmocked request fails loudly).
- Cover: parsers (title/price/rating/availability/urls/UPC/category/description/stock, missing optional fields, mojibake price, structurally unusable HTML), cache (TTL, bound, injectable clock), client (timeout->UpstreamTimeout, 500 retry then success, retries are bounded, 403/429/404 are not retried, redirect off-host rejected, UTF-8 decoding), service (index single-flight, stale-if-error, filters incl. inclusive boundaries, search, pagination edges), API via `httpx.ASGITransport` (every endpoint, all validation cases, 404s, 405, 502/504 mapping, error envelope shape, X-Request-ID).

## 7. Standalone evaluator (`scripts/test_api.py`) and `scripts/fake_upstream.py`
Implement exactly as in doc 11: standard-library only; live scenarios L/V/N/H against `--base-url`; self-managed fault scenarios F01-F10 that start a local fake upstream (serving `tests/fixtures/site/` with controllable failure modes and hit counters) and a second app instance via `python -m uvicorn`, with environment overrides; PASS/FAIL/SKIP lines with expected-vs-actual on failure; exit 0 only if all required scenarios pass, 1 on failure, 2 if the service is unreachable; always clean up subprocesses. The application itself must contain NO fault-injection hooks or debug endpoints.

## 8. Deliverables (see doc 12 for the full tree)
`README.md`, `LIMITATIONS.md` (SHORT: about one page, max 350 words, primary limitation plus the appropriate long-term fix: official API or authorized data feed / partnership, with quotas, versioning, SLAs and change notifications; no circumvention), `REVERSE_ENGINEERING_NOTES.md` (how the structure was discovered, URL map, selectors, quirks, no hidden JSON endpoints), `pyproject.toml`, pinned `requirements.txt` and `requirements-dev.txt`, `Dockerfile` (python:3.12-slim, non-root, HEALTHCHECK), `.dockerignore`, `.gitignore`, `Makefile`, `.github/workflows/ci.yml`, `.env.example` (keep as provided), `docs/spec-pack/` (keep), all source, tests and scripts.

## 9. Execution plan (work through in order; run checks at each phase)
1. Read all 12 docs. Write a brief plan (file list + the ambiguities you resolved) to `docs/IMPLEMENTATION_NOTES.md`.
2. Scaffold packages, `pyproject.toml`, requirements; create a venv; install; pin tested versions.
3. Fixtures (mini-site), then parsers + parser tests. Run pytest.
4. Config, exceptions, cache, client + client tests. Run pytest.
5. Index and services + service tests. Run pytest.
6. Schemas, routes, error handlers, app factory, lifespan, OpenAPI metadata + API/error tests. Run pytest and `ruff check .`.
7. `scripts/fake_upstream.py` and `scripts/test_api.py`. Start the app against the fake upstream (`BOOKBRIDGE_UPSTREAM_BASE_URL=http://127.0.0.1:8765`) and run the evaluator fully offline until everything passes, including deliberately breaking something to prove it exits 1, and running it against a stopped server to prove exit 2.
8. If network access is available: start the app against the real site and run the live evaluator once (it builds the index with ~70 polite requests). Fix real-markup discrepancies in the parser and update fixtures. If there is no network, say so in the report; do not fake results.
9. Dockerfile, `.dockerignore`, Makefile, CI. `docker build` and `docker run` plus `curl /health` if Docker is available; otherwise state that it was not verified.
10. Write README, LIMITATIONS.md, REVERSE_ENGINEERING_NOTES.md. Re-run every command in the README exactly as written.
11. Compliance self-review (grep the code for cookies, proxies, header spoofing, form posts, login, headless browsers, fault-injection hooks, TODO/FIXME/placeholder). Fix anything found.
12. Final full verification: `ruff check .`, `ruff format --check .`, `pytest -q`, evaluator run, docs-versus-code consistency check.

## 10. Quality bar
Type hints everywhere; small functions; clear names; no dead code; docstrings on public functions and modules; logging with request id; no broad `except` that hides errors (only the central handler); deterministic tests; no sleeps longer than needed (inject clocks and short backoffs). Code should read like a reviewer at a payments company would want to maintain it.

## 11. If you get stuck
Prefer the simplest implementation that satisfies the docs. If the live site contradicts a document, trust the saved fixture and note it. If a command cannot run in your environment, say exactly which and why. Never weaken a test to make it pass and never disable a boundary rule.

## 12. Final report (your last message, concise)
1. Files created (grouped). 2. Exact commands run with pass/fail results (ruff, pytest counts, evaluator summary, docker). 3. Conflicts or ambiguities and how you resolved them. 4. What was NOT verified and why. 5. Remaining limitations (point to LIMITATIONS.md). 6. Compliance statement confirming public-data-only behavior.
