"""Request context propagated through logs and asynchronous service calls."""

import logging
from contextvars import ContextVar

request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to every configured log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id.get()
        return True


def configure_logging(level: str) -> None:
    """Configure application logging without disabling existing test handlers."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s request_id=%(request_id)s %(name)s %(message)s")
        )
        root.addHandler(handler)
    for handler in root.handlers:
        handler.addFilter(RequestIdFilter())
    root.setLevel(level)
