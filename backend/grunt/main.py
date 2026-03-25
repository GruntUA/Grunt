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

# Phase 3 modules (imported for side-effects: table registration)
# workflow, permissions, reports engines are imported on-demand in endpoints

from grunt.core.middleware.security import SecurityHeadersMiddleware  # noqa: E402

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("grunt.startup", version="0.1.0")

    # Create all system tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Load registered DocTypes into memory (includes system DocTypes)
    async with AsyncSessionLocal() as session:
        await doctype_registry.load_all(session)

    # Sync system DocType tables and populate document tables
    from grunt.core.metadata.system_doctypes import SYSTEM_DOCTYPES  # noqa: PLC0415
    from grunt.core.metadata.compiler import sync_table  # noqa: PLC0415
    from grunt.core.startup import populate_system_doctypes, seed_grunt_workspace  # noqa: PLC0415

    for sys_dt in SYSTEM_DOCTYPES.values():
        await sync_table(sys_dt, engine)

    async with AsyncSessionLocal() as session:
        await populate_system_doctypes(session, engine)
        await seed_grunt_workspace(session)
        await session.commit()

    # Load hooks from installed apps
    import importlib  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    apps_dir = Path("grunt-apps")
    if apps_dir.exists():
        import sys  # noqa: PLC0415

        # Add project root to sys.path so grunt-apps is importable
        project_root = str(Path.cwd())
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        for app_hooks in apps_dir.glob("*/*/hooks.py"):
            module_path = str(app_hooks).replace("/", ".").replace("\\", ".").removesuffix(".py")
            try:
                importlib.import_module(module_path)
                logger.info("hooks.loaded", module=module_path)
            except Exception as e:
                logger.warning("hooks.load_error", module=module_path, error=str(e))

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

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: rate limiting via slowapi
try:
    from slowapi import _rate_limit_exceeded_handler  # noqa: PLC0415
    from slowapi.errors import RateLimitExceeded  # noqa: PLC0415
    from grunt.core.middleware.rate_limit import limiter  # noqa: PLC0415

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    pass  # slowapi not installed — rate limiting disabled

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
