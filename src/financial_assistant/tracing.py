"""LangSmith tracing wrapper.

T-044: Initialize LangSmith; trace_span() no-ops with warning when API key absent.
"""

import contextlib
from typing import Any, Generator

import structlog

log = structlog.get_logger()

_enabled = False


def init_tracing(api_key: str, project: str) -> None:
    """Configure LangSmith tracing. Called once from app lifespan."""
    global _enabled

    if not api_key:
        log.warning("tracing.disabled", reason="LANGSMITH_API_KEY not set")
        _enabled = False
        return

    import os

    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", project)

    _enabled = True
    log.info("tracing.enabled", project=project)


def is_enabled() -> bool:
    return _enabled


@contextlib.contextmanager
def trace_span(
    name: str,
    run_type: str = "chain",
    inputs: dict | None = None,
    metadata: dict | None = None,
) -> Generator[Any, None, None]:
    """Context manager that creates a LangSmith trace span.

    Yields the run object (or None when tracing is disabled). Catches and logs
    any tracing errors so pipeline code is never interrupted by observability failures.
    """
    if not _enabled:
        yield None
        return

    try:
        import langsmith

        with langsmith.trace(
            name=name,
            run_type=run_type,
            inputs=inputs or {},
            metadata=metadata or {},
        ) as run:
            yield run
    except Exception as exc:
        log.warning("tracing.span_error", span=name, error=str(exc))
        yield None
