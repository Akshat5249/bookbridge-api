"""Whole-index, stale fallback, filters, search and on-demand detail caching."""

import asyncio
from decimal import Decimal

import httpx
import pytest
import respx

from src.clients.catalogue import CatalogueClient
from src.config import Settings
from src.exceptions import NotFound, UpstreamParseError, UpstreamUnavailable
from src.services.books import BookService
from src.services.index import CatalogueIndex
from tests.conftest import BASE, SITE


def settings() -> Settings:
    return Settings(min_request_interval_seconds=0, retry_backoff_seconds=0, max_retries=0)


async def test_index_singleflight_and_refresh(site_router: respx.MockRouter) -> None:
    now = [0.0]
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(settings(), http)
        index = CatalogueIndex(client, settings(), lambda: now[0])
        assert not index.health().loaded
        snapshots = await asyncio.gather(*(index.get() for _ in range(8)))
        assert all(s is snapshots[0] for s in snapshots)
        assert len(snapshots[0].books) == 60
        assert len(site_router.calls) == 43  # robots + home + 41 category pages
        with pytest.raises(TypeError):
            snapshots[0].by_id["new"] = snapshots[0].books[0]  # type: ignore[index]
        now[0] = 901
        home_route = site_router.get(BASE + "/").respond(500)
        assert await index.get() is snapshots[0]
        assert index.health().stale
        count = len(site_router.calls)
        assert await index.get() is snapshots[0]
        assert len(site_router.calls) == count
        now[0] = 932
        home_route.respond(200, content=(SITE / "index.html").read_bytes())
        assert await index.get() is not snapshots[0]
        assert not index.health().stale


async def test_service_filters_search_and_detail(site_router: respx.MockRouter) -> None:
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(settings(), http)
        service = BookService(client, CatalogueIndex(client, settings()), settings())
        result = await service.list_books()
        assert result.pagination.total == 60 and len(result.data) == 20
        second = await service.list_books(page=2)
        assert not {b.id for b in result.data} & {b.id for b in second.data}
        filtered = await service.list_books(min_price=Decimal("10"), max_price=Decimal("40"))
        assert all(Decimal("10") <= b.price <= Decimal("40") for b in filtered.data)
        for price in ("10", "40"):
            exact = await service.list_books(min_price=Decimal(price), max_price=Decimal(price))
            assert exact.data and all(b.price == Decimal(price) for b in exact.data)
        combined = await service.list_books(
            rating=3, min_price=Decimal("10"), max_price=Decimal("60")
        )
        assert combined.data and all(
            b.rating == 3 and Decimal("10") <= b.price <= Decimal("60") for b in combined.data
        )
        lower = await service.list_books(query="light")
        upper = await service.list_books(query="LIGHT")
        assert lower == upper and lower.pagination.total == 2
        assert (await service.list_books(query="zzzxqjkw")).pagination.total == 0
        assert not (await service.list_books(page=999)).data
        poetry = await service.list_books(category_slug="poetry", page_size=50)
        assert poetry.pagination.total == 21 and all(b.category == "Poetry" for b in poetry.data)
        assert (await service.categories())[1].slug == "science-fiction"
        with pytest.raises(NotFound):
            await service.list_books(category_slug="no-such-category")
        count = len(site_router.calls)
        with pytest.raises(NotFound):
            await service.detail("../../etc")
        assert len(site_router.calls) == count
        first = await service.detail(result.data[0].id)
        assert await service.detail(first.id) is first
        assert len(site_router.calls) == count + 1


async def test_failed_build_and_detail_not_cached(offline_guard: respx.MockRouter) -> None:
    offline_guard.get(BASE + "/robots.txt").respond(404)
    route = offline_guard.get(BASE + "/").respond(500)
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(settings(), http)
        index = CatalogueIndex(client, settings())
        with pytest.raises(UpstreamUnavailable):
            await index.get()
        assert not index.health().loaded
        route.respond(200, text="<h1>Maintenance</h1>")
        with pytest.raises(UpstreamParseError):
            await index.get()
        service = BookService(client, index, settings())
        detail = offline_guard.get(BASE + "/catalogue/book_1/index.html").respond(500)
        for _ in range(2):
            with pytest.raises(UpstreamUnavailable):
                await service.detail("book_1")
        assert detail.call_count == 2


async def test_pagination_cycle_rejected(site_router: respx.MockRouter) -> None:
    from tests.conftest import SITE

    url = BASE + "/catalogue/category/books/poetry_23/index.html"
    html = (
        (SITE / "catalogue/category/books/poetry_23/index.html")
        .read_text()
        .replace("page-2.html", "index.html")
    )
    site_router.get(url).respond(200, text=html)
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(settings(), http)
        with pytest.raises(UpstreamParseError):
            await CatalogueIndex(client, settings()).get()


async def test_concurrent_failure_is_singleflight(offline_guard: respx.MockRouter) -> None:
    async def fail(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.01)
        return httpx.Response(500)

    route = offline_guard.get(BASE + "/").mock(side_effect=fail)
    config = settings().model_copy(update={"respect_robots_txt": False})
    async with httpx.AsyncClient() as http:
        index = CatalogueIndex(CatalogueClient(config, http), config)
        outcomes = await asyncio.gather(*(index.get() for _ in range(8)), return_exceptions=True)
        assert all(isinstance(result, UpstreamUnavailable) for result in outcomes)
        assert route.call_count == 1
        with pytest.raises(UpstreamUnavailable):
            await index.get()
        assert route.call_count == 2
        await index.close()
