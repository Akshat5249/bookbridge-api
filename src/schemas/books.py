"""Normalized immutable public response models."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class BookSummary(BaseModel):
    """Fields available on public category listing pages."""

    model_config = ConfigDict(frozen=True)
    id: str
    title: str
    price: Decimal = Field(ge=0, examples=[51.77])
    currency: Literal["GBP"] = "GBP"
    rating: int = Field(ge=1, le=5)
    availability: Literal["in_stock", "out_of_stock", "unknown"]
    category: str
    image_url: str | None
    product_url: str

    @field_serializer("price", when_used="json", return_type=float)
    def serialize_price(self, value: Decimal) -> float:
        """Expose money as a JSON number while retaining Decimal internally."""
        return float(value)


class BookDetail(BookSummary):
    """Additional fields fetched only from a requested detail page."""

    stock_count: int | None = Field(default=None, ge=0)
    upc: str | None = None
    description: str | None = None


class Pagination(BaseModel):
    """Pagination after filtering; pages beyond the end are empty."""

    page: int
    page_size: int
    total: int
    has_next: bool


class BookListResponse(BaseModel):
    """Paginated summary envelope."""

    data: list[BookSummary]
    pagination: Pagination


class BookDetailResponse(BaseModel):
    """Detail envelope."""

    data: BookDetail


class Category(BaseModel):
    """Public sidebar category."""

    model_config = ConfigDict(frozen=True)
    name: str
    slug: str


class CategoriesResponse(BaseModel):
    """Categories in original sidebar order."""

    data: list[Category]


class IndexHealth(BaseModel):
    """Local index state; reading this never requests upstream pages."""

    loaded: bool
    stale: bool
    age_seconds: float | None
    books: int


class HealthResponse(BaseModel):
    """Process health and educational service metadata."""

    status: str = "ok"
    service: str = "bookbridge-api"
    version: str = "1.0.0"
    index: IndexHealth
