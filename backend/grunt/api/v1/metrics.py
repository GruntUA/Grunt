"""Prometheus-compatible metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser

router = APIRouter()


@router.get("/metrics")
async def metrics(user: GruntUser = Depends(current_user)) -> Response:
    """Expose Prometheus metrics. Requires authentication."""
    from grunt.core.monitoring.metrics import get_metrics_output  # noqa: PLC0415

    body, content_type = get_metrics_output()
    return Response(content=body, media_type=content_type)
