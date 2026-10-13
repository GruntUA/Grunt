"""Web Push notification service (RFC 8030 + VAPID).

Uses ``pywebpush`` to send encrypted push messages to browser endpoints.
VAPID keys are generated once and stored in SystemSettings.

If ``pywebpush`` is not installed the service silently skips sending -
all other notification channels (in-app, email) continue to work.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
from dataclasses import dataclass

import grunt
from grunt import _, log
from grunt.site.settings import get_setting

_VAPID_PRIVATE_KEY_FIELD = "webpush_vapid_private"
_VAPID_PUBLIC_KEY_FIELD = "webpush_vapid_public"
_VAPID_CLAIMS_SUB = "mailto:system@grunt.local"


def _generate_vapid_keys() -> tuple[str, str]:
    """Generate a new VAPID key pair. Returns (private_pem, public_b64url)."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    v = Vapid()
    v.generate_keys()
    assert v.private_key is not None and v.public_key is not None

    # Export private key to PEM
    private_pem = v.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # Export public key as raw Uncompressed Point (required by Web Push)
    raw_pub = v.public_key.public_bytes(
        encoding=serialization.Encoding.X962, format=serialization.PublicFormat.UncompressedPoint
    )

    # Base64URL encode without padding
    public_b64 = base64.urlsafe_b64encode(raw_pub).decode().strip("=")

    return private_pem, public_b64


@dataclass(frozen=True)
class PushResult:
    ok: bool
    status: int | None = None
    error: str = ""
    expired: bool = False


class WebPushService:
    async def get_vapid_public_key(self) -> str | None:
        """Return the VAPID public key stored in SystemSettings, or None."""
        try:
            return await grunt.get_single("SystemSettings", _VAPID_PUBLIC_KEY_FIELD)
        except Exception:
            return None

    async def ensure_vapid_keys(self) -> str | None:
        """Ensure VAPID keys exist in SystemSettings; generate if missing. Returns public key."""
        if importlib.util.find_spec("py_vapid") is None:
            log.warning("webpush.pywebpush_not_installed")
            return None

        try:
            public_key = await grunt.get_single("SystemSettings", _VAPID_PUBLIC_KEY_FIELD)
            if public_key:
                return public_key

            # Generate new keys
            private_pem, public_b64 = _generate_vapid_keys()

            # Since SystemSettings is a Singleton, it's stored as KV in Singles table
            # We can use grunt.db.set_value which works beautifully for Singletons
            await grunt.db.set_value(
                "SystemSettings", "SystemSettings", _VAPID_PRIVATE_KEY_FIELD, private_pem
            )
            await grunt.db.set_value(
                "SystemSettings", "SystemSettings", _VAPID_PUBLIC_KEY_FIELD, public_b64
            )

            log.info("webpush.vapid_keys_generated")
            return public_b64
        except Exception as exc:
            log.warning("webpush.ensure_keys_failed", error=str(exc))
            return None

    async def save_subscription(
        self,
        user: str,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str = "",
    ) -> None:
        """Upsert a push subscription for a user (one per endpoint)."""
        # Remove old subscription at this endpoint if any using db.delete for performance
        await grunt.db.delete("PushSubscription", filters={"endpoint": endpoint})

        # Create new subscription document
        await grunt.new_doc(
            "PushSubscription",
            {
                "user": user,
                "endpoint": endpoint,
                "p256dh": p256dh,
                "auth": auth,
                "user_agent": user_agent,
            },
        )

    async def remove_subscription(self, endpoint: str, user: str) -> None:
        """Delete a push subscription by endpoint URL - only if it belongs to `user`."""
        await grunt.db.delete("PushSubscription", filters={"endpoint": endpoint, "user": user})

    async def _vapid_private_key(self) -> str | None:
        try:
            return await grunt.get_single("SystemSettings", _VAPID_PRIVATE_KEY_FIELD) or None
        except Exception:
            return None

    async def deliver(self, sub: dict, payload: str, vapid_private: str) -> PushResult:
        """Send one encrypted message to one subscription.

        Expired endpoints (404/410) are deleted. Never raises - the outcome
        is returned so callers can log it or show it to the user.
        """
        from pywebpush import WebPushException, webpush

        try:
            # pywebpush is a blocking HTTP call - keep it off the event loop.
            # No "aud" claim: pywebpush derives scheme://host from the endpoint.
            response = await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": _VAPID_CLAIMS_SUB},
                timeout=10,
            )
            return PushResult(ok=True, status=getattr(response, "status_code", None))
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            expired = status in (404, 410)
            if expired:
                # Browser dropped the subscription - forget it.
                await grunt.db.delete("PushSubscription", filters={"endpoint": sub["endpoint"]})
            detail = getattr(exc.response, "text", "") or str(exc)
            return PushResult(ok=False, status=status, error=detail[:500], expired=expired)
        except Exception as exc:
            return PushResult(ok=False, error=str(exc))

    async def send_push(
        self,
        user: str,
        subject: str,
        body: str,
        url: str = "/",
    ) -> None:
        """Send a Web Push notification to all subscriptions of a user."""
        if not await get_setting("enable_web_push", False):
            return
        if importlib.util.find_spec("pywebpush") is None:
            return  # Silently skip if not installed
        vapid_private = await self._vapid_private_key()
        if not vapid_private:
            return

        # Raw read: the caller is usually the *sender* (whoever triggered the
        # notification), and PushSubscription is row-matched to its owner - a
        # guarded read would see none of the recipient's subscriptions.
        subs = await grunt.db.get_all(
            "PushSubscription",
            filters={"user": user},
            fields=["endpoint", "p256dh", "auth"],
            limit=None,
        )
        if not subs:
            return

        payload = json.dumps({"title": subject, "body": body, "url": url})
        for sub in subs:
            result = await self.deliver(sub, payload, vapid_private)
            if result.expired:
                log.info("webpush.subscription_expired", user=user, status=result.status)
            elif not result.ok:
                log.warning(
                    "webpush.send_failed", user=user, status=result.status, error=result.error
                )

    async def send_test(
        self, sub: dict, *, title: str, body: str = "", url: str = "/"
    ) -> PushResult:
        """Send a test message to a single subscription (the form's test action)."""
        if not await get_setting("enable_web_push", False):
            return PushResult(ok=False, error=_("Web Push is disabled in the system settings"))
        if importlib.util.find_spec("pywebpush") is None:
            return PushResult(ok=False, error=_("The pywebpush package is not installed"))
        vapid_private = await self._vapid_private_key()
        if not vapid_private:
            return PushResult(ok=False, error=_("VAPID keys are not generated yet"))

        payload = json.dumps({"title": title, "body": body, "url": url})
        return await self.deliver(sub, payload, vapid_private)


webpush_service = WebPushService()
