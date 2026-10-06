**API Contract — BookBridge API**

*Endpoint and response contract*

# Base

Local base URL: http://localhost:8000. API prefix: /api/v1. JSON responses only.

# List Books

GET /api/v1/books?page=1&page_size=20&min_price=10&max_price=40&rating=5

Return data[] and pagination. Filters are optional; invalid combinations return 422.

# Book Details

GET /api/v1/books/a-light-in-the-attic_1000

{
  "data": {
    "id": "a-light-in-the-attic_1000",
    "title": "A Light in the Attic",
    "price": 51.77,
    "currency": "GBP",
    "rating": 3,
    "availability": "in_stock",
    "category": "Poetry"
  }
}

# Search and Categories

GET /api/v1/search?q=light&page=1&page_size=20
GET /api/v1/categories
GET /api/v1/categories/poetry/books?page=1&page_size=20

# Pagination Envelope

{
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1000,
    "has_next": true
  }
}

# Validation

| Parameter | Rule |
| --- | --- |
| page | >= 1 |
| page_size | 1..50 |
| rating | 1..5 |
| min_price | >= 0 |
| max_price | >= min_price |
| q | non-empty |

# Error Codes

| Code | Meaning |
| --- | --- |
| VALIDATION_ERROR | Bad client input |
| NOT_FOUND | Resource not found |
| UPSTREAM_TIMEOUT | Source timed out |
| UPSTREAM_UNAVAILABLE | Source unusable/unavailable |
| INTERNAL_ERROR | Unexpected failure |


---
BookBridge API • Razorpay Reverse-Engineering Assignment
