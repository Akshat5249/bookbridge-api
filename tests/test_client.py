"""Bounded retries, denied access, origin restrictions and explicit decoding."""

import asyncio

import httpx
import pytest
import respx

from src.clients.catalogue import CatalogueClient
from src.config import Settings
from src.exceptions import NotFound, UpstreamTimeout, UpstreamUnavailable

BASE = "https://books.toscrape.com"


def config(**kwargs: object) -> Settings:
    return Settings(
        respect_robots_txt=False, min_request_interval_seconds=0, retry_backoff_seconds=0, **kwargs
    )


@pytest.mark.parametrize(
    "status,error,calls",
    [
        (403, UpstreamUnavailable, 1),
        (429, UpstreamUnavailable, 1),
        (404, NotFound, 1),
        (500, UpstreamUnavailable, 3),
        (502, UpstreamUnavailable, 3),
        (503, UpstreamUnavailable, 3),
        (504, UpstreamUnavailable, 3),
    ],
)
async def test_status_mapping(
    offline_guard: respx.MockRouter, status: int, error: type[Exception], calls: int
) -> None:
    route = offline_guard.get(BASE + "/catalogue/book_1/index.html").respond(status)
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(config(), http)
        with pytest.raises(error):
            await client.fetch(BASE + "/catalogue/book_1/index.html", detail=True)
    assert route.call_count == calls


@pytest.mark.parametrize(
    "exc,error",
    [
        (httpx.ReadTimeout, UpstreamTimeout),
        (httpx.ConnectTimeout, UpstreamTimeout),
        (httpx.ConnectError, UpstreamUnavailable),
    ],
)
async def test_network_mapping(
    offline_guard: respx.MockRouter, exc: type[Exception], error: type[Exception]
) -> None:
    route = offline_guard.get(BASE + "/").mock(side_effect=exc("fail"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(error):
            await CatalogueClient(config(max_retries=1), http).fetch(BASE + "/")
    assert route.call_count == 2


async def test_retry_success_utf8_and_cookie_rejection(offline_guard: respx.MockRouter) -> None:
    route = offline_guard.get(BASE + "/").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(
                200, content="£ café".encode(), headers={"set-cookie": "session=secret"}
            ),
            httpx.Response(200, text="ok"),
        ]
    )
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(config(), http)
        assert await client.fetch(BASE + "/") == "£ café"
        assert await client.fetch(BASE + "/") == "ok"
        assert not http.cookies
    assert route.call_count == 3
    assert all("cookie" not in call.request.headers for call in route.calls)


async def test_redirects_and_index_404(offline_guard: respx.MockRouter) -> None:
    route = offline_guard.get(BASE + "/").respond(
        302, headers={"location": "https://example.org/private"}
    )
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(config(), http)
        with pytest.raises(UpstreamUnavailable):
            await client.fetch(BASE + "/")
        route.respond(302, headers={"location": "/index.html"})
        offline_guard.get(BASE + "/index.html").respond(200, text="ok")
        assert await client.fetch(BASE + "/") == "ok"
        route.respond(302, headers={"location": "/"})
        with pytest.raises(UpstreamUnavailable):
            await client.fetch(BASE + "/")
        route.respond(404)
        with pytest.raises(UpstreamUnavailable):
            await client.fetch(BASE + "/")


@pytest.mark.parametrize(
    "status,body,allowed",
    [
        (200, "User-agent: *\nDisallow: /catalogue/", False),
        (200, "User-agent: *\nDisallow:", True),
        (404, "", True),
        (403, "", False),
        (429, "", False),
    ],
)
async def test_robots(
    offline_guard: respx.MockRouter, status: int, body: str, allowed: bool
) -> None:
    robots = offline_guard.get(BASE + "/robots.txt").respond(status, text=body)
    target = offline_guard.get(BASE + "/catalogue/book_1/index.html").respond(200, text="ok")
    settings = config().model_copy(update={"respect_robots_txt": True})
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(settings, http)
        for _ in range(2):
            if allowed:
                assert await client.fetch(BASE + "/catalogue/book_1/index.html") == "ok"
            else:
                with pytest.raises(UpstreamUnavailable):
                    await client.fetch(BASE + "/catalogue/book_1/index.html")
    assert robots.call_count == 1
    assert target.call_count == (2 if allowed else 0)


async def test_redirect_obeys_robots(offline_guard: respx.MockRouter) -> None:
    offline_guard.get(BASE + "/robots.txt").respond(200, text="User-agent: *\nDisallow: /private")
    offline_guard.get(BASE + "/").respond(302, headers={"location": "/private"})
    async with httpx.AsyncClient() as http:
        with pytest.raises(UpstreamUnavailable):
            await CatalogueClient(
                config().model_copy(update={"respect_robots_txt": True}), http
            ).fetch(BASE + "/")


async def test_pacing_and_concurrency(offline_guard: respx.MockRouter) -> None:
    starts = []
    active = [0, 0]

    async def respond(request: httpx.Request) -> httpx.Response:
        starts.append(asyncio.get_running_loop().time())
        active[0] += 1
        active[1] = max(active)
        await asyncio.sleep(0.015)
        active[0] -= 1
        return httpx.Response(200, text="ok")

    offline_guard.get(BASE + "/").mock(side_effect=respond)
    settings = config().model_copy(
        update={"min_request_interval_seconds": 0.01, "max_concurrent_requests": 2}
    )
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(settings, http)
        await asyncio.gather(*(client.fetch(BASE + "/") for _ in range(4)))
    assert active[1] <= 2
    assert all(b - a >= 0.009 for a, b in zip(starts, starts[1:], strict=False))


@pytest.mark.parametrize("kind", ["network", "redirect"])
async def test_robots_unreachable_or_unsafe(offline_guard: respx.MockRouter, kind: str) -> None:
    robots = offline_guard.get(BASE + "/robots.txt")
    if kind == "network":
        robots.mock(side_effect=httpx.ConnectError("unreachable"))
    else:
        robots.respond(302, headers={"location": "https://example.org/robots.txt"})
    page = offline_guard.get(BASE + "/").respond(200, text="ok")
    async with httpx.AsyncClient() as http:
        client = CatalogueClient(
            config(max_retries=0).model_copy(update={"respect_robots_txt": True}), http
        )
        for _ in range(2):
            if kind == "network":
                assert await client.fetch(BASE + "/") == "ok"
            else:
                with pytest.raises(UpstreamUnavailable):
                    await client.fetch(BASE + "/")
    assert robots.call_count == 1
    assert page.call_count == (2 if kind == "network" else 0)


@pytest.mark.parametrize(
    "url",
    [
        "https://books.toscrape.com:bad/",
        "https://example.org/",
        "http://books.toscrape.com/",
        "https://user:password@books.toscrape.com/",
        BASE + "/../private",
        BASE + "/%2fprivate",
        BASE + "/path?query=1",
        BASE + "/path#fragment",
    ],
)
async def test_unsafe_url_has_no_request(offline_guard: respx.MockRouter, url: str) -> None:
    async with httpx.AsyncClient() as http:
        with pytest.raises(UpstreamUnavailable):
            await CatalogueClient(config(), http).fetch(url)
    assert not offline_guard.calls
