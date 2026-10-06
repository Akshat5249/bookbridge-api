"""All endpoints and validation through ASGITransport with fixture upstream."""

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from src.config import Settings
from src.main import create_app


@pytest.fixture
async def api(site_router: respx.MockRouter) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(min_request_interval_seconds=0, max_retries=0))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as http,
    ):
        yield http


async def test_health_never_requests_upstream(
    api: httpx.AsyncClient, site_router: respx.MockRouter
) -> None:
    response = await api.get("/health", headers={"X-Request-ID": "reviewer-1"})
    assert response.json()["index"] == {
        "loaded": False,
        "stale": False,
        "age_seconds": None,
        "books": 0,
    }
    assert response.headers["X-Request-ID"] == "reviewer-1"
    assert len(site_router.calls) == 0
    replacement = await api.get("/health", headers={"X-Request-ID": "bad id"})
    assert replacement.headers["X-Request-ID"] != "bad id"


async def test_all_endpoints(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/books")
    payload = response.json()
    assert response.status_code == 200 and len(payload["data"]) == 20
    assert payload["pagination"] == {"page": 1, "page_size": 20, "total": 60, "has_next": True}
    assert isinstance(payload["data"][0]["price"], float)
    assert "upc" not in payload["data"][0]
    detail = await api.get("/api/v1/books/" + payload["data"][0]["id"])
    assert detail.json()["data"]["upc"] == "a897fe39b1053632"
    exact = await api.get("/api/v1/books?min_price=10&max_price=10")
    assert exact.json()["pagination"]["total"] == 1
    assert (await api.get("/api/v1/books?rating=5")).json()["data"]
    searched = await api.get("/api/v1/search", params={"q": "  LIGHT  "})
    assert searched.json()["pagination"]["total"] == 2
    assert not (await api.get("/api/v1/search?q=zzzxqjkw")).json()["data"]
    assert len((await api.get("/api/v1/categories")).json()["data"]) == 40
    category = (await api.get("/api/v1/categories/poetry/books?page_size=50")).json()
    assert category["pagination"]["total"] == 21
    assert all(b["category"] == "Poetry" for b in category["data"])
    assert not (await api.get("/api/v1/categories/poetry/books?page=999")).json()["data"]
    assert not (await api.get("/api/v1/books?page=999")).json()["data"]
    spec = (await api.get("/openapi.json")).json()
    assert len(spec["paths"]) == 6
    for path in spec["paths"].values():
        for status in ("404", "422", "502", "504"):
            assert path["get"]["responses"][status]["content"]["application/json"]["schema"][
                "$ref"
            ].endswith("/ErrorResponse")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/books?page=0",
        "/api/v1/books?page=-1",
        "/api/v1/books?page=abc",
        "/api/v1/books?page_size=0",
        "/api/v1/books?page_size=1000",
        "/api/v1/books?rating=0",
        "/api/v1/books?rating=6",
        "/api/v1/books?min_price=-1",
        "/api/v1/books?max_price=-1",
        "/api/v1/books?min_price=50&max_price=10",
        "/api/v1/books?min_price=NaN",
        "/api/v1/books?max_price=Infinity",
        "/api/v1/search?q=",
        "/api/v1/search",
        "/api/v1/search?q=%20%20",
        "/api/v1/search?q=" + "a" * 101,
        "/api/v1/search?q=a&page=0",
        "/api/v1/categories/poetry/books?page_size=51",
    ],
)
async def test_validation(api: httpx.AsyncClient, site_router: respx.MockRouter, path: str) -> None:
    response = await api.get(path)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert isinstance(error["message"], str)
    assert error["details"] and all(set(d) == {"field", "message"} for d in error["details"])
    assert response.headers["X-Request-ID"]
    assert len(site_router.calls) == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/books/does-not-exist_0",
        "/api/v1/books/..%2f..%2fetc",
        "/api/v1/books/invalid",
        "/api/v1/categories/no-such-category/books",
        "/api/v1/unknown",
    ],
)
async def test_not_found(api: httpx.AsyncClient, path: str) -> None:
    response = await api.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["details"] is None
    assert response.headers["X-Request-ID"]


async def test_method(api: httpx.AsyncClient) -> None:
    response = await api.post("/api/v1/books")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["allow"]


async def test_trailing_slash_error_is_json(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/books/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
