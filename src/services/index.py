"""Lazy, single-flight catalogue snapshots with atomic refresh and stale-if-error."""

import asyncio
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType
from urllib.parse import urlsplit

from src.clients.catalogue import CatalogueClient
from src.config import Settings
from src.exceptions import BookBridgeError, UpstreamParseError
from src.parsers.books import parse_listing
from src.parsers.categories import CategoryLink, parse_categories
from src.schemas.books import BookSummary, Category, IndexHealth

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    """Immutable whole-catalogue view replaced only after a complete build."""

    books: tuple[BookSummary, ...]
    by_id: Mapping[str, BookSummary]
    categories: tuple[Category, ...]
    category_urls: Mapping[str, str]
    built_at: float


class CatalogueIndex:
    """One lazy index per application process; health reads local state only."""

    def __init__(
        self, client: CatalogueClient, settings: Settings, clock: Callable[[], float] = monotonic
    ) -> None:
        self.client, self.settings, self.clock = client, settings, clock
        self.snapshot: Snapshot | None = None
        self._lock = asyncio.Lock()
        self._failed_at: float | None = None
        self._task: asyncio.Task[Snapshot] | None = None

    def health(self) -> IndexHealth:
        """Return snapshot age and staleness without triggering any HTTP request."""
        snapshot = self.snapshot
        age = max(0, self.clock() - snapshot.built_at) if snapshot else None
        return IndexHealth(
            loaded=snapshot is not None,
            stale=age is not None and age >= self.settings.index_ttl_seconds,
            age_seconds=age,
            books=len(snapshot.books) if snapshot else 0,
        )

    async def get(self) -> Snapshot:
        """Serialize builds; on refresh failure retain and serve the old snapshot."""
        if self.snapshot and not self.health().stale:
            return self.snapshot
        async with self._lock:
            if self.snapshot and (
                not self.health().stale
                or (self._failed_at is not None and self.clock() - self._failed_at < 30)
            ):
                return self.snapshot
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._refresh())
            task = self._task
        return await asyncio.shield(task)

    async def close(self) -> None:
        """Cancel an in-flight build before the shared HTTP client closes."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _refresh(self) -> Snapshot:
        try:
            fresh = await self._build()
        except BookBridgeError:
            if self.snapshot is None:
                raise
            self._failed_at = self.clock()
            logger.warning("Catalogue refresh failed; serving stale snapshot")
            return self.snapshot
        self.snapshot, self._failed_at = fresh, None
        return fresh

    async def _category_books(self, link: CategoryLink) -> tuple[BookSummary, ...]:
        books = []
        url: str | None = link.url
        seen = set()
        folder = urlsplit(link.url).path.rsplit("/", 1)[0]
        while url:
            self.client.validate_url(url)
            path = urlsplit(url).path
            if (
                url in seen
                or len(seen) >= 100
                or not re.fullmatch(re.escape(folder) + r"/(?:index|page-\d+)\.html", path)
            ):
                raise UpstreamParseError()
            seen.add(url)
            html = await self.client.fetch(url)
            batch, url = parse_listing(html, url, link.category.name)
            for book in batch:
                self.client.validate_url(book.product_url)
            books.extend(batch)
        return tuple(books)

    async def _build(self) -> Snapshot:
        home = self.settings.upstream_base_url + "/"
        links = parse_categories(await self.client.fetch(home), home)
        tasks = [asyncio.create_task(self._category_books(link)) for link in links]
        try:
            groups = await asyncio.gather(*tasks)
        except (BookBridgeError, asyncio.CancelledError):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        by_id = {book.id: book for group in groups for book in group}
        books = tuple(
            sorted(by_id.values(), key=lambda book: int(book.id.rsplit("_", 1)[1]), reverse=True)
        )
        return Snapshot(
            books,
            MappingProxyType(by_id),
            tuple(link.category for link in links),
            MappingProxyType({link.category.slug: link.url for link in links}),
            self.clock(),
        )
