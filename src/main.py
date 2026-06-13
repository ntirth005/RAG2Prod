from fastapi import FastAPI
from src.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.
    """
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": "0.1.0"
    }

@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """
    Root endpoint returning basic metadata.
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API. Access documentation at /docs."
    }
