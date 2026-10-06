"""Typed service and pagination dependencies for thin route handlers."""

from typing import Annotated

from fastapi import Depends, Query, Request

from src.services.books import BookService


def book_service(request: Request) -> BookService:
    """Resolve the lifespan-owned service."""
    return request.app.state.book_service


def pagination(
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 20
) -> tuple[int, int]:
    """Validate common pagination consistently across all list endpoints."""
    return page, page_size


Service = Annotated[BookService, Depends(book_service)]
Page = Annotated[tuple[int, int], Depends(pagination)]
