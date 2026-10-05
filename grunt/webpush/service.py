"""Web Push notification service (RFC 8030 + VAPID).

Uses ``pywebpush`` to send encrypted push messages to browser endpoints.
VAPID keys are generated once and stored in SystemSettings.

If ``pywebpush`` is not installed the service silently skips sending -
all other notification channels (in-app, email) continue to work.
"""

from __future__ import annotations

import json

from grunt import log

_VAPID_PRIVATE_KEY_FIELD = "webpush_vapid_private"
_VAPID_PUBLIC_KEY_FIELD = "webpush_vapid_public"
_VAPID_CLAIMS_SUB = "mailto:system@grunt.local"


def _generate_vapid_keys() -> tuple[str, str]:
    """Generate a new VAPID key pair. Returns (private_pem, public_b64url)."""
    import base64

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


class WebPushService:
    async def get_vapid_public_key(self) -> str | None:
        """Return the VAPID public key stored in SystemSettings, or None."""
        import grunt

        try:
            return await grunt.get_single("SystemSettings", _VAPID_PUBLIC_KEY_FIELD)
        except Exception:
            return None

    async def ensure_vapid_keys(self) -> str | None:
        """Ensure VAPID keys exist in SystemSettings; generate if missing. Returns public key."""
        import importlib.util

        if importlib.util.find_spec("py_vapid") is None:
            log.warning("webpush.pywebpush_not_installed")
            return None

        import grunt

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
        import grunt

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
        import grunt

        await grunt.db.delete("PushSubscription", filters={"endpoint": endpoint, "user": user})

    async def send_push(
        self,
        user: str,
        subject: str,
        body: str,
        url: str = "/",
    ) -> None:
        """Send a Web Push notification to all subscriptions of a user."""
        from grunt.site.settings import get_setting

        if not await get_setting("enable_web_push", False):
            return

        try:
            from pywebpush import webpush
        except ImportError:
            return  # Silently skip if not installed

        import grunt

        # Get VAPID private key
        try:
            vapid_private = await grunt.get_single("SystemSettings", _VAPID_PRIVATE_KEY_FIELD)
            if not vapid_private:
                return
        except Exception:
            return

        # Get subscriptions for this user
        subs = await grunt.get_list("PushSubscription", filters={"user": user})

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
            except Exception as exc:
                log.warning("webpush.send_failed", user=user, error=str(exc))


webpush_service = WebPushService()
