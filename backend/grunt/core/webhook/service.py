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
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
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
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        if not doctype_registry._doctypes.get("OutgoingWebhook"):
            return

        try:
            async with grunt.system_context(session):
                webhooks = await grunt.db.get_all(
                    "OutgoingWebhook",
                    filters={"doctype_name": doctype, "event": event, "is_enabled": True},
                    limit=100,
                )
        except Exception:  # noqa: BLE001
            return

        if not webhooks:
            return

        payload_str = json.dumps(
            {
                "event": event,
                "doctype": doctype,
                "doc": {k: str(v) if v is not None else None for k, v in doc.items()},
                "timestamp": int(time.time()),
            },
            ensure_ascii=False,
        )

        for wh in webhooks:
            # Evaluate optional condition
            if wh.get("condition"):
                try:
                    safe_ns: dict = {"doc": doc, "__builtins__": {}}
                    if not eval(wh["condition"], safe_ns):  # noqa: S307
                        continue
                except Exception:  # noqa: BLE001
                    continue

            await self._send_and_log(
                session=session,
                webhook_id=str(wh.get("id") or wh.get("name") or ""),
                event=event,
                url=str(wh["url"]),
                payload=payload_str,
                secret=wh.get("secret") or "",
                extra_headers=wh.get("headers") or "",
                timeout=int(wh.get("timeout") or 10),
                is_test=False,
            )

    async def test_delivery(
        self,
        session: AsyncSession,
        webhook_id: str,
        user_email: str,
    ) -> dict[str, Any]:
        """Send a test payload for the given webhook and return the log entry."""
        from grunt.app import grunt  # noqa: PLC0415

        async with grunt.system_context(session):
            wh_data = await grunt.get_doc("OutgoingWebhook", webhook_id)

        if not wh_data:
            return {"success": False, "error": "Вебхук не знайдено"}

        payload_str = json.dumps(
            {
                "event": wh_data.get("event", "test"),
                "doctype": wh_data.get("doctype_name", ""),
                "doc": {"id": "test-doc-id", "name": "test-document", "_test": True},
                "timestamp": int(time.time()),
                "is_test": True,
            },
            ensure_ascii=False,
        )

        log = await self._send_and_log(
            session=session,
            webhook_id=webhook_id,
            event=wh_data.get("event", "test"),
            url=str(wh_data["url"]),
            payload=payload_str,
            secret=wh_data.get("secret") or "",
            extra_headers=wh_data.get("headers") or "",
            timeout=int(wh_data.get("timeout") or 10),
            is_test=True,
        )
        return log

    async def _send_and_log(
        self,
        session: AsyncSession,
        webhook_id: str,
        event: str,
        url: str,
        payload: str,
        secret: str,
        extra_headers: str,
        timeout: int,
        is_test: bool = False,
    ) -> dict[str, Any]:
        """Send a webhook POST and write a WebhookLog record. Returns log data."""
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        headers: dict[str, str] = {"Content-Type": "application/json"}

        if secret:
            sig = hmac.new(
                secret.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Grunt-Signature"] = f"sha256={sig}"

        if extra_headers:
            try:
                extra = json.loads(extra_headers)
                if isinstance(extra, dict):
                    headers.update({str(k): str(v) for k, v in extra.items()})
            except Exception:  # noqa: BLE001
                pass

        status_code: int | None = None
        response_body: str = ""
        error: str = ""
        success = False
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, content=payload, headers=headers)
                status_code = resp.status_code
                response_body = resp.text[:4000]
                success = 200 <= resp.status_code < 300
                logger.info("webhook.fired", url=url, status=resp.status_code, is_test=is_test)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.warning("webhook.fire_failed", url=url, error=error, is_test=is_test)

        duration_ms = int((time.monotonic() - start) * 1000)

        log_entry: dict[str, Any] = {
            "webhook": webhook_id,
            "event": event,
            "url": url,
            "status_code": status_code,
            "success": success,
            "duration_ms": duration_ms,
            "response_body": response_body,
            "error": error,
            "is_test": is_test,
        }

        # Write WebhookLog best-effort
        if doctype_registry._doctypes.get("WebhookLog"):
            try:
                async with grunt.system_context(session):
                    await grunt.new_doc("WebhookLog", log_entry)
            except Exception:  # noqa: BLE001
                logger.warning("webhook_log.write_failed", webhook_id=webhook_id)

        return {**log_entry, "success": success}


webhook_service = WebhookService()
