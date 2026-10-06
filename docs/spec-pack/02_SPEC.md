**SPEC — BookBridge API**

*Functional requirements and acceptance criteria*

# Objective

Build a read-only API over publicly accessible Books to Scrape catalogue pages. Fetch public HTML, extract product information, normalize it, and expose a stable REST contract.

# Scope and Boundaries

Unauthenticated public pages only.

No login, purchasing, form mutation, CAPTCHA bypass, proxy rotation or rate-limit evasion.

If access is denied, return a controlled error rather than circumventing the restriction.

# Normalized Book Schema

{
  "id": "a-light-in-the-attic_1000",
  "title": "A Light in the Attic",
  "price": 51.77,
  "currency": "GBP",
  "rating": 3,
  "availability": "in_stock",
  "stock_count": 22,
  "category": "Poetry",
  "upc": "a897fe39b1053632",
  "description": "...",
  "image_url": "https://...",
  "product_url": "https://..."
}

# Endpoint Behavior

## GET /health

Return 200 and service status.

## GET /api/v1/books

Support page, page_size, min_price, max_price and rating. page >=1; page_size 1..50; rating 1..5; min_price <= max_price.

## GET /api/v1/books/{id}

Return normalized details or 404.

## GET /api/v1/search

Require non-empty q; case-insensitive title matching; support pagination.

## GET /api/v1/categories

Return category name and slug.

## GET /api/v1/categories/{slug}/books

Return category books or 404 for unknown category.

# Errors

| Situation | HTTP |
| --- | --- |
| Invalid input | 422 |
| Not found | 404 |
| Upstream timeout | 504 |
| Upstream unusable/failure | 502 |
| Unexpected internal error | 500 |

{
  "error": {
    "code": "UPSTREAM_UNAVAILABLE",
    "message": "The upstream catalogue could not be reached.",
    "details": null
  }
}

# Acceptance Criteria

Fresh clone installs and starts using documented commands.

All endpoints are documented in OpenAPI.

pytest passes without requiring internet.

Standalone evaluator passes against a running instance.

Network/parser failures produce controlled JSON errors.

No private data, secrets or access-control bypass exists.


---
BookBridge API • Razorpay Reverse-Engineering Assignment
