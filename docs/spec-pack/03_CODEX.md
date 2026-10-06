**CODEX — Implementation Instructions**

*Authoritative engineering instructions for Codex*

# Role

Implement a polished take-home assignment. Prioritize correctness, readability, testability and reviewer experience. Treat SPEC and this document as authoritative.

# Required Stack

Python 3.12+; FastAPI/Uvicorn.

httpx AsyncClient; BeautifulSoup4.

Pydantic v2 / pydantic-settings.

pytest + pytest-asyncio + respx or equivalent HTTP mocking.

# Architecture

src/
  main.py
  config.py
  api/routes.py
  clients/catalogue.py
  services/books.py
  parsers/books.py
  schemas/books.py
  exceptions.py

tests/
  fixtures/
  test_api.py
  test_parsers.py
scripts/
  test_api.py

Routes must not parse HTML. Client owns fetching; parser owns extraction; service orchestrates; schemas define the public contract.

# Non-Negotiable Safety Rules

Use only pages available to an ordinary unauthenticated visitor.

Never bypass authentication, paywalls, CAPTCHA, WAF/bot controls or rate limits.

Never rotate proxies, spoof sessions, harvest cookies/credentials or use stealth techniques.

Never collect private/user data.

If blocked, fail gracefully and document the limitation.

# Implementation Rules

Explicit connect/read timeout and bounded retries.

Descriptive educational/demo User-Agent.

Safely resolve relative URLs.

Normalize price/currency and rating.

Parser functions deterministic and network-free.

Central exception-to-HTTP mapping.

Optional short TTL in-memory cache to reduce duplicate requests.

# Testing Rules

Normal pytest suite must make no live upstream calls.

Store representative public HTML fixtures.

Mock timeout, 404 and 5xx cases.

Test missing/malformed HTML fields.

Standalone evaluator may make a modest number of public requests through the local API.

# Definition of Done

Implement every endpoint in SPEC.

Implement validation and error cases.

All tests pass.

Evaluator passes.

Docker image builds and app starts.

Docs match implementation.

No critical TODO placeholders.

Self-review confirms public-data-only compliance.


---
BookBridge API • Razorpay Reverse-Engineering Assignment
