"""FastAPI application entrypoint.

Start with: uvicorn financial_assistant.main:app --reload
Or via entry point: financial-assistant
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from financial_assistant.api import router as api_router
from financial_assistant.auth import router as auth_router
from financial_assistant.auth_middleware import (
    CsrfMiddleware,
    MCPApiKeyMiddleware,
    SessionAuthMiddleware,
)
from financial_assistant.logging_config import configure_logging
from financial_assistant.mcp_server import router as mcp_router
from financial_assistant.middleware import ErrorLoggingMiddleware, RequestContextMiddleware
from financial_assistant.rate_limit import RateLimitMiddleware
from financial_assistant.tracing import init_tracing
from financial_assistant.upload import router as upload_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Config imported here so startup fails fast if required vars missing
    from financial_assistant.config import get_settings

    s = get_settings()
    configure_logging(s.log_level)
    init_tracing(s.langsmith_api_key, s.langsmith_project)
    yield


app = FastAPI(
    title="Financial Hygiene Assistant",
    version="0.1.0",
    description="MCP server exposing personal finance tools to AI agents.",
    lifespan=lifespan,
)

# Middleware added outermost-last (Starlette wraps in reverse order).
# Execution order on request: ErrorLogging → RequestContext → SessionAuth → Csrf → MCPApiKey → route
app.add_middleware(ErrorLoggingMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SessionAuthMiddleware)
app.add_middleware(CsrfMiddleware)
app.add_middleware(MCPApiKeyMiddleware)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(mcp_router)
app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def start() -> None:
    import uvicorn

    uvicorn.run("financial_assistant.main:app", host="0.0.0.0", port=8000, reload=True)
