"""FastAPI application entry point."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from backend.api.agent_reports import router as agent_reports_router
from backend.api.health import router as health_router
from backend.api.missions import router as missions_router
from backend.api.sites import router as sites_router
from backend.config import PROJECT_ROOT, settings
from backend.data.ingest import ingest_all
from backend.database import session as db_session
from backend.database.schema import init_schema

log = logging.getLogger("astra")


_ready = False
_ready_lock = threading.Lock()


def ensure_ready() -> None:
    """Create the schema and ingest datasets once per process (idempotent).

    Called from the lifespan hook and, because serverless platforms may skip
    lifespan events, again before the first API request.
    """
    global _ready
    if _ready:
        return
    with _ready_lock:
        if _ready:
            return
        init_schema(db_session.engine)
        for attempt in range(2):
            with db_session.SessionLocal() as db:
                try:
                    counts = ingest_all(db)
                    break
                except IntegrityError:
                    # Another instance ingested concurrently into a shared database.
                    db.rollback()
                    if attempt:
                        raise
        if counts:
            log.info("Ingested measurements: %s", counts)
        _ready = True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_ready()
    yield


app = FastAPI(
    title=settings.app_name,
    description="NASA planetary analog discovery system for Earth, Moon, and Mars.",
    version="1.0.0",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def _initialise_on_first_api_call(request: Request, call_next):
    if request.url.path.startswith("/api") and not _ready:
        ensure_ready()
    return await call_next(request)


app.include_router(health_router)
app.include_router(sites_router)
app.include_router(missions_router)
app.include_router(agent_reports_router)

FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
        # Watch only source code: .venv/ and OneDrive sync activity would otherwise
        # trigger endless reloads.
        reload_dirs=[str(PROJECT_ROOT / "backend")],
        reload_excludes=["*.pyc", "__pycache__"],
    )
