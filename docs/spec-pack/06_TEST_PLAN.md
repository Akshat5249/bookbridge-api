**Test Plan — BookBridge API**

*Automated tests, evaluator scenarios and quality gates*

# Strategy

Use saved HTML fixtures and mocked HTTP for deterministic tests. Keep the live evaluator small and reviewer-friendly.

# Parser Tests

Catalogue title, price, rating, availability, URL and image.

Detail UPC, category, description and stock count.

Relative URL resolution.

Missing optional fields.

Structurally unusable HTML.

# API Cases

| Case | Expected |
| --- | --- |
| GET /health | 200 |
| GET /api/v1/books | 200 + pagination |
| page=0 | 422 |
| page_size=1000 | 422 |
| rating=6 | 422 |
| min_price > max_price | 422 |
| empty q | 422 |
| unknown book | 404 |
| unknown category | 404 |
| mock timeout | 504 |
| mock upstream 500 | 502 |

# Search / Filter Cases

Case-insensitive title search.

No results returns empty data.

Inclusive min/max price boundaries.

Exact rating filter.

# Evaluator

python scripts/test_api.py --base-url http://localhost:8000

Print PASS/FAIL per scenario, use short timeouts, and exit 0 only if all required scenarios pass.

# Quality Gates

pytest -q succeeds.

Normal automated tests require no internet.

Live evaluator makes only modest requests.

Failure output clearly shows expected and actual behavior.


---
BookBridge API • Razorpay Reverse-Engineering Assignment
