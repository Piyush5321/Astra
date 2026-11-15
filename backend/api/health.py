"""Health check endpoint."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.config import settings
from backend.database.session import check_database

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """Response returned by the health check endpoint."""

    status: str
    application: str
    version: str
    database: dict = {}
    llm_enabled: bool = False


@router.get("/health", response_model=HealthResponse)
def health_check(request: Request) -> HealthResponse:
    """Report the running application's health, identity and database status."""
    db = check_database()
    return HealthResponse(
        status="healthy" if db["status"] == "ok" else "degraded",
        application=request.app.title,
        version=request.app.version,
        database=db,
        llm_enabled=settings.llm_enabled,
    )
