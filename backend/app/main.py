"""ReviewX backend — FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import router

app = FastAPI(
    title="ReviewX Backend",
    description="Backend REST API for the ReviewX VS Code extension.",
    version="0.1.0",
)

# CORS: allow requests from the local VS Code Webview and local dev tooling.
# Wide-open is fine for local development; tighten before any production use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by local tooling."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
