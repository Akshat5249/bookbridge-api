"""Catalogue filtering, search, pagination and cached on-demand details."""

from decimal import Decimal

from src.cache import TTLCache
from src.clients.catalogue import CatalogueClient
from src.config import Settings
from src.exceptions import NotFound
from src.parsers.books import BOOK_ID, parse_detail
from src.schemas.books import BookDetail, BookListResponse, BookSummary, Category, Pagination
from src.services.index import CatalogueIndex


class BookService:
    """Orchestrate normalized data without leaking HTML concerns into routes."""

    def __init__(self, client: CatalogueClient, index: CatalogueIndex, settings: Settings) -> None:
        self.client, self.index, self.settings = client, index, settings
        self.details = TTLCache[str, BookDetail](settings.detail_cache_ttl_seconds)

    async def detail(self, ident: str) -> BookDetail:
        """Validate before forming a URL; cache successes only."""
        if not BOOK_ID.fullmatch(ident) or len(ident) > 300:
            raise NotFound()
        cached = self.details.get(ident)
        if cached:
            return cached
        url = self.settings.upstream_base_url + f"/catalogue/{ident}/index.html"
        book = parse_detail(await self.client.fetch(url, detail=True), url)
        self.details.set(ident, book)
        return book

    async def categories(self) -> list[Category]:
        """List categories in upstream sidebar order."""
        return list((await self.index.get()).categories)

    async def list_books(
        self,
        page: int = 1,
        page_size: int = 20,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        rating: int | None = None,
        query: str | None = None,
        category_slug: str | None = None,
    ) -> BookListResponse:
        """Apply inclusive AND filters before pagination in descending numeric order."""
        snapshot = await self.index.get()
        category = None
        if category_slug is not None:
            category = next((c.name for c in snapshot.categories if c.slug == category_slug), None)
            if category is None:
                raise NotFound()
        books = [
            book
            for book in snapshot.books
            if (min_price is None or book.price >= min_price)
            and (max_price is None or book.price <= max_price)
            and (rating is None or book.rating == rating)
            and (query is None or query.casefold() in book.title.casefold())
            and (category is None or book.category == category)
        ]
        return paginate(books, page, page_size)


def paginate(books: list[BookSummary], page: int, page_size: int) -> BookListResponse:
    """Represent empty and out-of-range pages with a stable envelope."""
    total = len(books)
    start = (page - 1) * page_size
    return BookListResponse(
        data=books[start : start + page_size],
        pagination=Pagination(
            page=page, page_size=page_size, total=total, has_next=page * page_size < total
        ),
    )
