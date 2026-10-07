"""FastAPI exception handlers.

All in one place and wired by :func:`register_exception_handlers`, called
once from :mod:`grunt.main` after the routers are mounted.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError

from grunt import _, log
from grunt.api.messages import ApplicationError
from grunt.config import settings
from grunt.errors import error_body
from grunt.logging_config import mark_logged

if TYPE_CHECKING:
    from fastapi import FastAPI
    from jinja2 import Environment

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "website" / "templates"
_error_env: Environment | None = None


def _wants_html(request: Request) -> bool:
    """A browser navigation (website page, form post) - not an API/XHR call."""
    if request.url.path.startswith("/api/"):
        return False
    return "text/html" in request.headers.get("accept", "")


def _format_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(exc))


def _origin_frame(exc: BaseException) -> dict[str, Any] | None:
    """The innermost frame outside third-party packages - where to look first.

    Jinja rewrites template frames to point at the ``.html`` file/line, so for
    a template error this is the offending template line.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if "site-packages" not in f.filename]
    frame = (ours or frames or [None])[-1]
    if frame is None:
        return None
    return {
        "filename": frame.filename,
        "lineno": frame.lineno,
        "name": frame.name,
        "line": frame.line,
    }


def _render_error_html(
    request: Request,
    status_code: int,
    title: str,
    message: str = "",
    debug: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Standalone HTML error page - deliberately not extending any site
    ``_base.html``, which may itself be what failed."""
    global _error_env
    try:
        if _error_env is None:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            _error_env = Environment(
                loader=FileSystemLoader(str(_TEMPLATES_DIR)),
                autoescape=select_autoescape(default=True),
            )
        from grunt.i18n import translation_service

        html = _error_env.get_template("_error.html").render(
            request=request,
            request_id=getattr(request.state, "request_id", None),
            status_code=status_code,
            title=title,
            message=message if message != title else "",
            debug=debug,
            home_label=_("Back to home page"),
            lang=translation_service.get_lang(),
        )
    except Exception:  # noqa: BLE001 - never fail while reporting a failure
        log.exception("error_page.render_failed")
        html = f"<h1>{status_code}</h1>"
    return HTMLResponse(html, status_code=status_code, headers=headers)


async def _validation_error(request: Request, exc: ValidationError) -> Response:
    content = error_body(
        "VALIDATION_ERROR",
        _("Validation error"),
        [str(e["msg"]) for e in exc.errors()],
    )

    # Debug mode: attach the same rich `debug` bundle _generic_exception() gives
    # 500s - this is a server-side pydantic bug (a metadata model rejecting a
    # shape the DB actually holds), not a client input mistake, and the plain
    # "422 / Помилка валідації" message alone gives no way to find it. Listing
    # each failing field/input is what actually points at the broken model.
    if settings.debug:
        content["error"]["debug"] = {
            "exc_type": type(exc).__name__,
            "message": str(exc),
            "traceback": _format_traceback(exc),
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

    if _wants_html(request):
        debug = content["error"].get("debug")
        if debug:
            debug["where"] = _origin_frame(exc)
        return _render_error_html(request, 422, _("Validation error"), debug=debug)
    return JSONResponse(status_code=422, content=content)


async def _http_exception(request: Request, exc: HTTPException) -> Response:
    # APIError carries a semantic code + details; plain HTTPException falls back
    # to HTTP_<status> with any list detail surfaced as details.
    code = getattr(exc, "code", None) or f"HTTP_{exc.status_code}"
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    details = getattr(exc, "details", None)
    if details is None:
        details = exc.detail if isinstance(exc.detail, list) else []
    if _wants_html(request):
        return _render_error_html(
            request,
            exc.status_code,
            _page_title(exc.status_code),
            message,
            headers=getattr(exc, "headers", None),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, details),
        headers=getattr(exc, "headers", None),
    )


async def _application_error(request: Request, exc: ApplicationError) -> Response:
    """Render ApplicationError with the HTTP status its code maps to."""
    if _wants_html(request):
        return _render_error_html(
            request, exc.status_code, exc.title or _page_title(exc.status_code), exc.message
        )
    return JSONResponse(
        status_code=exc.status_code,
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
    except Exception:  # noqa: BLE001 - the 500 response must go out regardless
        log.debug("error_log.http_persist_failed", exc_info=True)


async def _generic_exception(request: Request, exc: Exception) -> Response:
    log.exception("unhandled_error", path=request.url.path)
    mark_logged(exc)
    await _persist_error_log(request, exc)

    if not settings.debug:
        if _wants_html(request):
            return _render_error_html(request, 500, _("Internal server error"))
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
        "traceback": _format_traceback(exc),
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

    if _wants_html(request):
        debug_info["where"] = _origin_frame(exc)
        return _render_error_html(request, 500, _("Internal server error"), debug=debug_info)
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


def _page_title(status_code: int) -> str:
    return {
        401: _("Login required"),
        403: _("Access denied"),
        404: _("Page not found"),
    }.get(status_code) or (_("Internal server error") if status_code >= 500 else _("Error"))


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette types handlers as taking a bare Exception; each one here only
    # ever gets the class it is registered for.
    app.add_exception_handler(ValidationError, _validation_error)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(HTTPException, _http_exception)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(ApplicationError, _application_error)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(Exception, _generic_exception)
