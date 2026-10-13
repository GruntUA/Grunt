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
from typing import TYPE_CHECKING

import grunt
from grunt import _, log
from grunt.site.settings import get_setting

if TYPE_CHECKING:
    from py_vapid import Vapid

_VAPID_PRIVATE_KEY_FIELD = "webpush_vapid_private"
_VAPID_PUBLIC_KEY_FIELD = "webpush_vapid_public"
_VAPID_CLAIMS_SUB = "mailto:system@grunt.local"
_PUSH_TTL_SECONDS = 24 * 60 * 60


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


class PushUnavailableError(Exception):
    """Web Push can't be sent at all (disabled, package missing, no/invalid VAPID key)."""


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

    async def _vapid(self) -> Vapid | None:
        """Load the stored VAPID private key; ``None`` if keys aren't generated yet.

        Stored as PEM (see :func:`_generate_vapid_keys`). It must be parsed here:
        handed to pywebpush as a string it goes through ``Vapid.from_string``,
        which only understands raw / bare base64-DER keys and chokes on PEM.
        Raises ``ValueError`` when the stored key is unreadable.
        """
        from py_vapid import Vapid

        try:
            key = await grunt.get_single("SystemSettings", _VAPID_PRIVATE_KEY_FIELD)
        except Exception:
            return None
        if not key:
            return None
        try:
            if "-----BEGIN" in key:
                # Not Vapid.from_pem: it decodes standard base64 as URL-safe.
                from cryptography.hazmat.primitives import serialization

                return Vapid(serialization.load_pem_private_key(key.encode(), password=None))
            return Vapid.from_string(key)
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    async def deliver(self, sub: dict, payload: str, vapid: Vapid) -> PushResult:
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
                vapid_private_key=vapid,
                vapid_claims={"sub": _VAPID_CLAIMS_SUB},
                # pywebpush defaults to TTL 0, which WNS (Edge on Windows)
                # rejects with a bare 400; it also drops the message for any
                # browser that happens to be offline at that moment.
                ttl=_PUSH_TTL_SECONDS,
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

    async def _ready_vapid(self) -> Vapid:
        """Return the signing key, or raise :class:`PushUnavailableError` with the reason."""
        if not await get_setting("enable_web_push", False):
            raise PushUnavailableError(_("Web Push is disabled in the system settings"))
        if importlib.util.find_spec("pywebpush") is None:
            raise PushUnavailableError(_("The pywebpush package is not installed"))
        try:
            vapid = await self._vapid()
        except ValueError as exc:
            raise PushUnavailableError(
                _("The stored VAPID key is invalid: %(error)s") % {"error": exc}
            ) from exc
        if vapid is None:
            raise PushUnavailableError(_("VAPID keys are not generated yet"))
        return vapid

    async def send_to_user(
        self, user: str, *, title: str, body: str = "", url: str = "/"
    ) -> list[PushResult]:
        """Push to every browser *user* subscribed from; one result per subscription.

        *user* is a User id or email: subscriptions are saved under the email,
        and a user whose email changed keeps the old one as their id.

        Raises :class:`PushUnavailableError` when push can't be sent at all.
        """
        vapid = await self._ready_vapid()

        email = await grunt.db.get_value("User", user, "email")
        # Raw read: the caller is usually the *sender* (whoever triggered the
        # notification), and PushSubscription is row-matched to its owner - a
        # guarded read would see none of the recipient's subscriptions.
        subs = await grunt.db.get_all(
            "PushSubscription",
            filters={"user__in": sorted({user, email} - {None, ""})},
            fields=["endpoint", "p256dh", "auth"],
            limit=None,
        )
        payload = json.dumps({"title": title, "body": body, "url": url})
        results = []
        for sub in subs:
            result = await self.deliver(sub, payload, vapid)
            if result.expired:
                log.info("webpush.subscription_expired", user=user, status=result.status)
            elif not result.ok:
                log.warning(
                    "webpush.send_failed", user=user, status=result.status, error=result.error
                )
            results.append(result)
        return results

    async def send_push(
        self,
        user: str,
        subject: str,
        body: str,
        url: str = "/",
    ) -> None:
        """Best-effort push for a notification - never raises, failures are logged."""
        try:
            await self.send_to_user(user, title=subject, body=body, url=url)
        except PushUnavailableError as exc:
            log.debug("webpush.unavailable", reason=str(exc))

    async def send_test(
        self, sub: dict, *, title: str, body: str = "", url: str = "/"
    ) -> PushResult:
        """Send a test message to a single subscription (the form's test action)."""
        try:
            vapid = await self._ready_vapid()
        except PushUnavailableError as exc:
            return PushResult(ok=False, error=str(exc))
        payload = json.dumps({"title": title, "body": body, "url": url})
        return await self.deliver(sub, payload, vapid)


webpush_service = WebPushService()
