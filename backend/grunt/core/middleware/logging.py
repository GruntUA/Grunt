"""Request logging middleware — adds request_id, duration_ms, status_code to logs."""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from grunt.config import settings

logger = structlog.get_logger()

_SKIP_PATHS = frozenset({"/api/v1/health", "/api/v1/ready", "/api/v1/metrics"})
# Don't profile the profiler endpoints themselves
_PROFILER_PREFIX = "/api/v1/dev"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        request.state.request_id = request_id

        path = request.url.path
        use_profiler = settings.debug and not path.startswith(_PROFILER_PREFIX)

        if use_profiler:
            from grunt.core.db.profiler import collect_for_request, finish_request  # noqa: PLC0415
            with collect_for_request(request_id, threshold_ms=settings.slow_query_threshold_ms):
                response = await call_next(request)
        else:
            response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id

        # Record Prometheus metrics (always)
        try:
            from grunt.core.monitoring.metrics import record_request  # noqa: PLC0415
            record_request(request.method, path, response.status_code, duration_ms / 1000)
        except Exception:  # noqa: BLE001
            pass

        if use_profiler:
            finish_request(  # type: ignore[possibly-undefined]
                request_id=request_id,
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

        if path not in _SKIP_PATHS:
            logger.info(
                "http.request",
                request_id=request_id,
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

        return response
