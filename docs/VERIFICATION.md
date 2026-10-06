# Verification report — 7 October 2026

## Delivered files

- Application: every package in `src/`, app factory/lifespan, configuration, bounded
  TTL cache, HTTP client, pure parsers, immutable index, service orchestration,
  schemas, API routes, centralized errors and request-id logging.
- Tests: parser/cache/client/service/API/error tests, network guards, synthetic
  60-book/40-category fixture mini-site and three saved public HTML regressions.
- Evaluator: standard-library `scripts/test_api.py` and `scripts/fake_upstream.py`.
- Tooling: pinned runtime/dev requirements, Python 3.12 pyproject, Makefile,
  Dockerfile, dockerignore, gitignore and GitHub Actions CI.
- Documentation: README, short limitations (261 words), reverse-engineering
  notes, implementation decisions and these verification logs. Original master
  prompt, twelve specs and `.env.example` preserved.

## Commands and outcomes

Commands run from repo root. Activated-venv commands are equivalent to their
`.venv/bin/` paths. Final checks were also performed through Makefile targets.

| Exact command | Outcome |
| --- | --- |
| `python3.12 -m venv .venv` | Passed |
| `source .venv/bin/activate` | Passed |
| `python -m pip install -r requirements-dev.txt` | Passed with exact pinned versions |
| `python -m pip install -r requirements.txt` | Passed |
| `.venv/bin/python -m pip check` | No broken requirements |
| `pytest -q` | 80 passed; outbound sockets blocked, upstream requests mocked |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| `python scripts/fake_upstream.py --port 8765` | Started loopback-only fixture server |
| `BOOKBRIDGE_UPSTREAM_BASE_URL=http://127.0.0.1:8765 uvicorn src.main:app --reload` | Started; health and API checks passed |
| `python scripts/test_api.py --base-url http://localhost:8000` | 46 passed, 0 failed, 0 skipped, exit 0 |
| `python scripts/test_api.py --base-url http://localhost:8000 --skip-fault-scenarios` | 36 passed, 10 explicit skips, exit 0 |
| `python scripts/test_api.py --json` | 46 passed; JSON summary validated; exit 0 |
| `.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8001` | Started real-site verification server |
| `.venv/bin/python scripts/test_api.py --base-url http://127.0.0.1:8001 --skip-fault-scenarios` | 36 live passes, 10 fault skips (already tested offline), exit 0 |
| `make install`, `make test`, `make lint`, `make evaluate` | Passed; evaluate 46/46 |
| `BOOKBRIDGE_UPSTREAM_BASE_URL=http://127.0.0.1:8765 make run` | Started; local health verified |
| `docker version` | Client installed; Docker subsequently verified on the user's machine |
| `docker build -t bookbridge-api .` | Passed on the user's machine |
| `docker run --rm -p 8000:8000 bookbridge-api` | Passed on the user's machine |
| Container `/health` | Passed on the user's machine |
| Docker HEALTHCHECK | Reports `healthy`, verified on the user's machine |
| Container runtime user | `bookbridge` (non-root), verified on the user's machine |
| Evaluator against the container | Passed on the user's machine |

All six exact README `curl -sS` commands returned successful JSON against local
fixtures. The live evaluator made its single permitted full-index run (~11.3s
warmup). Normal pytest and CI do not request the public website.

Deliberate evaluator exit verification used `/tmp/bookbridge_exit_checks.py`: a
throwaway loopback HTTP server returned intentionally broken JSON contracts.
The evaluator returned **1** with expected-vs-actual diagnostics; after closing
the server, the same evaluator returned **2**, including the startup hint.
Neither case modified the app or weakened a test.

Logs:

- [Complete offline evaluator](evaluator-offline.log)
- [Single live evaluator run](evaluator-live.log)
- [Deliberately broken service](evaluator-deliberately-broken.log)
- [Stopped service](evaluator-stopped.log)

## Conflicts, assumptions and practical limits

Followed SPEC > CODEX > DESIGN_DECISIONS and the master's supersession of doc 08.
The abbreviated detail in doc 04 is expanded to the full SPEC schema. Malformed
book IDs return 404 per D3; both price bounds are nonnegative. Decimal is retained
internally, but numeric JSON cannot promise trailing zeros. The fixture minimum
was expanded to satisfy evaluator checks for 50 books/page and 40 categories.
The index includes a 30-second failed-refresh cooldown and shares concurrent
failures without caching them for future requests. URL checks are stricter than
the same-host minimum: same origin, no credentials, traversal or query strings.

Development capture saved home, Poetry and Science Fiction HTML. The guessed
Science Fiction second page returned 404, so capture stopped; it has 16 books
and no next link. Five total capture requests included robots.txt, within the
specified budget. This optional capture failure is recorded, not presented as
successful. Synthetic fixtures cover detail markup and multi-page categories;
the live evaluator separately verified the golden detail page. No parser changes
were needed for real HTML.

Docker build/run, container `/health`, HEALTHCHECK (`healthy`), the non-root user
(`bookbridge`) and the evaluator against the container were verified on the user's
machine. GitHub-hosted CI has not run. Browser DevTools network inspection was
not performed; no claim is made that hidden JSON endpoints are impossible.
Remaining integration risks and the authorized long-term fix are in
[../LIMITATIONS.md](../LIMITATIONS.md).

## Compliance self-audit

Reviewed Python sources with rg for cookies, proxies, spoofing, HTTP mutations,
login, headless tools, fault hooks, TODO/FIXME and placeholders. Matches are the
reject-all-cookie policy, disabled proxy handling, immutable MappingProxyType,
local-only fault scripts, and the API's method-rejection test. The application
contains no fault controls, debug routes, form submission, authentication,
browser automation, proxy rotation or private endpoints. Synthetic cookie text
in tests is not a credential. No secrets or private/user data are included.
All application source functions have argument and return annotations.

Source access uses public unauthenticated GETs only; robots denial, 403 and 429
produce controlled failures without retry or evasion. No access restriction was
bypassed. Original spec documents and `.env.example` have no diff.
