"""Central error mapping and request-id middleware; never expose exception text."""

import logging
import re
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.exceptions import BookBridgeError
from src.observability import request_id
from src.schemas.errors import Error, ErrorResponse, ValidationDetail

logger = logging.getLogger(__name__)


def response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[ValidationDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Serialize safe errors with an ID, including outer-server 500 responses."""
    ident = getattr(request.state, "request_id", str(uuid4()))
    logger.warning("HTTP %s code=%s", status, code, extra={"request_id": ident})
    return JSONResponse(
        ErrorResponse(error=Error(code=code, message=message, details=details)).model_dump(),
        status_code=status,
        headers={**(headers or {}), "X-Request-ID": ident},
    )


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Expose only field names and validation messages, never raw rejected values."""
    details = [
        ValidationDetail(
            field=".".join(
                str(part) for part in item["loc"] if part not in {"query", "path", "body"}
            ),
            message=item["msg"],
        )
        for item in exc.errors()
    ]
    return response(request, 422, "VALIDATION_ERROR", "Invalid request parameters.", details)


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize Starlette-generated route and method errors."""
    mapping = {
        404: ("NOT_FOUND", "The requested resource was not found."),
        405: ("METHOD_NOT_ALLOWED", "The request method is not allowed."),
        422: ("VALIDATION_ERROR", "Invalid request parameters."),
    }
    code, message = mapping.get(
        exc.status_code, ("INTERNAL_ERROR", "An unexpected error occurred.")
    )
    return response(request, exc.status_code, code, message, headers=exc.headers)


async def domain_error(request: Request, exc: BookBridgeError) -> JSONResponse:
    """Map deliberately controlled source errors."""
    return response(request, exc.status, exc.code, exc.message)


async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    """The sole catch-all: log internally and return a fixed safe message."""
    logger.error(
        "Unexpected application failure",
        exc_info=exc,
        extra={"request_id": getattr(request.state, "request_id", "-")},
    )
    return response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")


def register_handlers(app: FastAPI) -> None:
    """Register the contract once for all routes."""
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(BookBridgeError, domain_error)
    app.add_exception_handler(Exception, internal_error)


class RequestIdMiddleware:
    """Echo sane IDs, generate replacements, and propagate IDs into logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        ident = incoming if re.fullmatch(r"[A-Za-z0-9._-]{1,100}", incoming) else str(uuid4())
        scope.setdefault("state", {})["request_id"] = ident
        token = request_id.set(ident)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                message["headers"].append((b"x-request-id", ident.encode("ascii")))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id.reset(token)
