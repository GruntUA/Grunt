"""Request logging middleware - adds request_id, duration_ms, status_code to logs."""

from __future__ import annotations

import re
import time
import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from grunt.config import settings
from grunt.logging_config import _safe_logger_name
from grunt.monitoring import perf

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger(__name__)

_SKIP_PATHS = frozenset({"/api/v1/health", "/api/v1/ready"})
# Don't profile the profiler endpoints themselves
_PROFILER_PREFIX = "/api/v1/dev"
_METHOD_PREFIX = "/api/v1/method/"
_CATCH_ALL = "/{path:path}"
_PARAM = re.compile(r"\{(\w+)(?::\w+)?\}")


def _perf_endpoint(request: Request) -> tuple[str, str, str | None] | None:
    """``(kind, endpoint, ref_doctype)`` for the perf stats, or None to skip.

    Named by the route template, never the raw path, so ids don't multiply
    the keys: RPC calls by method, the website catch-all by first path
    segment, static files (a dot in the last segment) and dev-only routes not
    at all.
    """
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if template is None:
        return None
    path = request.url.path
    if path.startswith(_PROFILER_PREFIX) or path in _SKIP_PATHS:
        return None
    if path.startswith(_METHOD_PREFIX):
        return "RPC", path.removeprefix(_METHOD_PREFIX), None
    if template == _CATCH_ALL or template.endswith("/{path:path}"):
        segments = [s for s in path.split("/") if s]
        if template != _CATCH_ALL or (segments and "." in segments[-1]):
            return None
        head = f"/{segments[0]}" if segments else "/"
        return "Page", head + ("/*" if len(segments) > 1 else ""), None
    params = request.scope.get("path_params") or {}
    return (
        "HTTP",
        f"{request.method} {_full_template(path, template, params)}",
        params.get("doctype"),
    )


def _full_template(path: str, template: str, params: dict) -> str:
    """The route template with its router prefix: an included router's route
    only knows its own part (``/{doctype}``), so the prefix is whatever of
    the real path is left once that part, filled in, is cut off the end."""
    filled = _PARAM.sub(lambda m: str(params.get(m.group(1), "")), template)
    if filled and path.endswith(filled):
        return path[: len(path) - len(filled)] + template
    return template


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        request.state.request_id = request_id

        path = request.url.path
        use_profiler = settings.debug and not path.startswith(_PROFILER_PREFIX)

        with perf.sql_tally() as tally:
            try:
                response = await self._call(request, call_next, request_id, start, use_profiler)
            except Exception:
                self._record_perf(request, start, tally, error=True)
                raise
            self._record_perf(request, start, tally, error=response.status_code >= 500)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-ID"] = request_id

        if path not in _SKIP_PATHS:
            from grunt.site.manager import current_site

            site = current_site.get(None)
            access_logger = (
                structlog.get_logger(f"grunt.web.{_safe_logger_name(site)}") if site else logger
            )
            access_logger.info(
                "http.request",
                request_id=request_id,
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                site=site,
            )

        return response

    @staticmethod
    def _record_perf(request: Request, start: float, tally: perf.SqlTally, *, error: bool) -> None:
        target = _perf_endpoint(request)
        if target is not None:
            kind, endpoint, ref_doctype = target
            ms = (time.perf_counter() - start) * 1000
            perf.record(kind, endpoint, ms, ref_doctype=ref_doctype, sql=tally, error=error)

    @staticmethod
    async def _call(
        request: Request, call_next, request_id: str, start: float, use_profiler: bool
    ) -> Response:
        if not use_profiler:
            return await call_next(request)

        from grunt.db.profiler import (
            collect_for_request,
            finish_request,
            set_request_db_threshold,
            set_request_threshold,
        )

        set_request_db_threshold(settings.slow_request_db_ms)
        set_request_threshold(settings.slow_request_ms)
        with collect_for_request(request_id, threshold_ms=settings.slow_query_threshold_ms):
            response = await call_next(request)
            # finish_request must be called inside the `with` block while
            # the per-request ContextVar is still set
            finish_request(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
        return response
