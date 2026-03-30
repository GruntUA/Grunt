"""Prometheus metrics for Grunt.

Metrics exposed:
  grunt_http_requests_total{method, path, status}   — request counter
  grunt_http_request_duration_seconds{method, path} — latency histogram
  grunt_ws_connections_active                        — active WebSocket connections
  grunt_db_pool_size                                 — DB connection pool size (if available)

If prometheus_client is not installed, a stub is used and /metrics returns a 501.
"""
from __future__ import annotations

import re

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    _AVAILABLE = True

    http_requests_total = Counter(
        "grunt_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    http_request_duration = Histogram(
        "grunt_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    ws_connections_active = Gauge(
        "grunt_ws_connections_active",
        "Active WebSocket connections",
    )

    _PATH_ID_PATTERN = re.compile(r"/[0-9a-f-]{8,}(/|$)")

except ImportError:
    _AVAILABLE = False
    http_requests_total = None  # type: ignore[assignment]
    http_request_duration = None  # type: ignore[assignment]
    ws_connections_active = None  # type: ignore[assignment]
    generate_latest = None  # type: ignore[assignment]
    CONTENT_TYPE_LATEST = "text/plain"


def is_available() -> bool:
    return _AVAILABLE


def record_request(method: str, path: str, status: int, duration: float) -> None:
    """Record an HTTP request in Prometheus counters."""
    if not _AVAILABLE:
        return
    # Normalize path to avoid high-cardinality (replace UUIDs/IDs)
    norm_path = _PATH_ID_PATTERN.sub(r"/{id}\1", path)
    http_requests_total.labels(method=method, path=norm_path, status=str(status)).inc()
    http_request_duration.labels(method=method, path=norm_path).observe(duration)


def get_metrics_output() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    if not _AVAILABLE:
        return b"prometheus_client not installed\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST
