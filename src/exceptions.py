"""Safe domain failures mapped to the public error contract."""


class BookBridgeError(Exception):
    """Base error with a safe, fixed public message."""

    status = 500
    code = "INTERNAL_ERROR"
    message = "An unexpected error occurred."


class NotFound(BookBridgeError):
    """Requested public resource does not exist."""

    status = 404
    code = "NOT_FOUND"
    message = "The requested resource was not found."


class UpstreamUnavailable(BookBridgeError):
    """The source is unavailable or access is restricted."""

    status = 502
    code = "UPSTREAM_UNAVAILABLE"
    message = "The upstream catalogue could not be reached."


class UpstreamParseError(UpstreamUnavailable):
    """Critical public markup could not be parsed."""


class UpstreamTimeout(BookBridgeError):
    """The source did not respond within the bounded timeout."""

    status = 504
    code = "UPSTREAM_TIMEOUT"
    message = "The upstream catalogue timed out."
