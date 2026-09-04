"""FastAPI exception handlers.

All in one place and wired by :func:`register_exception_handlers`, called
once from :mod:`grunt.main` after the routers are mounted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from grunt.api.messages import ApplicationError
from grunt.config import settings
from grunt.errors import GruntError, error_body

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger()


async def _validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR",
            "Помилка валідації",
            [str(e["msg"]) for e in exc.errors()],
        ),
    )


async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    # APIError carries a semantic code + details; plain HTTPException falls back
    # to HTTP_<status> with any list detail surfaced as details.
    code = getattr(exc, "code", None) or f"HTTP_{exc.status_code}"
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    details = getattr(exc, "details", None)
    if details is None:
        details = exc.detail if isinstance(exc.detail, list) else []
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, details),
        headers=getattr(exc, "headers", None),
    )


async def _grunt_error(request: Request, exc: GruntError) -> JSONResponse:
    """Map GruntError to appropriate HTTP status codes based on title."""
    status_map = {
        "PERMISSION_DENIED": 403,
        "NOT_FOUND": 404,
        "CONFLICT": 409,
        "VALIDATION_ERROR": 422,
    }
    status_code = status_map.get(exc.title or "APPLICATION_ERROR", 422)
    return JSONResponse(
        status_code=status_code,
        content=error_body(exc.title or "APPLICATION_ERROR", str(exc)),
    )


async def _application_error(request: Request, exc: ApplicationError) -> JSONResponse:
    """Map ApplicationError to appropriate HTTP status codes based on code."""
    status_map = {
        "UNAUTHORIZED": 401,
        "PERMISSION_DENIED": 403,
        "NOT_FOUND": 404,
        "CONFLICT": 409,
        "DUPLICATE_DATA": 409,
        "VALIDATION_ERROR": 422,
        "RATE_LIMITED": 429,
    }
    status_code = status_map.get(exc.code, 422)
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
            },
        },
    )


async def _generic_exception(request: Request, exc: Exception) -> JSONResponse:
    import traceback as _tb

    logger.exception("unhandled_error", error=str(exc))

    if not settings.debug:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Внутрішня помилка сервера",
                },
            },
        )

    # Debug mode: return rich error info
    debug_info: dict = {
        "exc_type": type(exc).__name__,
        "message": str(exc),
        "traceback": _tb.format_exc(),
    }

    # Extract SQL details from SQLAlchemy errors
    try:
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(exc, SQLAlchemyError):
            stmt = getattr(exc, "statement", None)
            params = getattr(exc, "params", None)
            orig = getattr(exc, "orig", None)
            if stmt:
                debug_info["sql"] = str(stmt)
            if params:
                debug_info["sql_params"] = str(params)
            if orig:
                debug_info["db_error"] = str(orig)
    except Exception:
        logger.exception("suppressed_error")

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутрішня помилка сервера",
                "debug": debug_info,
            },
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_exception)
    app.add_exception_handler(GruntError, _grunt_error)
    app.add_exception_handler(ApplicationError, _application_error)
    app.add_exception_handler(Exception, _generic_exception)
