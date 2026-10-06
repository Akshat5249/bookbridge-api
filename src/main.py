"""FastAPI factory and lifespan-owned shared HTTP client and services."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from src.api.errors import RequestIdMiddleware, register_handlers
from src.api.routes import router
from src.clients.catalogue import CatalogueClient
from src.config import Settings
from src.exceptions import BookBridgeError
from src.observability import configure_logging
from src.services.books import BookService
from src.services.index import CatalogueIndex

logger = logging.getLogger(__name__)


async def warmup(index: CatalogueIndex) -> None:
    """Optional startup warmup cannot block readiness or crash the application."""
    try:
        await index.get()
    except BookBridgeError:
        logger.warning("Background catalogue warmup failed; next request can retry")


def create_app(
    settings: Settings | None = None, client: httpx.AsyncClient | None = None
) -> FastAPI:
    """Create an isolated app, optionally using a caller-owned mock HTTP client."""
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        http = client or httpx.AsyncClient(
            trust_env=False,
            timeout=httpx.Timeout(
                settings.read_timeout_seconds, connect=settings.connect_timeout_seconds
            ),
            limits=httpx.Limits(max_connections=settings.max_concurrent_requests),
        )
        upstream = CatalogueClient(settings, http)
        index = CatalogueIndex(upstream, settings)
        application.state.book_service = BookService(upstream, index, settings)
        task = asyncio.create_task(warmup(index)) if settings.index_warmup_on_startup else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await index.close()
            if client is None:
                await http.aclose()

    application = FastAPI(
        redirect_slashes=False,
        title="BookBridge API",
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "An educational demonstration scraping public sandbox HTML from Books to Scrape. "
            "Data may be stale; public, unauthenticated GET pages only."
        ),
    )
    application.add_middleware(RequestIdMiddleware)
    register_handlers(application)
    application.include_router(router)
    return application


app = create_app()
