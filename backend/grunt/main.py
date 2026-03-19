"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from grunt.config import settings
from grunt.api.v1.router import v1_router
from grunt.core.db.base import Base
from grunt.core.db.session import AsyncSessionLocal, engine
from grunt.core.metadata.registry import doctype_registry

# Ensure all ORM models are imported so Base.metadata is complete
import grunt.core.db.system_tables  # noqa: F401
import grunt.core.auth.models  # noqa: F401

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("grunt.startup", version="0.1.0")

    # Create all system tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Load registered DocTypes into memory
    async with AsyncSessionLocal() as session:
        await doctype_registry.load_all(session)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    await engine.dispose()
    logger.info("grunt.shutdown")


app = FastAPI(
    title="Ґрунт API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


# ── Exception handlers ───────────────────────────────────────────────────


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Помилка валідації",
                "details": [str(e["msg"]) for e in exc.errors()],
            },
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": detail,
                "details": exc.detail if isinstance(exc.detail, list) else [],
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error=str(exc))
    details = [str(exc)] if settings.debug else []
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутрішня помилка сервера",
                "details": details,
            },
        },
    )
