"""Safe 500/502/504 responses, request IDs and a loud unmocked-network guard."""

import httpx
import pytest
import respx

from src.config import Settings
from src.main import create_app
from tests.conftest import BASE


@pytest.mark.parametrize(
    "mode,status,code",
    [
        ("timeout", 504, "UPSTREAM_TIMEOUT"),
        ("500", 502, "UPSTREAM_UNAVAILABLE"),
        ("403", 502, "UPSTREAM_UNAVAILABLE"),
        ("429", 502, "UPSTREAM_UNAVAILABLE"),
        ("garbage", 502, "UPSTREAM_UNAVAILABLE"),
    ],
)
async def test_upstream_api_mapping(
    offline_guard: respx.MockRouter, mode: str, status: int, code: str
) -> None:
    route = offline_guard.get(BASE + "/")
    if mode == "timeout":
        route.mock(side_effect=httpx.ReadTimeout("private path"))
    elif mode == "garbage":
        route.respond(200, text="<h1>Maintenance</h1>")
    else:
        route.respond(int(mode))
    app = create_app(
        Settings(respect_robots_txt=False, max_retries=0, min_request_interval_seconds=0)
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as api,
    ):
        response = await api.get("/api/v1/books")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["details"] is None
    assert response.headers["X-Request-ID"]
    assert "private" not in response.text


async def test_internal_error_has_id_and_no_trace(
    site_router: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings())
    async with app.router.lifespan_context(app):

        def broken_health() -> None:
            raise RuntimeError("secret /internal/path")

        monkeypatch.setattr(app.state.book_service.index, "health", broken_health)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as api:
            response = await api.get("/health", headers={"X-Request-ID": "internal-check"})
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "details": None,
        }
    }
    assert response.headers["X-Request-ID"] == "internal-check"
    assert "secret" not in response.text


async def test_unmocked_http_fails_loudly() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(AssertionError, match="not mocked"):
            await client.get("https://unmocked.invalid/")
