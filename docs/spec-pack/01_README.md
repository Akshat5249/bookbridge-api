**README — BookBridge API**

*Project overview, setup, evaluation and submission guide*

# Project Summary

BookBridge API converts publicly accessible product pages from Books to Scrape into a clean JSON REST API. It demonstrates reverse-engineering of a public website without authentication, private data, access-control bypasses, CAPTCHA evasion or aggressive crawling.

Recommended stack: Python 3.12+, FastAPI, httpx, BeautifulSoup4, Pydantic v2, pytest and Docker.

# Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /health | Health check |
| GET | /api/v1/books | List/filter books |
| GET | /api/v1/books/{id} | Book details |
| GET | /api/v1/search?q=... | Search titles |
| GET | /api/v1/categories | List categories |
| GET | /api/v1/categories/{slug}/books | Category books |

# Local Setup

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload

Open /docs for generated Swagger/OpenAPI documentation.

# Evaluation

python scripts/test_api.py --base-url http://localhost:8000

The evaluator should test success cases, validation, not-found behavior and controlled upstream failures, and exit non-zero if a required case fails.

# Engineering Expectations

Separate routes, service logic, HTTP fetching, HTML parsing and Pydantic schemas.

Use explicit timeouts, bounded retries and conservative request volume.

Use fixture-based parser tests so CI does not repeatedly hit the source website.

Provide Dockerfile, .env.example, tests and exact run commands.


---
BookBridge API • Razorpay Reverse-Engineering Assignment
