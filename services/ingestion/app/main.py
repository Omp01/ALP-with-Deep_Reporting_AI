"""
Ingestion Service — Content processing, competency extraction, and assessment generation.

Handles:
- File upload processing (PDF, PPT, DOC, audio, video)
- Text extraction and chunking
- AI-powered competency extraction from content
- AI-powered assessment question generation
- Embedding generation using sentence-transformers
- Storage in PostgreSQL + pgvector + MinIO
"""
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingestion")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        '{"event": "startup", "service": "ingestion", '
        '"message": "Ingestion Service starting"}'
    )
    yield
    logger.info(
        '{"event": "shutdown", "service": "ingestion", '
        '"message": "Ingestion Service shutting down"}'
    )


app = FastAPI(
    title="Ingestion Service",
    description="Content processing, competency extraction, and assessment generation",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()
    response: Response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        f'{{"event": "request", "service": "ingestion", '
        f'"request_id": "{request_id}", "method": "{request.method}", '
        f'"path": "{request.url.path}", "status": {response.status_code}, '
        f'"duration_ms": {duration_ms}}}'
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": "ingestion",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/ready", tags=["Health"])
async def readiness():
    return {
        "status": "ready",
        "service": "ingestion",
        "dependencies": {"postgresql": "not_configured", "minio": "not_configured"},
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        f'{{"event": "unhandled_error", "service": "ingestion", '
        f'"request_id": "{request_id}", "error": "{type(exc).__name__}: {exc}"}}'
    )
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An internal error occurred."}},
    )
