"""Request logging middleware — adds request_id, duration_ms, status_code to logs."""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        # Make request_id available downstream
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id

        path = request.url.path

        # Record Prometheus metrics (always)
        try:
            from grunt.core.monitoring.metrics import record_request  # noqa: PLC0415
            record_request(request.method, path, response.status_code, duration_ms / 1000)
        except Exception:  # noqa: BLE001
            pass

        # Skip health/metrics noise in logs
        if path not in ("/api/v1/health", "/api/v1/ready", "/api/v1/metrics"):
            logger.info(
                "http.request",
                request_id=request_id,
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

        return response
