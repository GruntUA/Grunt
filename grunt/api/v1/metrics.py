"""Prometheus-compatible metrics endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from grunt.auth.dependencies import current_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.User import User

router = APIRouter()


@router.get("/metrics")
async def metrics(user: User = Depends(current_user)) -> Response:
    """Expose Prometheus metrics. Requires authentication."""
    from grunt.monitoring.metrics import get_metrics_output  # noqa: PLC0415

    body, content_type = get_metrics_output()
    return Response(content=body, media_type=content_type)
