"""Thin REST routes: validation, orchestration and documented response models."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BeforeValidator, Field

from src.api.deps import Page, Service
from src.schemas.books import (
    BookDetailResponse,
    BookListResponse,
    CategoriesResponse,
    HealthResponse,
)
from src.schemas.errors import ErrorResponse

ERRORS = {status: {"model": ErrorResponse} for status in (404, 405, 422, 500, 502, 504)}
router = APIRouter(responses=ERRORS)
Money = Annotated[Decimal, Query(ge=0, allow_inf_nan=False)]
SearchTerm = Annotated[
    str,
    BeforeValidator(lambda value: value.strip() if isinstance(value, str) else value),
    Field(min_length=1, max_length=100),
]


@router.get(
    "/health", response_model=HealthResponse, tags=["Health"], summary="Check local service health"
)
async def health(request: Request) -> HealthResponse:
    """Return local process and index health without fetching upstream data."""
    return HealthResponse(index=request.app.state.book_service.index.health())


@router.get(
    "/api/v1/books",
    response_model=BookListResponse,
    tags=["Books"],
    summary="List and filter the catalogue",
)
async def list_books(
    service: Service,
    paging: Page,
    min_price: Money | None = None,
    max_price: Money | None = None,
    rating: Annotated[int | None, Query(ge=1, le=5)] = None,
) -> BookListResponse:
    """Filter with inclusive price bounds and exact rating using AND semantics."""
    if min_price is not None and max_price is not None and min_price > max_price:
        raise RequestValidationError(
            [{"loc": ("query", "max_price"), "msg": "must be >= min_price", "type": "value_error"}]
        )
    return await service.list_books(
        *paging, min_price=min_price, max_price=max_price, rating=rating
    )


@router.get(
    "/api/v1/books/{id}",
    response_model=BookDetailResponse,
    tags=["Books"],
    summary="Fetch one book's full details",
)
async def detail(id: str, service: Service) -> BookDetailResponse:
    """Return 404 for malformed IDs before constructing any upstream URL."""
    return BookDetailResponse(data=await service.detail(id))


@router.get(
    "/api/v1/search",
    response_model=BookListResponse,
    tags=["Search"],
    summary="Search titles by substring",
)
async def search(
    service: Service, paging: Page, q: Annotated[SearchTerm, Query(examples=["light"])]
) -> BookListResponse:
    """Trim the query then match case-insensitively across the complete index."""
    return await service.list_books(*paging, query=q)


@router.get(
    "/api/v1/categories",
    response_model=CategoriesResponse,
    tags=["Categories"],
    summary="List sidebar categories",
)
async def categories(service: Service) -> CategoriesResponse:
    """Exclude the top-level Books node and preserve sidebar order."""
    return CategoriesResponse(data=await service.categories())


@router.get(
    "/api/v1/categories/{slug}/books",
    response_model=BookListResponse,
    tags=["Categories"],
    summary="List books in a category",
)
async def category_books(slug: str, service: Service, paging: Page) -> BookListResponse:
    """Map public slugs from the index; never guess an upstream folder."""
    return await service.list_books(*paging, category_slug=slug)
