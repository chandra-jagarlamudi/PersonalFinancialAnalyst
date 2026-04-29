"""Structured JSON logging configuration.

Call configure_logging() once at app startup. After that, use:

    import structlog
    log = structlog.get_logger()
    log.info("event", key=value, ...)

All log calls within a request automatically include request_id and user_id
via the context variables set by RequestContextMiddleware.
"""

import contextvars
import logging
import sys

import structlog

# Context variables propagated through the request lifecycle
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="none"
)
_user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id", default="anonymous"
)


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(value: str) -> None:
    _request_id_var.set(value)


def get_user_id() -> str:
    return _user_id_var.get()


def set_user_id(value: str) -> None:
    _user_id_var.set(value)


def _inject_context(logger: object, method: str, event_dict: dict) -> dict:
    event_dict["request_id"] = _request_id_var.get()
    event_dict["user_id"] = _user_id_var.get()
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON output to stdout."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_context,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Redirect standard library logging through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
