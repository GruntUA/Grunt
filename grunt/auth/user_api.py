"""User HTTP endpoints - registration, sign-in, profile, MFA, password reset.

The public method paths stay ``grunt.auth.doctypes.User.user.<name>``: the
User controller module re-exports everything here, and the method dispatcher
resolves names with ``getattr`` on that module.
"""

from typing import Any

from fastapi import HTTPException, Request

import grunt
from grunt import log
from grunt.auth.doctypes.UserSession.user_session import (
    client_device_id,
    client_ip,
    client_user_agent,
    end_session,
    rotate_session,
)
from grunt.auth.impersonation import start_impersonation
from grunt.auth.ip_policy import sign_in_ip_allowed
from grunt.auth.login import issue_login
from grunt.auth.mfa import begin_mfa_setup, check_mfa_code, confirm_mfa_setup, mfa_setup_required
from grunt.auth.password_policy import enforce_password_policy
from grunt.auth.service import (
    access_token_minutes,
    consume_password_reset_token,
    create_access_token,
    create_password_reset_token,
    verify_mfa_setup_token,
    verify_mfa_token,
)
from grunt.auth.users import (
    _apply_signup_approval,
    _assign_default_role,
    _auth_user_dump,
    _guard_registration,
    authenticate,
    create_user,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    is_account_locked,
    list_users,
    register_failed_attempt,
)
from grunt.i18n import _, translation_service
from grunt.permissions.roles import user_has_roles
from grunt.utils.http import public_base_url
lazy from grunt.auth.doctypes.User.user import SYSTEM_USER, User, UserPublic
lazy from grunt.auth.mfa import disable_mfa as _disable_mfa
lazy from grunt.email.service import email_service
lazy from grunt.i18n import use_language


@grunt.whitelist(allow_guest=True)
async def register(
    email: str,
    password: str,
    first_name: str | None = None,
    last_name: str | None = None,
    middle_name: str | None = None,
) -> dict[str, Any]:
    """Register a new user."""
    await _guard_registration()
    await enforce_password_policy(password)

    existing = await get_user_by_email(email)
    if existing is not None:
        grunt.throw(_("User with email '%(email)s' already exists") % {"email": email}, "CONFLICT")

    user = await create_user(email, password, first_name or "", last_name or "", middle_name)
    await _assign_default_role(user.id)
    pending = await _apply_signup_approval(user)
    return {**UserPublic.dump(user), "approval_pending": pending}


@grunt.whitelist(allow_guest=True)
async def register_full_name_api(email: str, password: str, full_name: str) -> dict[str, Any]:
    """Register a new user using a single full_name string."""
    await _guard_registration()
    await enforce_password_policy(password)

    name_parts = full_name.split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    # last_name is required on User: a one-word name (a nickname) fills both.
    last_name = name_parts[1] if len(name_parts) > 1 else first_name
    user = await create_user(email, password, first_name, last_name, None)
    await _assign_default_role(user.id)
    pending = await _apply_signup_approval(user)
    return {**_auth_user_dump(user), "approval_pending": pending}


@grunt.whitelist(allow_guest=True)
async def login_api(email: str, password: str, request: Request | None = None) -> dict[str, Any]:
    """Authenticate a user and issue auth tokens or MFA challenge token."""
    try:
        user = await authenticate(email, password)
    except ValueError as exc:
        if str(exc) == "locked":
            grunt.throw(_("Account temporarily locked. Try again later."), "TOO_MANY_REQUESTS")
        raise

    if user is None:
        grunt.throw(_("Incorrect email or password"), "UNAUTHORIZED")

    return await issue_login(
        user,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
        device_id=client_device_id(request),
        method="password",
    )


@grunt.whitelist(allow_guest=True)
async def mfa_login_api(
    mfa_token: str,
    code: str,
    request: Request | None = None,
) -> dict[str, Any]:
    """Verify MFA challenge token+code and issue full auth tokens."""
    payload = verify_mfa_token(mfa_token)
    if not payload:
        grunt.throw(_("Invalid or expired MFA token"), "UNAUTHORIZED")

    user = await get_user_by_id(payload["uid"])
    if not user or not user.is_active:
        grunt.throw(_("User not found"), "UNAUTHORIZED")

    # The password step already reset the failure counter, so a wrong second
    # factor must count against the same lockout - a 6-digit code is guessable.
    if await is_account_locked(user):
        grunt.throw(_("Account temporarily locked. Try again later."), "TOO_MANY_REQUESTS")
    try:
        await check_mfa_code(user, code)
    except HTTPException:
        await register_failed_attempt(user)
        raise
    except Exception as exc:
        log.error("auth.mfa_verify_error", error=str(exc))
        raise

    # Counter cleared by issue_login once the full login completes below.
    # honor_mfa=False: the second factor has just been proven here.
    return await issue_login(
        user,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
        device_id=client_device_id(request),
        method="password",
        honor_mfa=False,
    )


async def _user_for_mfa_setup(mfa_token: str) -> User:
    """Resolve the user behind an ``mfa_setup`` token who still has to enroll."""
    payload = verify_mfa_setup_token(mfa_token)
    if not payload:
        grunt.throw(_("Invalid or expired MFA setup token"), "UNAUTHORIZED")
    user = await get_user_by_id(payload["uid"])
    if not user or not user.is_active or not await mfa_setup_required(user):
        grunt.throw(_("MFA setup is unavailable"), "UNAUTHORIZED")
    return user


@grunt.whitelist(allow_guest=True)
async def mfa_enroll_begin(mfa_token: str) -> dict[str, Any]:
    """Login-time MFA enrollment, step 1: a fresh TOTP secret + QR code."""
    return await begin_mfa_setup(await _user_for_mfa_setup(mfa_token))


@grunt.whitelist(allow_guest=True)
async def mfa_enroll_complete(
    mfa_token: str,
    code: str,
    request: Request | None = None,
) -> dict[str, Any]:
    """Login-time MFA enrollment, step 2: confirm the code, then sign in.

    Returns the regular login payload plus ``backup_codes`` to show once.
    """
    user = await _user_for_mfa_setup(mfa_token)
    backup_codes = await confirm_mfa_setup(user, code)
    user.mfa_enabled = True
    payload = await issue_login(
        user,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
        device_id=client_device_id(request),
        method="password",
        honor_mfa=False,
    )
    return {**payload, "backup_codes": backup_codes}


@grunt.whitelist()
async def whoami() -> dict[str, Any]:
    """Return the currently authenticated user.

    Re-reads the row from the DB (the context user is built from JWT claims and
    lacks profile fields like ``mfa_enabled`` / ``language`` / ``timezone``).
    """
    ctx_user = grunt.get_user()
    user = (await get_user_by_id(ctx_user.id) if ctx_user.id else None) or ctx_user
    return {
        **UserPublic.dump(user),
        "mfa_enabled": bool(user.mfa_enabled),
        "has_password": bool(getattr(user, "hashed_password", None)),
        "language": getattr(user, "language", None) or None,
        "timezone": getattr(user, "timezone", None) or None,
        # Set only while a System Manager is viewing the system as this user.
        "impersonated_by": ctx_user.data.get("_impersonator"),
    }


@grunt.whitelist()
async def update_me_api(
    theme: str | None = None,
    language: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Update current user preferences and return updated profile."""
    user = grunt.get_user()

    values: dict[str, Any] = {}
    if theme is not None:
        if theme not in ("light", "dark", "system"):
            grunt.throw(_("Invalid theme value"), "VALIDATION_ERROR")
        values["theme"] = theme
    if language is not None:
        # "" clears the preference (follow the site default).
        if language and language not in translation_service.ui_languages():
            grunt.throw(_("Invalid language value"), "VALIDATION_ERROR")
        values["language"] = language or None
    if timezone is not None:
        values["timezone"] = timezone.strip()

    assert user.id is not None
    if values:
        await grunt.set_value("User", user.id, values)

    updated = await get_user_by_id(user.id)
    if updated is None:
        grunt.throw(_("User not found"), "NOT_FOUND")
    return _auth_user_dump(updated)


@grunt.whitelist(allow_guest=True)
async def refresh_api(refresh_token: str, request: Request | None = None) -> dict[str, Any]:
    """Exchange a session's refresh token for a new access+refresh pair."""
    rotated = await rotate_session(refresh_token, client_ip(request))
    if rotated is None:
        grunt.throw(_("Invalid or expired refresh token"), "UNAUTHORIZED")

    sid, new_refresh_token, user_id = rotated
    user = await get_user_by_id(user_id)
    if user is None or not user.is_active:
        grunt.throw(_("Invalid or expired refresh token"), "UNAUTHORIZED")

    # A role started requiring MFA after this session was opened (or MFA was
    # turned off), or the session moved to an address the user's role does not
    # allow: end the session so the next sign-in goes through the policy.

    if not await sign_in_ip_allowed(user, client_ip(request)):
        await end_session(sid)
        grunt.throw(_("Sign-in from this IP address is not allowed for your role"), "UNAUTHORIZED")

    if await mfa_setup_required(user):
        await end_session(sid)
        grunt.throw(
            _("Your role requires two-factor authentication; sign in again"), "UNAUTHORIZED"
        )

    return {
        "access_token": create_access_token(user, await access_token_minutes(), sid=sid),
        "refresh_token": new_refresh_token,
        "mfa_token": None,
        "token_type": "bearer",
        "user": _auth_user_dump(user),
        "mfa_required": False,
    }


@grunt.whitelist()
async def logout_api() -> bool:
    """End the current device's session (other devices stay signed in)."""
    user = grunt.get_user()
    if sid := user.data.get("_sid"):
        await end_session(sid)
    return True


@grunt.whitelist(require=lambda user: user_has_roles(user, ["System Manager"]))
async def start_impersonation_api(user_id: str) -> dict[str, Any]:
    """Open a short-lived session as another user. System Manager only.

    Returns an access token (no refresh token) that authenticates as
    ``user_id`` with that user's roles, plus an ``impersonated_by`` block.
    """
    actor = grunt.get_user()
    return await start_impersonation(actor, user_id)


@grunt.whitelist()
async def stop_impersonation_api() -> bool:
    """Log the end of an impersonation session.

    The real session is restored client-side from the tokens it stashed before
    starting; this endpoint only records that the view-as session was closed.
    """
    user = grunt.get_user()
    imp = user.data.get("_impersonator") if hasattr(user, "data") else None
    if imp:
        log.warning(
            "auth.impersonation.stop",
            actor=imp.get("email"),
            target=user.email,
        )
    return True


@grunt.whitelist()
async def list_colleagues_api() -> list[dict[str, Any]]:
    """The people directory for any signed-in user: active accounts with just
    what a picker shows (sharing, assigning) - no roles, no account state."""
    rows = await grunt.db.get_all(
        "User",
        filters={"is_active": 1},
        fields=["name", "email", "full_name", "avatar"],
        order_by="full_name",
        limit=10_000,
    )
    return [r for r in rows if r.get("email") != SYSTEM_USER.email]


@grunt.whitelist(roles=["System Manager"])
async def list_users_detailed_api() -> list[dict[str, Any]]:
    """List all users with fields needed by the admin REST endpoint."""
    users = await list_users()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "roles": u.roles,
            "theme": u.theme,
            "avatar": u.avatar,
            "mfa_enabled": bool(u.mfa_enabled),
            "is_active": bool(u.is_active),
            "signup_state": getattr(u, "signup_state", None) or "approved",
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@grunt.whitelist(roles=["System Manager"])
async def list_pending_users_api() -> list[dict[str, Any]]:
    """Self-registered users awaiting approval. System Manager only."""
    rows = await grunt.get_list(
        "User",
        filters={"signup_state": "pending"},
        fields=["name", "email", "full_name", "created_at"],
        order_by="created_at asc",
        limit=500,
    )
    return rows


async def _set_signup_state(user_id: str, state: str) -> bool:
    user = await get_user_by_id(user_id)
    if not user or not user.id:
        grunt.throw(_("User not found"), "NOT_FOUND")
    await grunt.set_value(
        "User",
        user.id,
        {"signup_state": state, "is_active": state == "approved"},
    )
    log.info("user.signup_state_changed", email=user.email, state=state)
    return True


@grunt.whitelist(roles=["System Manager"])
async def approve_user_api(user_id: str) -> bool:
    """Approve a pending registration - the user can now sign in. System Manager only."""
    return await _set_signup_state(user_id, "approved")


@grunt.whitelist(roles=["System Manager"])
async def reject_user_api(user_id: str) -> bool:
    """Reject a pending registration. System Manager only."""
    return await _set_signup_state(user_id, "rejected")


@grunt.whitelist()
async def set_user_password_api(
    user_id: str, new_password: str, current_password: str | None = None
) -> bool:
    """Set a new password for a user.

    A user may change *their own* password by passing their ``current_password``.
    When the account has no password yet (provisioned via OIDC / email link),
    that check is skipped - it is a first-time set. Changing *someone else's*
    password requires the System Manager role.
    """
    user = await get_user_by_id(user_id)
    if not user or not user.id:
        grunt.throw(_("User not found"), "NOT_FOUND")

    current = grunt.get_user()
    is_self = bool(
        current
        and (
            (current.id and current.id == user.id)
            or (current.email and current.email == user.email)
        )
    )
    is_admin = bool(current and user_has_roles(current, ["System Manager"]))

    if not is_admin:
        if not is_self:
            grunt.throw(_("Not permitted to change another user's password"), "PERMISSION_DENIED")
        # A first-time set (no existing password) needs no current-password proof.
        if user.hashed_password and (
            not current_password or not await user.check_password(current_password)
        ):
            grunt.throw(_("The current password is incorrect"), "PERMISSION_DENIED")

    await enforce_password_policy(new_password)
    await grunt.set_value("User", user.id, "hashed_password", await hash_password(new_password))
    return True


async def _current_user_doc() -> User:
    """The signed-in user's full row (with MFA columns), for the MFA endpoints."""
    current = grunt.get_user()
    assert current.id is not None
    user = await get_user_by_id(current.id)
    if not user:
        grunt.throw(_("User not found"), "NOT_FOUND")
    return user


@grunt.whitelist()
async def setup_mfa() -> dict[str, Any]:
    """Start MFA setup for the current user."""
    return await begin_mfa_setup(await _current_user_doc())


@grunt.whitelist()
async def confirm_mfa(code: str) -> dict[str, Any]:
    """Confirm MFA setup for the current user."""
    return {"backup_codes": await confirm_mfa_setup(await _current_user_doc(), code)}


@grunt.whitelist()
async def verify_mfa(code: str) -> bool:
    """Verify a TOTP or backup code for the current user."""
    await check_mfa_code(await _current_user_doc(), code)
    return True


@grunt.whitelist()
async def disable_mfa() -> bool:
    """Disable MFA for the current user."""
    await _disable_mfa(await _current_user_doc())
    return True


@grunt.whitelist(allow_guest=True)
async def forgot_password_api(email: str, request: Request | None = None) -> bool:
    """Queue a password reset email if the user exists (always returns success)."""
    user = await get_user_by_email(email)
    if user is None or not user.id:
        return True

    token = await create_password_reset_token(user.id)
    # Build the link from the caller's real origin (Host / X-Forwarded-Proto),
    # not the APP_URL default which is localhost in most deployments.
    reset_url = f"{public_base_url(request)}/reset-password?token={token}"

    try:
        # The mail is for the account owner - render it in *their* language.
        with use_language(user.language):
            html_body = await grunt.render_template(
                "password_reset.html",
                {"full_name": user.full_name, "reset_url": reset_url},
            )
            plain = "\n\n".join(
                [
                    _("Hello, %(name)s,") % {"name": user.full_name},
                    _("Password reset link (valid for 1 hour):"),
                    reset_url,
                    _("If you did not request this, just ignore this email."),
                ]
            )
            subject = _("Password reset")
        session = grunt.get_session()
        await email_service.queue_email(
            session=session,
            to=user.email,
            subject=subject,
            body=plain,
            html_body=html_body,
        )
        await session.flush()
        log.info("auth.forgot_password", email=user.email)
    except Exception:
        # Stay silent to the caller (anti-enumeration), but keep the traceback -
        # a swallowed warning here left us blind when a request landed mid-reload.
        log.warning("auth.forgot_password_email_queue_failed", email=user.email, exc_info=True)

    return True


@grunt.whitelist(allow_guest=True)
async def reset_password_api(token: str, new_password: str) -> bool:
    """Reset password using a valid reset token."""
    await enforce_password_policy(new_password)

    reset_ok = await consume_password_reset_token(token, new_password)
    if not reset_ok:
        grunt.throw(_("Invalid or expired reset token"), "VALIDATION_ERROR")
    return True
