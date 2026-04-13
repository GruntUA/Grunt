"""Webhook management endpoints.

Outgoing webhooks
-----------------
POST /webhooks/outgoing/{webhook_id}/test  — send a test payload

Incoming webhooks
-----------------
POST /webhooks/incoming/{slug}             — public receive endpoint (no auth)
GET  /webhooks/incoming/{webhook_id}/logs  — list recent delivery logs (superadmin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from grunt.api.v1.schemas.response import ok, ok_list
from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ── Outgoing webhooks ──────────────────────────────────────────────────────────

@router.post("/outgoing/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Send a test payload for an outgoing webhook and return the delivery log."""
    from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can test webhooks",
        )

    result = await webhook_service.test_delivery(session, webhook_id, user.email)
    return ok(result)


# ── Incoming webhooks ──────────────────────────────────────────────────────────

@router.post("/incoming/{slug}", status_code=status.HTTP_200_OK)
async def receive_incoming_webhook(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Public endpoint that receives incoming webhook events.

    No authentication required — security is enforced via HMAC signature
    verification if the webhook is configured with a secret.

    Returns ``{"accepted": true}`` on success or ``{"accepted": false, "detail": "..."}``
    on rejection (invalid signature, unknown slug, disabled webhook).
    """
    from grunt.core.webhook.incoming_service import incoming_webhook_service  # noqa: PLC0415

    body = await request.body()
    # Forward all request headers as a plain dict (lowercase keys)
    headers = {k.lower(): v for k, v in request.headers.items()}

    result = await incoming_webhook_service.receive(
        session=session,
        slug=slug,
        raw_body=body,
        headers=headers,
    )

    if not result.get("accepted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("detail", "Rejected"),
        )

    return ok(result)


@router.get("/incoming/{webhook_id}/logs")
async def list_incoming_webhook_logs(
    webhook_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    _user: GruntUser = Depends(superadmin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List recent delivery logs for an incoming webhook (superadmin only)."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.auth.models import SYSTEM_USER  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        logs = await grunt.get_list(
            "IncomingWebhookLog",
            filters={"webhook": webhook_id},
            fields=["id", "slug", "status", "action_taken", "duration_ms", "error", "created_at"],
            order_by="created_at",
            order="desc",
            limit=per_page,
            page=page,
        )
        total = await grunt.db.count("IncomingWebhookLog", filters={"webhook": webhook_id})
    finally:
        grunt.reset_context(_tokens)

    return ok_list(logs, total=total, page=page, per_page=per_page)
