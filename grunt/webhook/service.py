"""Outgoing Webhook service.

Sends HTTP POST requests to registered webhook URLs when document events occur -
after the commit, through the outbox (:mod:`grunt.outbox`): the save doesn't wait
on the remote server, a rollback sends nothing, a failed delivery is retried with
a backoff. Every attempt is written to ``WebhookLog``. Payload is signed with
HMAC-SHA256 using the webhook secret (if configured).

The ``X-Grunt-Signature`` header contains: ``sha256=<hex_digest>``
Recipients can verify it with their copy of the secret.
"""

import hashlib
import hmac
import json
import time
from typing import Any

import httpx2
from sqlalchemy.ext.asyncio import AsyncSession

import grunt.outbox as outbox
from grunt.db.api import GruntDB
from grunt.i18n import _
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry
lazy from grunt.document.api import documents
lazy from grunt.webhook.doctypes.OutgoingWebhook.outgoing_webhook import OutgoingWebhook

_db = GruntDB()  # stateless: reads through the context's session


class WebhookService:
    async def fire(
        self,
        session: AsyncSession,
        event: str,
        doctype: str,
        doc: dict[str, Any],
    ) -> None:
        """Queue *event* for the matching enabled webhooks - one outbox message
        each, delivered after the commit (:func:`deliver_webhook`)."""
        if await doctype_registry.get_or_none("OutgoingWebhook") is None:
            return

        try:
            async with system_context(session):
                webhooks = await _db.get_all(
                    "OutgoingWebhook",
                    filters={"doctype_name": doctype, "event": event, "is_enabled": True},
                    limit=100,
                )
        except Exception:
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
                    from simpleeval import simple_eval

                    if not simple_eval(wh["condition"], names={"doc": doc}):
                        continue
                except Exception:
                    log.warning(
                        "webhook.condition_eval_error",
                        webhook=str(wh.get("name") or ""),
                        condition=wh["condition"],
                    )
                    continue

            await outbox.put(
                deliver_webhook,
                {"webhook": str(wh.get("name") or ""), "event": event, "body": payload_str},
                session=session,
            )

    async def test_delivery(
        self,
        session: AsyncSession,
        webhook_id: str,
        user_email: str,
    ) -> dict[str, Any]:
        """Send a test payload for the given webhook and return the log entry."""
        async with system_context(session):
            wh_data = await documents.find_doc(OutgoingWebhook, webhook_id)

        if not wh_data:
            return {"success": False, "error": _("Webhook not found")}

        payload_str = json.dumps(
            {
                "event": wh_data.event or "test",
                "doctype": wh_data.doctype_name or "",
                "doc": {"id": "test-doc-id", "name": "test-document", "_test": True},
                "timestamp": int(time.time()),
                "is_test": True,
            },
            ensure_ascii=False,
        )

        log = await self._send_and_log(
            session=session,
            webhook_id=webhook_id,
            event=wh_data.event or "test",
            url=str(wh_data.url),
            payload=payload_str,
            secret=wh_data.secret or "",
            extra_headers=wh_data.headers or "",
            timeout=int(wh_data.timeout or 10),
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
            except Exception:
                log.exception("suppressed_error")

        status_code: int | None = None
        response_body: str = ""
        error: str = ""
        success = False
        start = time.monotonic()

        try:
            async with httpx2.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, content=payload, headers=headers)
                status_code = resp.status_code
                response_body = resp.text[:4000]
                success = 200 <= resp.status_code < 300
                log.info("webhook.fired", url=url, status=resp.status_code, is_test=is_test)
        except Exception as exc:
            error = str(exc)
            log.warning("webhook.fire_failed", url=url, error=error, is_test=is_test)

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
        if await doctype_registry.get_or_none("WebhookLog") is not None:
            try:
                async with system_context(session):
                    await documents.new_doc("WebhookLog", log_entry)
            except Exception:
                log.warning("webhook_log.write_failed", webhook_id=webhook_id)

        return {**log_entry, "success": success}


webhook_service = WebhookService()


class WebhookDeliveryError(Exception):
    """The remote end didn't take the webhook (no answer, or not a 2xx) - retried."""


async def deliver_webhook(message: dict[str, Any]) -> None:
    """Send one queued webhook (an outbox handler) with its current settings - a
    webhook disabled or deleted since is skipped. The attempt is logged and
    committed before a failure is raised, so a retry keeps the history."""
    session = require_session()
    rows = await _db.get_all("OutgoingWebhook", filters={"name": message["webhook"]}, limit=1)
    wh = rows[0] if rows else None
    if wh is None or not wh.get("is_enabled"):
        return
    # No transaction open while the remote server answers.
    await session.commit()
    result = await webhook_service._send_and_log(
        session=session,
        webhook_id=message["webhook"],
        event=message["event"],
        url=str(wh["url"]),
        payload=message["body"],
        secret=wh.get("secret") or "",
        extra_headers=wh.get("headers") or "",
        timeout=int(wh.get("timeout") or 10),
        is_test=False,
    )
    await session.commit()
    if not result["success"]:
        raise WebhookDeliveryError(result.get("error") or f"HTTP {result.get('status_code')}")
