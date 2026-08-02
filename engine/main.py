"""Entry-point for the moderation engine API."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from config import settings
from database import AsyncSessionLocal, init_db
from gdpr import gdpr_router, process_pending_deletions, run_retention_cleanup
from known_content import protected_images_router
from routes import router
from warn import warnings_router

# ---------------------------------------------------------------------------
# Logging setup (structlog wrapping stdlib)
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logging.basicConfig(format="%(message)s", level=logging.INFO)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Rate limiter — applied globally via SlowAPIMiddleware
# ---------------------------------------------------------------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit],
)


# ---------------------------------------------------------------------------
# Lifespan — database initialisation and GDPR cleanup on startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise the database and run GDPR housekeeping on startup."""
    await init_db()
    async with AsyncSessionLocal() as session:
        cleaned = await run_retention_cleanup(session)
        processed = await process_pending_deletions(session)
        if cleaned or processed:
            log.info(
                "startup_gdpr_cleanup",
                retention_deleted=cleaned,
                erasure_requests_processed=processed,
            )
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Deepfake Guardian – Moderation Engine",
    version="0.5.0",
    description="Lightweight content moderation API for text, images, and video.",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.include_router(router)
app.include_router(gdpr_router)
app.include_router(warnings_router)
app.include_router(protected_images_router)


# ---------------------------------------------------------------------------
# API-key middleware (all routes except /health)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def require_api_key(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Reject requests that don't carry the correct X-API-Key header.

    Authentication is skipped when API_KEY is not configured (empty string),
    which is the default for local development.
    """
    if settings.api_key:
        # /health is always public
        if request.url.path != "/health":
            provided = request.headers.get("X-API-Key", "")
            if provided != settings.api_key:
                log.warning("api_key_rejected", path=request.url.path)
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or missing API key"},
                )
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, object]:
    """Liveness plus what deepfake detection is *actually* doing.

    A stub fallback means no deepfake is ever detected, so it has to be
    visible here rather than only in the startup logs.
    """
    from deepfake.factory import active_detector_status

    return {"status": "ok", "deepfake": active_detector_status()}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
