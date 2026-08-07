"""Application-wide logging.

One module configures the handlers and one factory hands out loggers, so every
part of the app logs in the same format and a single ``LOG_LEVEL`` controls all
of it.

Import ``get_logger`` here rather than calling ``logging.getLogger`` directly.
Configuration is applied when this module is first imported, so a module that
reaches for the stdlib logger on its own can emit records before any handler
exists — those records are silently dropped or fall back to the "last resort"
handler with a different format.

Every record carries a request id. It travels in a ``ContextVar`` rather than
being passed down through call arguments, so a warning raised deep inside
storage or the scorer is still attributable to the request that triggered it
without every function in between having to accept a correlation argument.
Work with no request in scope — the background worker, CLI scripts — logs a
``-`` instead.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

from app.config import get_settings

# Set per request by the middleware in app.main. The default covers everything
# that runs outside a request: worker jobs, scripts, and import-time records.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


class _RequestIdFilter(logging.Filter):
    """Attach the current request id to every record.

    Installed on the handler rather than on a logger: records propagating up
    from any module's logger pass through the root handler, so one filter
    covers loggers this module never sees, including uvicorn's and
    SQLAlchemy's.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging() -> None:
    """Install the root handler. Safe to call more than once.

    Idempotent because Uvicorn imports the app module in each worker process
    and the test suite imports it per session; adding a second handler would
    duplicate every line.
    """
    global _configured
    if _configured:
        return

    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    # Replace rather than append: basicConfig may already have run, and Uvicorn
    # installs its own handlers when started from the CLI.
    root.handlers = [handler]

    # The request middleware logs every request with timing and a request id.
    # Uvicorn's access log would repeat each one in a different format.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return the logger for a module, configuring logging on first use."""
    configure_logging()
    return logging.getLogger(name)


def set_request_id(value: str) -> object:
    """Bind the request id for the current context. Returns a reset token."""
    return _request_id.set(value)


def reset_request_id(token: object) -> None:
    """Restore the previous request id, undoing a ``set_request_id`` call."""
    _request_id.reset(token)  # type: ignore[arg-type]


def get_request_id() -> str:
    """The request id in scope, or ``-`` outside a request."""
    return _request_id.get()
