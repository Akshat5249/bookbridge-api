"""The only HTTP layer: bounded GETs, robots, safe redirects and polite pacing."""

import asyncio
import logging
import random
from http.cookiejar import DefaultCookiePolicy
from time import monotonic
from urllib.parse import SplitResult, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from src.config import Settings
from src.exceptions import NotFound, UpstreamTimeout, UpstreamUnavailable

logger = logging.getLogger(__name__)
RETRY_STATUSES = {500, 502, 503, 504}


class RejectCookies(DefaultCookiePolicy):
    """Never store or return upstream cookies."""

    def set_ok(self, cookie: object, request: object) -> bool:
        return False

    def return_ok(self, cookie: object, request: object) -> bool:
        return False


class CatalogueClient:
    """Shared HTTP client with one semaphore and global request-start interval."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client
        self.client.cookies.clear()
        self.client.cookies.jar.set_policy(RejectCookies())
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self._pace_lock = asyncio.Lock()
        self._robots_lock = asyncio.Lock()
        self._last_start: float | None = None
        self._robots: RobotFileParser | None = None
        self._robots_checked = False
        self._robots_denied = False

    def validate_url(self, url: str) -> None:
        """Reject off-origin requests, credentials, fragments and traversal paths."""
        try:
            base, parts = urlsplit(self.settings.upstream_base_url), urlsplit(url)
            _ = parts.port
        except ValueError as exc:
            raise UpstreamUnavailable() from exc

        def origin(parts: SplitResult) -> tuple[str, str | None, int]:
            return (
                parts.scheme,
                parts.hostname,
                parts.port or (443 if parts.scheme == "https" else 80),
            )

        if (
            origin(parts) != origin(base)
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or "%" in parts.path
            or "\\" in parts.path
            or any(piece in {".", ".."} for piece in parts.path.split("/"))
        ):
            raise UpstreamUnavailable()

    async def _pace(self) -> None:
        async with self._pace_lock:
            if self._last_start is not None:
                wait = self.settings.min_request_interval_seconds - (monotonic() - self._last_start)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_start = monotonic()

    async def _response(self, url: str) -> httpx.Response:
        """Request one URL with bounded transient retries and no automatic redirects."""
        self.validate_url(url)
        for attempt in range(self.settings.max_retries + 1):
            started = monotonic()
            try:
                async with self._semaphore:
                    await self._pace()
                    request = self.client.build_request(
                        "GET", url, headers={"User-Agent": self.settings.user_agent}
                    )
                    request.headers.pop("cookie", None)
                    request.extensions["timeout"] = httpx.Timeout(
                        self.settings.read_timeout_seconds,
                        connect=self.settings.connect_timeout_seconds,
                    ).as_dict()
                    response = await self.client.send(request, follow_redirects=False)
                logger.info(
                    "GET %s status=%s duration=%.3f attempt=%s",
                    urlsplit(url).path,
                    response.status_code,
                    monotonic() - started,
                    attempt + 1,
                )
                if (
                    response.status_code not in RETRY_STATUSES
                    or attempt == self.settings.max_retries
                ):
                    return response
            except httpx.TimeoutException as exc:
                logger.warning(
                    "GET %s timeout duration=%.3f attempt=%s",
                    urlsplit(url).path,
                    monotonic() - started,
                    attempt + 1,
                )
                if attempt == self.settings.max_retries:
                    raise UpstreamTimeout() from exc
            except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                logger.warning(
                    "GET %s connection failure duration=%.3f attempt=%s",
                    urlsplit(url).path,
                    monotonic() - started,
                    attempt + 1,
                )
                if attempt == self.settings.max_retries:
                    raise UpstreamUnavailable() from exc
            await asyncio.sleep(
                self.settings.retry_backoff_seconds * 2**attempt + random.uniform(0, 0.1)
            )
        raise UpstreamUnavailable()

    async def _follow(self, url: str, *, robots: bool = False) -> httpx.Response:
        for redirects in range(4):
            if not robots:
                self._check_permission(url)
            response = await self._response(url)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if redirects == 3 or not location:
                raise UpstreamUnavailable()
            url = urljoin(url, location)
            self.validate_url(url)
        raise UpstreamUnavailable()

    def _check_permission(self, url: str) -> None:
        if self._robots_denied or (
            self._robots and not self._robots.can_fetch(self.settings.user_agent, url)
        ):
            raise UpstreamUnavailable()

    async def _ensure_robots(self) -> None:
        if not self.settings.respect_robots_txt or self._robots_checked:
            return
        async with self._robots_lock:
            if self._robots_checked:
                return
            try:
                response = await self._follow(
                    self.settings.upstream_base_url + "/robots.txt", robots=True
                )
            except (UpstreamTimeout, UpstreamUnavailable) as exc:
                # D10 allows unreachable robots, but never unsafe redirects.
                self._robots_checked = True
                if isinstance(exc.__cause__, httpx.TransportError):
                    logger.warning("robots.txt unreachable; proceeding per configured policy")
                    return
                self._robots_denied = True
                raise
            if response.status_code == 200:
                parser = RobotFileParser()
                parser.parse(response.content.decode("utf-8", errors="replace").splitlines())
                self._robots = parser
            elif response.status_code != 404:
                self._robots_denied = True
            self._robots_checked = True

    async def fetch(self, url: str, *, detail: bool = False) -> str:
        """Fetch UTF-8 public HTML; detail-only 404s become resource-not-found."""
        self.validate_url(url)
        await self._ensure_robots()
        response = await self._follow(url)
        if response.status_code == 404 and detail:
            raise NotFound()
        if response.status_code != 200:
            raise UpstreamUnavailable()
        try:
            return response.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UpstreamUnavailable() from exc
