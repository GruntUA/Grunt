"""FastAPI exception handlers.

All in one place and wired by :func:`register_exception_handlers`, called
once from :mod:`grunt.main` after the routers are mounted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from grunt.api.messages import ApplicationError
from grunt.config import settings
from grunt.errors import GruntError, error_body
from grunt.i18n import _
from grunt.log import log

if TYPE_CHECKING:
    from fastapi import FastAPI


async def _validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    content = error_body(
        "VALIDATION_ERROR",
        _("Validation error"),
        [str(e["msg"]) for e in exc.errors()],
    )

    # Debug mode: attach the same rich `debug` bundle _generic_exception() gives
    # 500s — this is a server-side pydantic bug (a metadata model rejecting a
    # shape the DB actually holds), not a client input mistake, and the plain
    # "422 / Помилка валідації" message alone gives no way to find it. Listing
    # each failing field/input is what actually points at the broken model.
    if settings.debug:
        import traceback as _tb

        content["error"]["debug"] = {
            "exc_type": type(exc).__name__,
            "message": str(exc),
            "traceback": _tb.format_exc(),
            "fields": [
                {
                    "loc": ".".join(str(p) for p in e["loc"]),
                    "msg": e["msg"],
                    "type": e["type"],
                    "input": repr(e.get("input")),
                }
                for e in exc.errors()
            ],
        }

    return JSONResponse(status_code=422, content=content)


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


async def _persist_error_log(request: Request, exc: Exception) -> None:
    """Record an unhandled HTTP 500 to the ErrorLog DocType (best-effort)."""
    try:
        from grunt.monitoring.error_log import record_error

        route = request.scope.get("route")
        method = getattr(route, "name", None) or request.url.path
        await record_error(
            exc=exc,
            context="HTTP Request",
            method=method,
            http_status=500,
            request_method=request.method,
            request_path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
        )
    except Exception:  # noqa: BLE001 — the 500 response must go out regardless
        log.debug("error_log.http_persist_failed", exc_info=True)


async def _generic_exception(request: Request, exc: Exception) -> JSONResponse:
    import traceback as _tb

    log.exception("unhandled_error", error=str(exc))
    await _persist_error_log(request, exc)

    if not settings.debug:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": _("Internal server error"),
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
        log.exception("suppressed_error")

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": _("Internal server error"),
                "debug": debug_info,
            },
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette types handlers as taking a bare Exception; each one here only
    # ever gets the class it is registered for.
    app.add_exception_handler(ValidationError, _validation_error)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(HTTPException, _http_exception)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(GruntError, _grunt_error)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(ApplicationError, _application_error)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(Exception, _generic_exception)
