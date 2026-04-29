"""FastAPI application entrypoint.

Start with: uvicorn financial_assistant.main:app --reload
Or via entry point: financial-assistant
"""

from fastapi import FastAPI

app = FastAPI(
    title="Financial Hygiene Assistant",
    version="0.1.0",
    description="MCP server exposing personal finance tools to AI agents.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def start() -> None:
    import uvicorn

    uvicorn.run("financial_assistant.main:app", host="0.0.0.0", port=8000, reload=True)
