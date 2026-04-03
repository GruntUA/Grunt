"""Web Push notification service (RFC 8030 + VAPID).

Uses ``pywebpush`` to send encrypted push messages to browser endpoints.
VAPID keys are generated once and stored in SystemSettings.

If ``pywebpush`` is not installed the service silently skips sending —
all other notification channels (in-app, email) continue to work.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

_VAPID_PRIVATE_KEY_FIELD = "webpush_vapid_private"
_VAPID_PUBLIC_KEY_FIELD = "webpush_vapid_public"
_VAPID_CLAIMS_SUB = "mailto:system@grunt.local"


def _generate_vapid_keys() -> tuple[str, str]:
    """Generate a new VAPID key pair. Returns (private_pem, public_b64url)."""
    from py_vapid import Vapid  # type: ignore[import]
    v = Vapid()
    v.generate_keys()
    private_pem = v.private_key.private_bytes(
        encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.PEM,
        format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PrivateFormat"]).PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=__import__("cryptography.hazmat.primitives.serialization", fromlist=["NoEncryption"]).NoEncryption(),
    ).decode()
    public_b64 = v.public_key_urlsafe_base64
    return private_pem, public_b64


class WebPushService:

    async def get_vapid_public_key(self, session: AsyncSession) -> str | None:
        """Return the VAPID public key stored in SystemSettings, or None."""
        try:
            from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
            from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
            from sqlalchemy import select  # noqa: PLC0415

            ss_dt = doctype_registry._doctypes.get("SystemSettings")
            if not ss_dt:
                return None
            table = compile_doctype_to_table(ss_dt)
            if _VAPID_PUBLIC_KEY_FIELD not in table.c:
                return None
            row = (await session.execute(select(table).limit(1))).first()
            return str(row._mapping[_VAPID_PUBLIC_KEY_FIELD]) if row else None
        except Exception:  # noqa: BLE001
            return None

    async def ensure_vapid_keys(self, session: AsyncSession) -> str | None:
        """Ensure VAPID keys exist in SystemSettings; generate if missing. Returns public key."""
        try:
            from py_vapid import Vapid  # noqa: F401 — test import
        except ImportError:
            logger.warning("webpush.pywebpush_not_installed")
            return None

        try:
            from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
            from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
            from sqlalchemy import select  # noqa: PLC0415

            ss_dt = doctype_registry._doctypes.get("SystemSettings")
            if not ss_dt:
                return None
            table = compile_doctype_to_table(ss_dt)
            if _VAPID_PUBLIC_KEY_FIELD not in table.c:
                return None

            row = (await session.execute(select(table).limit(1))).first()
            if row and row._mapping.get(_VAPID_PUBLIC_KEY_FIELD):
                return str(row._mapping[_VAPID_PUBLIC_KEY_FIELD])

            # Generate new keys
            private_pem, public_b64 = _generate_vapid_keys()
            if row:
                await session.execute(
                    table.update().values(**{
                        _VAPID_PRIVATE_KEY_FIELD: private_pem,
                        _VAPID_PUBLIC_KEY_FIELD: public_b64,
                    })
                )
            else:
                now = datetime.now(timezone.utc)
                await session.execute(table.insert().values(
                    id=str(uuid.uuid4()), name="SystemSettings",
                    owner="system", created_at=now, modified_at=now,
                    modified_by="system", docstatus=0,
                    **{_VAPID_PRIVATE_KEY_FIELD: private_pem, _VAPID_PUBLIC_KEY_FIELD: public_b64},
                ))
            await session.flush()
            logger.info("webpush.vapid_keys_generated")
            return public_b64
        except Exception as exc:  # noqa: BLE001
            logger.warning("webpush.ensure_keys_failed", error=str(exc))
            return None

    async def save_subscription(
        self,
        session: AsyncSession,
        user: str,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str = "",
    ) -> None:
        """Upsert a push subscription for a user (one per endpoint)."""
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from sqlalchemy import select, delete  # noqa: PLC0415

        dt = doctype_registry._doctypes.get("PushSubscription")
        if not dt:
            return
        table = compile_doctype_to_table(dt)

        # Remove old subscription at this endpoint if any
        await session.execute(
            delete(table).where(table.c.endpoint == endpoint)
        )

        now = datetime.now(timezone.utc)
        sub_id = str(uuid.uuid4())
        await session.execute(table.insert().values(
            id=sub_id, name=sub_id, owner=user,
            created_at=now, modified_at=now, modified_by=user, docstatus=0,
            user=user, endpoint=endpoint, p256dh=p256dh, auth=auth,
            user_agent=user_agent,
        ))
        await session.flush()

    async def remove_subscription(self, session: AsyncSession, endpoint: str) -> None:
        """Delete a push subscription by endpoint URL."""
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from sqlalchemy import delete  # noqa: PLC0415

        dt = doctype_registry._doctypes.get("PushSubscription")
        if not dt:
            return
        table = compile_doctype_to_table(dt)
        await session.execute(delete(table).where(table.c.endpoint == endpoint))
        await session.flush()

    async def send_push(
        self,
        session: AsyncSession,
        user: str,
        subject: str,
        body: str,
        url: str = "/",
    ) -> None:
        """Send a Web Push notification to all subscriptions of a user."""
        try:
            from pywebpush import webpush, WebPushException  # type: ignore[import]
        except ImportError:
            return  # Silently skip if not installed

        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        # Get VAPID private key
        try:
            ss_dt = doctype_registry._doctypes.get("SystemSettings")
            if not ss_dt:
                return
            ss_table = compile_doctype_to_table(ss_dt)
            ss_row = (await session.execute(select(ss_table).limit(1))).first()
            if not ss_row or not ss_row._mapping.get(_VAPID_PRIVATE_KEY_FIELD):
                return
            vapid_private = str(ss_row._mapping[_VAPID_PRIVATE_KEY_FIELD])
            vapid_public = str(ss_row._mapping[_VAPID_PUBLIC_KEY_FIELD])
        except Exception:  # noqa: BLE001
            return

        # Get subscriptions for this user
        sub_dt = doctype_registry._doctypes.get("PushSubscription")
        if not sub_dt:
            return
        sub_table = compile_doctype_to_table(sub_dt)
        subs = (await session.execute(
            select(sub_table).where(sub_table.c.user == user)
        )).mappings().all()

        payload = json.dumps({"title": subject, "body": body, "url": url})

        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                    },
                    data=payload,
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": _VAPID_CLAIMS_SUB, "aud": sub["endpoint"].split("/")[2]},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("webpush.send_failed", user=user, error=str(exc))


webpush_service = WebPushService()
