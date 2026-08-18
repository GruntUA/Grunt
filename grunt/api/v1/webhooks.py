"""Webhook API — management via methods, public receiver via router."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

import grunt
from grunt.api.router import GruntRouter

router = GruntRouter(optional_auth=True)


@router.post("/incoming/{slug}")
async def receive_incoming_webhook(slug: str, request: Request) -> dict[str, Any]:
    """Public receiver endpoint. Kept as router for stable external URL."""
    from grunt.webhook.incoming_service import incoming_webhook_service

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    result = await incoming_webhook_service.receive(
        slug=slug,
        raw_body=body,
        headers=headers,
    )
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result.get("detail", "Rejected"))
    return {"success": True, **result}


@grunt.whitelist(roles=["superadmin"])
async def test_outgoing_webhook(webhook_id: str) -> dict[str, Any]:
    """Send a test payload for an outgoing webhook."""
    from grunt.app import grunt as grunt_app
    from grunt.webhook.service import webhook_service

    user = await grunt.get_current_user()
    result = await webhook_service.test_delivery(
        grunt_app._require_session(), webhook_id, user.email
    )
    return result


@grunt.whitelist(roles=["superadmin"])
async def list_incoming_logs(webhook_id: str, page: int = 1, per_page: int = 20) -> dict[str, Any]:
    """List recent delivery logs for an incoming webhook."""
    logs = await grunt.get_list(
        "IncomingWebhookLog",
        filters={"webhook": webhook_id},
        fields=["name", "slug", "status", "action_taken", "duration_ms", "error", "created_at"],
        order_by="created_at",
        order="desc",
        limit=int(per_page),
        page=int(page),
    )
    total = await grunt.db.count("IncomingWebhookLog", filters={"webhook": webhook_id})
    return {"items": logs, "total": total, "page": int(page), "per_page": int(per_page)}
