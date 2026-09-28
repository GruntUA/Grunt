"""WebAuthn / passkey authentication provider — the reference implementation
for :mod:`grunt.auth.providers`.

Credentials are stored one-per-row in the ``WebAuthnCredential`` DocType. The
challenge that has to survive between ``begin`` and ``complete`` is carried in a
signed, single-purpose JWT (:func:`grunt.auth.service.create_challenge_token`)
rather than server state, so the flow stays stateless.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlparse

import webauthn

from grunt import _, log
from grunt.api.messages import throw
from grunt.auth.providers.base import AuthFlowContext, AuthProvider
from grunt.auth.providers.registry import register
from grunt.auth.service import create_challenge_token, verify_challenge_token
from grunt.config import settings

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


_AUTH_PURPOSE = "webauthn-auth"
_REG_PURPOSE = "webauthn-reg"
_CRED = "WebAuthnCredential"


# ── deployment config ───────────────────────────────────────────────────────
#
# ``WEBAUTHN_RP_ID`` / ``WEBAUTHN_ORIGIN`` are explicit overrides and SHOULD be
# pinned in production (a stable rp_id lets one passkey work across sub-domains).
# When unset we derive both from the incoming request, so a passkey works on
# whatever host the app is actually served from — not the ``APP_URL`` default.


def _rp_name() -> str:
    return settings.webauthn_rp_name or settings.app_name


def _origin_from_request(request: Any) -> str | None:
    if request is None:
        return None
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    host = request.headers.get("host")
    if host:
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        return f"{scheme}://{host}"
    return None


def _resolve_rp(request: Any) -> tuple[str, str]:
    """Return ``(rp_id, origin)`` for this request.

    The browser rejects an assertion whose ``rp_id`` is not a suffix of the page
    origin, so these must match the domain the user is really on.
    """
    origin = (
        settings.webauthn_origin.rstrip("/")
        if settings.webauthn_origin
        else _origin_from_request(request)
    ) or settings.app_url.rstrip("/")

    rp_id = settings.webauthn_rp_id or (urlparse(origin).hostname or "localhost")

    if (
        not settings.debug
        and not origin.startswith("https://")
        and "localhost" not in origin
        and "127.0.0.1" not in origin
    ):
        log.warning(
            "webauthn.insecure_origin",
            origin=origin,
            hint="WebAuthn requires HTTPS — set WEBAUTHN_ORIGIN / serve over TLS",
        )
    return rp_id, origin


# ── DB helpers ──────────────────────────────────────────────────────────────


async def _credentials_for_user(user_id: str) -> list[dict]:
    import grunt

    async with grunt.system_context(grunt.get_session()):
        return await grunt.get_list(
            _CRED,
            filters={"user": user_id},
            fields=["name", "credential_id", "public_key", "sign_count", "transports"],
            limit=100,
        )


async def _credential_by_id(credential_id: str) -> dict | None:
    import grunt

    async with grunt.system_context(grunt.get_session()):
        rows = await grunt.get_list(
            _CRED,
            filters={"credential_id": credential_id},
            fields=["name", "user", "public_key", "sign_count"],
            limit=1,
        )
    return rows[0] if rows else None


def _descriptors(rows: list[dict]) -> list[Any]:
    from webauthn.helpers.structs import (
        AuthenticatorTransport,
        PublicKeyCredentialDescriptor,
    )

    def _transports(raw: str | None) -> list[Any] | None:
        out: list[Any] = []
        for name in (raw or "").split(","):
            try:
                out.append(AuthenticatorTransport(name.strip()))
            except ValueError:
                continue  # drop transports this library version doesn't know
        return out or None

    return [
        PublicKeyCredentialDescriptor(
            id=webauthn.base64url_to_bytes(row["credential_id"]),
            transports=_transports(row.get("transports")),
        )
        for row in rows
    ]


# ── Provider ────────────────────────────────────────────────────────────────


class WebAuthnProvider(AuthProvider):
    name = "webauthn"
    label = "Passkey"
    kind: ClassVar = "challenge"
    icon = "fingerprint"
    requires_identifier = False  # usernameless (resident-key) sign-in supported
    supports_enrollment = True

    # ── sign in ────────────────────────────────────────────────────────────

    async def begin(self, ctx: AuthFlowContext) -> dict[str, Any]:
        from webauthn.helpers.structs import UserVerificationRequirement

        from grunt.auth.doctypes.User.user import get_user_by_email

        # "cross-device" = sign in with a passkey on a phone (QR/Bluetooth hybrid
        # transport). It must be a discoverable-credential request — the phone
        # can then present any passkey for this RP — so we never scope it to a
        # known credential list, even when an email was supplied.
        cross_device = ctx.get("mode") == "cross-device"

        allow: list[Any] = []
        email = (ctx.get("email") or "").strip().lower()
        if email and not cross_device:
            user = await get_user_by_email(email)
            if user and user.id:
                allow = _descriptors(await _credentials_for_user(user.id))

        rp_id, origin = _resolve_rp(ctx.request)
        options = webauthn.generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=allow or None,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        token = create_challenge_token(
            _AUTH_PURPOSE,
            ttl_minutes=5,
            challenge=webauthn.helpers.bytes_to_base64url(options.challenge),
            rp_id=rp_id,
            origin=origin,
        )
        options_json = json.loads(webauthn.options_to_json(options))
        if cross_device:
            # WebAuthn L3 hint — steer the client straight to the phone/QR UI.
            options_json["hints"] = ["hybrid"]
        return {"options": options_json, "challenge_token": token}

    async def complete(self, ctx: AuthFlowContext) -> User:
        import grunt
        from grunt.auth.doctypes.User.user import get_user_by_id

        response = ctx.get("response") or ctx.get("credential")
        token = ctx.get("challenge_token")
        if not response or not token:
            throw(_("Missing WebAuthn response"), "VALIDATION_ERROR")

        claims = verify_challenge_token(token, _AUTH_PURPOSE)
        if not claims:
            throw(_("Expired or invalid WebAuthn challenge"), "UNAUTHORIZED")
        assert claims  # throw() above is NoReturn

        raw_id = response.get("rawId") or response.get("id")
        cred = await _credential_by_id(raw_id)
        if not cred:
            throw(_("Unknown passkey"), "UNAUTHORIZED")

        fallback_rp_id, fallback_origin = _resolve_rp(ctx.request)
        try:
            verification = webauthn.verify_authentication_response(
                credential=response,
                expected_challenge=webauthn.base64url_to_bytes(claims["challenge"]),
                expected_rp_id=claims.get("rp_id") or fallback_rp_id,
                expected_origin=claims.get("origin") or fallback_origin,
                credential_public_key=webauthn.base64url_to_bytes(cred["public_key"]),
                credential_current_sign_count=int(cred.get("sign_count") or 0),
                require_user_verification=False,
            )
        except Exception as exc:  # library raises InvalidAuthenticationResponse
            log.warning("webauthn.verify_failed", error=str(exc))
            throw(_("Passkey verification failed"), "UNAUTHORIZED")

        async with grunt.system_context(grunt.get_session()):
            await grunt.db.set_value(
                _CRED,
                cred["name"],
                {
                    "sign_count": verification.new_sign_count,
                    "backed_up": bool(verification.credential_backed_up),
                    "last_used_at": datetime.now(UTC),
                },
            )

        user = await get_user_by_id(cred["user"])
        if user is None or not user.is_active:
            throw(_("User not found or inactive"), "UNAUTHORIZED")
        return user

    # ── enrol a passkey for the signed-in user ───────────────────────────

    async def enroll_begin(self, ctx: AuthFlowContext) -> dict[str, Any]:
        from webauthn.helpers.structs import (
            AuthenticatorAttachment,
            AuthenticatorSelectionCriteria,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )

        user = ctx.user
        if user is None or not user.id:
            throw(_("Authentication required"), "UNAUTHORIZED")

        cross_device = ctx.get("mode") == "cross-device"
        rp_id, origin = _resolve_rp(ctx.request)
        exclude = _descriptors(await _credentials_for_user(user.id))
        options = webauthn.generate_registration_options(
            rp_id=rp_id,
            rp_name=_rp_name(),
            user_id=user.id.encode(),
            user_name=user.email,
            user_display_name=user.full_name or user.email,
            exclude_credentials=exclude or None,
            authenticator_selection=AuthenticatorSelectionCriteria(
                # cross-platform tells the browser this credential is meant to
                # live off this machine (phone / security key).
                authenticator_attachment=(
                    AuthenticatorAttachment.CROSS_PLATFORM if cross_device else None
                ),
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )
        token = create_challenge_token(
            _REG_PURPOSE,
            ttl_minutes=10,
            uid=user.id,
            challenge=webauthn.helpers.bytes_to_base64url(options.challenge),
            rp_id=rp_id,
            origin=origin,
        )
        options_json = json.loads(webauthn.options_to_json(options))
        if cross_device:
            # L3 hint — "hybrid" only (NOT "client-device", which pulls the
            # picker back to this device). Some platforms (Windows) still show
            # their own sheet defaulting to the local device with a "Change"
            # link; the RP cannot override that.
            options_json["hints"] = ["hybrid"]
        return {"options": options_json, "challenge_token": token}

    async def enroll_complete(self, ctx: AuthFlowContext) -> dict[str, Any]:
        import grunt

        user = ctx.user
        if user is None or not user.id:
            throw(_("Authentication required"), "UNAUTHORIZED")

        response = ctx.get("response") or ctx.get("credential")
        token = ctx.get("challenge_token")
        label = (ctx.get("label") or "").strip() or "Passkey"
        if not response or not token:
            throw(_("Missing WebAuthn response"), "VALIDATION_ERROR")

        claims = verify_challenge_token(token, _REG_PURPOSE)
        if not claims or claims.get("uid") != user.id:
            throw(_("Expired or invalid WebAuthn challenge"), "UNAUTHORIZED")
        assert claims  # throw() above is NoReturn

        fallback_rp_id, fallback_origin = _resolve_rp(ctx.request)
        try:
            reg = webauthn.verify_registration_response(
                credential=response,
                expected_challenge=webauthn.base64url_to_bytes(claims["challenge"]),
                expected_rp_id=claims.get("rp_id") or fallback_rp_id,
                expected_origin=claims.get("origin") or fallback_origin,
                require_user_verification=False,
            )
        except Exception as exc:
            log.warning("webauthn.register_failed", error=str(exc))
            throw(_("Passkey registration failed"), "VALIDATION_ERROR")

        credential_id = webauthn.helpers.bytes_to_base64url(reg.credential_id)
        if await _credential_by_id(credential_id):
            throw(_("This passkey is already registered"), "CONFLICT")

        transports = ",".join((response.get("response") or {}).get("transports") or [])
        async with grunt.system_context(grunt.get_session()):
            doc = await grunt.new_doc(
                _CRED,
                {
                    "user": user.id,
                    "label": label,
                    "credential_id": credential_id,
                    "public_key": webauthn.helpers.bytes_to_base64url(reg.credential_public_key),
                    "sign_count": reg.sign_count,
                    "aaguid": str(reg.aaguid or ""),
                    "transports": transports,
                    "backed_up": bool(reg.credential_backed_up),
                    "last_used_at": datetime.now(UTC),
                },
            )
        log.info("webauthn.registered", user=user.email, credential=doc["name"])
        return {"name": doc["name"], "label": label}


def register_provider() -> None:
    register(WebAuthnProvider())
