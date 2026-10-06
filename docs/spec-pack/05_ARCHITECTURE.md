**Architecture — BookBridge API**

*Components, flow, resilience and rationale*

# System Flow

API Consumer
    |
FastAPI Routes
    |
Service Layer ----> Short TTL Cache
    |
Catalogue HTTP Client
    |
Public Website HTML
    |
Parser / Normalizer
    |
Pydantic Response

# Responsibilities

## Routes

Validate HTTP inputs and serialize documented responses.

## Services

Coordinate pagination, filters, search, caching and providers.

## HTTP Client

Fetch public pages with explicit timeout, bounded retry and configured User-Agent. Never circumvent rejected requests.

## Parser

Convert HTML to structured records and remain independently fixture-testable.

## Cache

Short-lived in-process cache to reduce duplicate upstream requests during a demo.

# Error Mapping

Timeout -> HTTP 504
Upstream 5xx / critical parse failure -> HTTP 502
Missing resource -> HTTP 404
Validation -> HTTP 422

# Design Rationale

Upstream HTML changes remain localized to parser/client code.

Tests stay deterministic and fast.

Consumers never depend directly on CSS classes or page markup.

The architecture clearly demonstrates the fragility of an implicit reverse-engineered contract.


---
BookBridge API • Razorpay Reverse-Engineering Assignment
