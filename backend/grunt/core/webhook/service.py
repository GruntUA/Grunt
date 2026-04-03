"""Outgoing Webhook service.

Fires HTTP POST requests to registered webhook URLs when document events occur.
Payload is signed with HMAC-SHA256 using the webhook secret (if configured).

The ``X-Grunt-Signature`` header contains: ``sha256=<hex_digest>``
Recipients can verify it with their copy of the secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class WebhookService:

    async def fire(
        self,
        session: AsyncSession,
        event: str,
        doctype: str,
        doc: dict[str, Any],
    ) -> None:
        """Load matching enabled webhooks and fire them concurrently (best-effort)."""
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        wh_dt = doctype_registry._doctypes.get("OutgoingWebhook")
        if not wh_dt:
            return

        table = compile_doctype_to_table(wh_dt)
        stmt = (
            select(table)
            .where(table.c.doctype_name == doctype)
            .where(table.c.event == event)
            .where(table.c.is_enabled.is_(True))
        )
        try:
            result = await session.execute(stmt)
            webhooks = result.mappings().all()
        except Exception:  # noqa: BLE001
            return

        if not webhooks:
            return

        payload_str = json.dumps({
            "event": event,
            "doctype": doctype,
            "doc": {k: str(v) if v is not None else None for k, v in doc.items()},
            "timestamp": int(time.time()),
        }, ensure_ascii=False)

        for wh in webhooks:
            # Evaluate optional condition
            if wh.get("condition"):
                try:
                    safe_ns: dict = {"doc": doc, "__builtins__": {}}
                    if not eval(wh["condition"], safe_ns):  # noqa: S307
                        continue
                except Exception:  # noqa: BLE001
                    continue

            await self._send(
                url=str(wh["url"]),
                payload=payload_str,
                secret=wh.get("secret") or "",
                extra_headers=wh.get("headers") or "",
                timeout=int(wh.get("timeout") or 10),
            )

    async def _send(
        self,
        url: str,
        payload: str,
        secret: str,
        extra_headers: str,
        timeout: int,
    ) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}

        # HMAC-SHA256 signature
        if secret:
            sig = hmac.new(
                secret.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Grunt-Signature"] = f"sha256={sig}"

        # Merge extra headers from JSON
        if extra_headers:
            try:
                extra = json.loads(extra_headers)
                if isinstance(extra, dict):
                    headers.update({str(k): str(v) for k, v in extra.items()})
            except Exception:  # noqa: BLE001
                pass

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, content=payload, headers=headers)
                logger.info(
                    "webhook.fired",
                    url=url,
                    status=resp.status_code,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("webhook.fire_failed", url=url, error=str(exc))


webhook_service = WebhookService()
