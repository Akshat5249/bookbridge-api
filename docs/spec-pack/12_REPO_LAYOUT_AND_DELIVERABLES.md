# REPO LAYOUT AND DELIVERABLES — BookBridge API

*Final file tree, configuration, tooling, documentation and submission checklist*

## Final Repository Tree

This extends the tree in CODEX. Additional files are allowed; the listed responsibilities are not negotiable (routes thin, client fetches, parser extracts, service orchestrates, schemas define the contract).

```
bookbridge-api/
  README.md
  LIMITATIONS.md                 short note (about 1 page)
  REVERSE_ENGINEERING_NOTES.md
  pyproject.toml                 ruff + pytest config
  requirements.txt               exact tested runtime versions
  requirements-dev.txt           pytest, pytest-asyncio, respx, ruff
  Dockerfile  .dockerignore  .env.example  .gitignore  Makefile
  .github/workflows/ci.yml
  docs/spec-pack/                the 12 spec documents (markdown)
  src/
    __init__.py  main.py  config.py  exceptions.py  cache.py
    api/        __init__.py  routes.py  deps.py  errors.py
    clients/    __init__.py  catalogue.py
    services/   __init__.py  books.py  index.py
    parsers/    __init__.py  books.py  categories.py
    schemas/    __init__.py  books.py  errors.py
  tests/
    __init__.py  conftest.py
    fixtures/site/...            mirrors real URL layout
    test_parsers.py  test_cache.py  test_client.py
    test_service.py  test_api.py  test_errors.py
  scripts/
    test_api.py                  standalone evaluator
    fake_upstream.py             local fake upstream for fault scenarios
```

## Configuration (pydantic-settings, prefix BOOKBRIDGE_)

| Variable | Default | Purpose |
| --- | --- | --- |
| `UPSTREAM_BASE_URL` | `https://books.toscrape.com` | Source site (overridable for the fake upstream). |
| `USER_AGENT` | `BookBridgeAPI/1.0 (educational demo; contact: you@example.com)` | Honest, descriptive UA. |
| `CONNECT_TIMEOUT_SECONDS` | 3 | httpx connect timeout. |
| `READ_TIMEOUT_SECONDS` | 8 | httpx read timeout. |
| `MAX_RETRIES` | 2 | Retries after the first attempt. |
| `RETRY_BACKOFF_SECONDS` | 0.5 | Base for exponential backoff. |
| `MAX_CONCURRENT_REQUESTS` | 4 | Global upstream concurrency cap. |
| `MIN_REQUEST_INTERVAL_SECONDS` | 0.1 | Minimum gap between request starts. |
| `DETAIL_CACHE_TTL_SECONDS` | 300 | Per-book detail cache. |
| `INDEX_TTL_SECONDS` | 900 | Catalogue index lifetime. |
| `INDEX_WARMUP_ON_STARTUP` | false | Background index build at startup. |
| `RESPECT_ROBOTS_TXT` | true | Check robots.txt once. |
| `LOG_LEVEL` | INFO | Logging level. |

A ready-made `.env.example` with exactly these keys is included in the pack. The application must start with no `.env` file present.

## Dependencies

- Runtime: fastapi, uvicorn[standard], httpx, beautifulsoup4 (use the built-in `html.parser` backend, no lxml), pydantic>=2, pydantic-settings.
- Dev: pytest, pytest-asyncio, respx, ruff.
- Pin the exact versions that were installed and tested in `requirements.txt` and `requirements-dev.txt`.

## Dockerfile Requirements

- Base `python:3.12-slim`; install from requirements.txt; copy `src/` only; run as a non-root user; `PYTHONUNBUFFERED=1`.
- `HEALTHCHECK` using Python's `urllib` against `/health`. `CMD` runs `uvicorn src.main:app --host 0.0.0.0 --port 8000`.
- `.dockerignore` excludes `.git`, `.venv`, `__pycache__`, `tests`, `docs`.

## Makefile Targets

| Target | Command |
| --- | --- |
| `install` | Create `.venv`, install requirements and dev requirements. |
| `run` | `uvicorn src.main:app --reload` |
| `test` | `pytest -q` |
| `lint` | `ruff check .` and `ruff format --check .` |
| `evaluate` | `python scripts/test_api.py --base-url http://localhost:8000` |
| `docker-build` / `docker-run` | Build image `bookbridge-api` and run it on port 8000. |

## CI (GitHub Actions)

`.github/workflows/ci.yml`: on push and pull request, Python 3.12, install dev requirements, `ruff check`, `pytest -q`, and a `docker build` step. CI must never call the live website.

## README Outline

1. One-paragraph summary and the compliance statement (public, unauthenticated pages only; no bypass).
2. Quick start (venv, install, run) and Docker quick start, using only verified commands.
3. Endpoint table with `curl` examples and sample responses.
4. Configuration table (copy of the table above) and error envelope with status mapping.
5. How to run pytest (offline) and the evaluator (what it covers, how fault scenarios work).
6. Project structure and layer responsibilities.
7. Design notes: catalogue index strategy, caching, retries, politeness.
8. Link to LIMITATIONS.md and REVERSE_ENGINEERING_NOTES.md.

## LIMITATIONS.md (short note, 350 words max)

Required by the assignment. Structure: What this is (2 sentences); Limitations (5 bullets: depends on HTML presentation layer; first request builds an index from about 70 pages; staleness and no freshness guarantee; displayed data may not equal underlying data; source policy may change); Why this is fragile (markup, URLs, pagination change silently); Appropriate long-term fix (an official documented API or authorized data feed, or a partnership with agreed contract, authentication, quotas, versioning, availability and change notifications); Do not circumvent (no CAPTCHA/proxy/rate-limit evasion); Migration path in 5 short steps (as in doc 07).

## Submission Checklist

| Item | How to verify |
| --- | --- |
| All six endpoints implemented | Evaluator L01-L18 pass; `/docs` lists all six. |
| Validation and error envelope | Evaluator V01-V12, N01-N05; `tests/test_errors.py` passes. |
| Controlled upstream failures | Evaluator F01-F10; client tests for timeout, 5xx, 403, 429. |
| Offline tests | Run `pytest -q` with networking disabled; passes. |
| Evaluator works and exits non-zero on failure | Run it against a stopped server (exit 2) and against a deliberately broken run (exit 1). |
| Docker builds and starts | `docker build`, `docker run`, `curl /health`. |
| Docs match implementation | Re-run every README command once. |
| Public-data-only compliance | Grep for cookies, proxies, user-agent spoofing, form submission, login: none present. |
| Short limitations note present | `LIMITATIONS.md` exists and is under 350 words. |

---
BookBridge API • Razorpay Reverse-Engineering Assignment
