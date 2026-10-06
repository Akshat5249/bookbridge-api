**Initial Codex Prompt**

*Master prompt to start repository generation*

# Copy This Into Codex

Build the BookBridge API repository using all supplied specification documents.

Read in this priority:
1. SPEC
2. CODEX Implementation Instructions
3. API Contract
4. Architecture
5. Test Plan
6. Limitations
7. README

Goal:
Create a polished take-home assignment exposing a REST API over publicly accessible Books to Scrape catalogue pages.

Boundaries:
- Public unauthenticated information only.
- Never bypass authentication, CAPTCHA, bot protection, rate limits, paywalls, or access controls.
- Never collect private/user data.
- Never use proxy rotation, stealth automation, credential/session harvesting, or privileged endpoints.
- If upstream access is denied, fail gracefully and document it.

Stack:
Python 3.12+, FastAPI, httpx async, BeautifulSoup4, Pydantic v2, pytest with HTTP mocks and saved HTML fixtures, Docker.

Required endpoints:
GET /health
GET /api/v1/books
GET /api/v1/books/{id}
GET /api/v1/search
GET /api/v1/categories
GET /api/v1/categories/{slug}/books

Keep routes thin. Separate client, parser, service, schemas and exception mapping.
Implement explicit timeouts, bounded retries, validation, normalized errors and a short TTL cache where useful.

Testing:
Normal pytest must not depend on the live website. Use fixtures and mocks.
The standalone scripts/test_api.py evaluator may exercise the running service with a modest number of public requests.

Work autonomously:
1. Inspect all specs.
2. Create the complete repository.
3. Implement the application.
4. Add fixtures and tests.
5. Run tests and fix failures.
6. Validate Docker if available.
7. Verify README commands.
8. Remove critical TODOs/placeholders.
9. Perform a compliance/self-review.
10. Finish with a concise summary of files created, tests run and remaining limitations.

Do not stop after scaffolding. Deliver a runnable, tested submission.

# Completion Checklist

All six routes work.

pytest passes offline.

Evaluator exists and works.

Dockerfile and .env.example exist.

Documentation matches actual implementation.

No prohibited access behavior exists.


---
BookBridge API • Razorpay Reverse-Engineering Assignment
