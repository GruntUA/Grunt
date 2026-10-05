"""Incoming Webhook service.

Receives HTTP POST requests at public endpoints, verifies HMAC signatures,
and dispatches configured actions (log_only / run_server_script / create_document).

Endpoint: ``POST /api/v1/webhooks/incoming/{slug}``

Signature verification
If the webhook is configured with a ``secret`` the request must include a
header (``signature_header``) whose value is one of:

* ``sha256=<hex>`` - HMAC-SHA256 of the raw request body
* ``sha1=<hex>`` - HMAC-SHA1 of the raw request body
* bare ``<hex>`` - treated as HMAC-SHA256

The algorithm used is selected by ``signature_type`` (hmac_sha256 / hmac_sha1 / none).

Field mapping (create_document action)
``field_mapping`` is a JSON object: ``{"doctype_field": "payload.nested.key"}``.
Dotted paths are resolved against the parsed JSON payload.  Literal values can
be prefixed with ``=``, e.g. ``{"status": "=Active"}``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from grunt import log

_MAX_PAYLOAD = 5 * 1024 * 1024  # 5 MB


class IncomingWebhookService:
    # Public API

    async def receive(
        self,
        slug: str,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Process an incoming webhook request.

        Caller must already have an active grunt context (session only -
        this always runs as SYSTEM_USER internally, whatever the ambient
        user is or isn't, since it's driven by an unauthenticated external
        caller).

        Returns a response dict with ``accepted`` flag and optional ``detail``.
        Never raises - all errors are logged and a safe response is returned.
        """
        start = time.monotonic()

        # 1. Load webhook config
        webhook = await self._load_webhook(slug)
        if webhook is None:
            return {"accepted": False, "detail": "Not found"}

        if not webhook.get("is_enabled"):
            return {"accepted": False, "detail": "Webhook disabled"}

        webhook_id = str(webhook.get("name") or "")
        action = webhook.get("action") or "log_only"
        status = "success"
        action_taken = action
        error_msg = ""

        # 2. Verify signature
        secret = (webhook.get("secret") or "").strip()
        sig_type = webhook.get("signature_type") or "hmac_sha256"
        if secret and sig_type != "none":
            sig_header_name = (webhook.get("signature_header") or "X-Grunt-Signature").lower()
            provided_sig = headers.get(sig_header_name, "")
            if not provided_sig:
                # Try canonical header name variations
                for k, v in headers.items():
                    if k.lower() == sig_header_name:
                        provided_sig = v
                        break

            if not self._verify_signature(raw_body, secret, sig_type, provided_sig):
                log.warning("incoming_webhook.signature_rejected", slug=slug)
                await self._write_log(
                    webhook_id=webhook_id,
                    slug=slug,
                    status="error",
                    action_taken="signature_rejected",
                    raw_body=raw_body,
                    headers=headers,
                    error="Invalid or missing signature",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                return {"accepted": False, "detail": "Invalid signature"}

        # 3. Parse payload
        payload: Any = None
        try:
            if raw_body:
                payload = json.loads(raw_body)
        except Exception:
            payload = raw_body.decode(errors="replace")

        # 4. Dispatch action
        try:
            if action == "run_server_script":
                action_taken, error_msg = await self._run_server_script(webhook, payload)
            elif action == "create_document":
                action_taken, error_msg = await self._create_document(webhook, payload)
            # log_only: nothing extra to do

            if error_msg:
                status = "error"
        except Exception as exc:
            status = "error"
            error_msg = f"{type(exc).__name__}: {exc}"
            log.exception("incoming_webhook.dispatch_error", slug=slug)

        duration_ms = int((time.monotonic() - start) * 1000)

        # 5. Write log
        await self._write_log(
            webhook_id=webhook_id,
            slug=slug,
            status=status,
            action_taken=action_taken,
            raw_body=raw_body,
            headers=headers,
            error=error_msg,
            duration_ms=duration_ms,
        )

        log.info(
            "incoming_webhook.received",
            slug=slug,
            status=status,
            action=action,
            duration_ms=duration_ms,
        )
        return {"accepted": True, "status": status}

    # Signature verification

    def _verify_signature(
        self,
        body: bytes,
        secret: str,
        sig_type: str,
        provided: str,
    ) -> bool:
        """Return True if the provided signature matches the computed HMAC."""
        key = secret.encode()
        if sig_type == "hmac_sha1":
            computed = hmac.new(key, body, hashlib.sha1).hexdigest()
            expected_prefix = "sha1="
        else:
            computed = hmac.new(key, body, hashlib.sha256).hexdigest()
            expected_prefix = "sha256="

        # Strip algorithm prefix if present
        candidate = provided
        if candidate.startswith(expected_prefix):
            candidate = candidate[len(expected_prefix) :]
        elif candidate.startswith("sha256=") or candidate.startswith("sha1="):
            # Wrong algorithm prefix - reject
            return False

        try:
            return hmac.compare_digest(computed, candidate)
        except Exception:
            return False

    # Action handlers

    async def _run_server_script(
        self,
        webhook: dict[str, Any],
        payload: Any,
    ) -> tuple[str, str]:
        """Execute the linked ServerScript.  Returns (action_taken, error)."""
        import grunt
        from grunt.auth.doctypes.User.user import SYSTEM_USER
        from grunt.scripting.server_script import ServerScriptRunner

        server_script_engine = ServerScriptRunner()

        script_id = webhook.get("server_script")
        if not script_id:
            return "run_server_script", "server_script not configured"

        session = grunt.get_session()
        async with grunt.system_context(session):
            script_doc = await grunt.find_doc("ServerScript", script_id)

        if not script_doc:
            return "run_server_script", f"ServerScript '{script_id}' not found"

        source = script_doc.get("script") or ""
        result = await server_script_engine.execute(
            source=source,
            doc={},
            session=session,
            extra_context={"payload": payload, "webhook": webhook},
            user_email=SYSTEM_USER.email,
        )

        if not result.success:
            return "run_server_script", result.error or "Script execution failed"

        return f"run_server_script:{script_id}", ""

    async def _create_document(
        self,
        webhook: dict[str, Any],
        payload: Any,
    ) -> tuple[str, str]:
        """Create a DocType document from the payload using field_mapping."""
        import grunt

        target_doctype = webhook.get("target_doctype")
        if not target_doctype:
            return "create_document", "target_doctype not configured"

        mapping_raw = (webhook.get("field_mapping") or "").strip()
        if not mapping_raw:
            return "create_document", "field_mapping not configured"

        try:
            mapping: dict[str, str] = json.loads(mapping_raw)
        except Exception:
            return "create_document", "field_mapping is not valid JSON"

        # Resolve field values from payload
        doc_data: dict[str, Any] = {}
        payload_dict = payload if isinstance(payload, dict) else {}
        for field, path in mapping.items():
            if isinstance(path, str) and path.startswith("="):
                doc_data[field] = path[1:]
            else:
                doc_data[field] = _resolve_path(payload_dict, str(path))

        async with grunt.system_context(grunt.get_session()):
            doc = await grunt.new_doc(target_doctype, doc_data)

        return f"create_document:{target_doctype}:{doc.get('id', '')}", ""

    # Helpers

    async def _load_webhook(self, slug: str) -> dict[str, Any] | None:
        import grunt
        from grunt.metadata.registry import doctype_registry

        if await doctype_registry.get_or_none("IncomingWebhook") is None:
            return None

        async with grunt.system_context(grunt.get_session()):
            rows = await grunt.db.get_all(
                "IncomingWebhook",
                filters={"slug": slug},
                limit=1,
            )

        return rows[0] if rows else None

    async def _write_log(
        self,
        *,
        webhook_id: str,
        slug: str,
        status: str,
        action_taken: str,
        raw_body: bytes,
        headers: dict[str, str],
        error: str,
        duration_ms: int,
    ) -> None:
        import grunt
        from grunt.metadata.registry import doctype_registry

        if await doctype_registry.get_or_none("IncomingWebhookLog") is None:
            return

        payload_str = raw_body[:_MAX_PAYLOAD].decode(errors="replace")
        try:
            headers_str = json.dumps(dict(headers), ensure_ascii=False)
        except Exception:
            headers_str = ""

        log_data: dict[str, Any] = {
            "slug": slug,
            "status": status,
            "action_taken": action_taken[:255] if action_taken else "",
            "request_headers": headers_str[:4000],
            "payload": payload_str[:10000],
            "error": error[:2000] if error else "",
            "duration_ms": duration_ms,
        }
        if webhook_id:
            log_data["webhook"] = webhook_id

        try:
            async with grunt.system_context(grunt.get_session()):
                await grunt.new_doc("IncomingWebhookLog", log_data)
        except Exception:
            log.warning("incoming_webhook_log.write_failed", slug=slug)


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    """Resolve a dot-separated path in a nested dict.

    Example: ``_resolve_path({"a": {"b": 1}}, "a.b")`` -> ``1``
    """
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


incoming_webhook_service = IncomingWebhookService()
