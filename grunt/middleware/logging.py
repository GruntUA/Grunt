"""Request logging middleware — adds request_id, duration_ms, status_code to logs."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from grunt.config import settings
from grunt.logging_config import _safe_logger_name

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger(__name__)

_SKIP_PATHS = frozenset({"/api/v1/health", "/api/v1/ready", "/api/v1/metrics"})
# Don't profile the profiler endpoints themselves
_PROFILER_PREFIX = "/api/v1/dev"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        request.state.request_id = request_id

        path = request.url.path
        use_profiler = settings.debug and not path.startswith(_PROFILER_PREFIX)

        if use_profiler:
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
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                # finish_request must be called inside the `with` block while
                # the per-request ContextVar is still set
                finish_request(
                    request_id=request_id,
                    method=request.method,
                    path=path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
        else:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-ID"] = request_id

        # Record Prometheus metrics (always)
        try:
            from grunt.monitoring.metrics import record_request

            record_request(request.method, path, response.status_code, duration_ms / 1000)
        except Exception:
            logger.exception("suppressed_error")

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
