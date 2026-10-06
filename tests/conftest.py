"""Offline network guard and shared site-backed respx mocks."""

import socket
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
import respx

SITE = Path(__file__).parent / "fixtures/site"
BASE = "https://books.toscrape.com"


@pytest.fixture(autouse=True)
def offline_guard() -> Iterator[respx.MockRouter]:
    """Every HTTPX network request must be explicitly mocked, including robots."""
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
def site_router(offline_guard: respx.MockRouter) -> respx.MockRouter:
    """Serve the fixture mini-site through respx with no sockets."""

    def respond(request: httpx.Request) -> httpx.Response:
        path = urlsplit(str(request.url)).path.lstrip("/") or "index.html"
        file = SITE / path
        return (
            httpx.Response(200, content=file.read_bytes())
            if file.is_file()
            else httpx.Response(404)
        )

    for file in SITE.rglob("*"):
        if file.is_file():
            path = file.relative_to(SITE).as_posix()
            offline_guard.get(BASE + "/" + path).mock(side_effect=respond)
    offline_guard.get(BASE + "/").mock(side_effect=respond)
    offline_guard.get(url__startswith=BASE).mock(side_effect=respond)
    return offline_guard


@pytest.fixture(autouse=True)
def block_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent all outbound sockets, including clients accidentally bypassing HTTPX."""

    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("Real network sockets are forbidden in pytest")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr("src.clients.catalogue.random.uniform", lambda *args: 0)
