"""
API Service — The main gateway for the Adaptive LMS platform.

Handles:
- Authentication & authorization
- Multi-tenancy resolution
- CRUD operations for organizations, users, courses, modules, content
- Learning event ingestion
- Request routing to internal services (adaptive, reporting, ingestion)
- Export/BI endpoints
- Health checks
"""
import logging
import sys
import asyncio
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

# Automatically locate and add project root to sys.path for 'shared' imports when running locally
# (in the container the layout is /app/app and /app/shared, so the root is one level up)
_here = Path(__file__).resolve()
root_dir = next((p for p in _here.parents if (p / "shared").is_dir()), _here.parents[1])
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi import FastAPI, Request, Response
from app.core.config import settings
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Configure structured JSON logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    logger.info(
        '{"event": "startup", "service": "api", "message": "API Service starting"}'
    )
    try:  # jobs a restart left "processing" must not wait forever
        from app.ingestion.pipeline import recover_stale_jobs
        await recover_stale_jobs()
    except Exception:
        logger.exception("could not recover stale ingestion jobs")
    dispatcher = None
    if settings.event_dispatcher_enabled:
        from app.events.dispatcher import run_dispatcher
        dispatcher = asyncio.create_task(run_dispatcher(), name="event-dispatcher")
    scheduler = None
    if settings.report_scheduler_enabled:
        from app.reporting.scheduler import run_scheduler
        scheduler = asyncio.create_task(run_scheduler(), name="report-scheduler")
    yield
    for task in (dispatcher, scheduler):
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    logger.info(
        '{"event": "shutdown", "service": "api", "message": "API Service shutting down"}'
    )


app = FastAPI(
    title="Adaptive LMS API",
    description="Adaptive Learning Management System with Deep Reporting AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Structured logging for every request with request_id."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()

    response: Response = await call_next(request)

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        f'{{"event": "request", "service": "api", "request_id": "{request_id}", '
        f'"method": "{request.method}", "path": "{request.url.path}", '
        f'"status": {response.status_code}, "duration_ms": {duration_ms}}}'
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Root & Health Checks
# ---------------------------------------------------------------------------
@app.get("/", tags=["Root"])
async def root():
    """Service root descriptor with links to interactive documentation and health."""
    return {
        "service": "Adaptive LMS API Gateway",
        "status": "online",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "health_url": "/health",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health", tags=["Health"])
async def health():
    """Liveness probe — is the service running?"""
    return {
        "status": "healthy",
        "service": "api",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/ready", tags=["Health"])
async def readiness():
    """
    Readiness probe — verifies live PostgreSQL and Redis dependencies.
    """
    dependencies = {
        "postgresql": "healthy",
        "redis": "healthy",
    }
    overall = "ready"

    # PostgreSQL check
    try:
        from app.core.database import async_engine
        from sqlalchemy import text
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        dependencies["postgresql"] = f"unhealthy ({str(e)})"
        overall = "not_ready"

    # Redis check
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
    except Exception as e:
        dependencies["redis"] = f"unhealthy ({str(e)})"
        overall = "not_ready"

    status_code = 200 if overall == "ready" else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "service": "api",
            "dependencies": dependencies,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Include API v1 Router
# ---------------------------------------------------------------------------
from app.api.v1.router import api_v1_router
app.include_router(api_v1_router)


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a safe error response."""
    import traceback
    traceback.print_exc()
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        f'{{"event": "unhandled_error", "service": "api", '
        f'"request_id": "{request_id}", "error": "{type(exc).__name__}: {exc}"}}'
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"An internal error occurred: {type(exc).__name__}: {exc}",
            }
        },
    )
