"""The one place that turns an authenticated :class:`User` into a token payload.

Every sign-in path - password (``login_api``), MFA second step
(``mfa_login_api``), OIDC callback, WebAuthn assertion, any future provider -
ends here so the response shape, the MFA gate and session tracking stay in a
single implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt import _

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


async def issue_login(
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device_id: str | None = None,
    method: str | None = None,
    honor_mfa: bool = True,
) -> dict[str, Any]:
    """Return the standard auth payload for *user*.

    When ``honor_mfa`` and the user has MFA enabled, this returns an
    ``mfa_required`` challenge instead of real tokens - the caller must then
    complete ``mfa_login_api``. Pass ``honor_mfa=False`` from the MFA step
    itself (the factor has already been proven).

    A disabled user (``is_active`` off) is refused outright.

    A role with ``Role.allowed_ips`` refuses sign-in from any other address.

    When one of the user's roles has ``Role.require_mfa`` but MFA is off, the
    payload is the same challenge shape plus ``mfa_setup_required`` and an
    ``mfa_setup`` token - the client enrolls via ``mfa_enroll_begin`` /
    ``mfa_enroll_complete`` instead of verifying. No tokens until then.
    """
    from grunt.api.messages import throw
    from grunt.auth.doctypes.User.user import _auth_user_dump
    from grunt.auth.doctypes.UserSession.user_session import open_session
    from grunt.auth.ip_policy import sign_in_ip_allowed
    from grunt.auth.mfa import mfa_setup_required
    from grunt.auth.service import (
        access_token_minutes,
        create_access_token,
        create_mfa_setup_token,
        create_mfa_token,
    )

    # Signup approval first: a pending account is also inactive, but it waits
    # for an admin rather than being switched off.
    state = getattr(user, "signup_state", None) or "approved"
    if state == "rejected":
        throw(_("The registration request was rejected by an administrator."), "UNAUTHORIZED")
    if state == "pending":
        # Not an error - the frontend shows a "waiting for approval" notice.
        return {
            "access_token": None,
            "refresh_token": None,
            "mfa_token": None,
            "token_type": "bearer",
            "user": _auth_user_dump(user),
            "mfa_required": False,
            "approval_pending": True,
        }

    # A disabled account would otherwise get tokens that every request (and
    # refresh) rejects with 401 - the client just bounces back to the login page.
    if not user.is_active:
        throw(_("This account is disabled. Contact an administrator."), "UNAUTHORIZED")

    if not await sign_in_ip_allowed(user, ip_address):
        throw(_("Sign-in from this IP address is not allowed for your role."), "PERMISSION_DENIED")

    if honor_mfa and await mfa_setup_required(user):
        return {
            "access_token": None,
            "refresh_token": None,
            "mfa_token": create_mfa_setup_token(user),
            "token_type": "bearer",
            "user": _auth_user_dump(user),
            "mfa_required": True,
            "mfa_setup_required": True,
        }

    if honor_mfa and user.mfa_enabled:
        return {
            "access_token": None,
            "refresh_token": None,
            "mfa_token": create_mfa_token(user),
            "token_type": "bearer",
            "user": _auth_user_dump(user),
            "mfa_required": True,
        }

    assert user.id is not None
    # Login is fully complete here (every challenge - MFA verify, MFA setup,
    # pending approval - returned earlier, above). Only now reset the failed
    # attempt counter: clearing it at the password step would let a known
    # password reset the counter that wrong MFA codes increment, defeating the
    # lockout on the 6-digit second factor.
    from grunt.auth.doctypes.User.user import clear_failed_attempts

    await clear_failed_attempts(user)

    sid, refresh_token = await open_session(
        user.id, ip_address, user_agent, device_id=device_id, method=method
    )
    access_token = create_access_token(user, await access_token_minutes(), sid=sid)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "mfa_token": None,
        "token_type": "bearer",
        "user": _auth_user_dump(user),
        "mfa_required": False,
    }


async def find_or_create_external_user(email: str, full_name: str) -> User:
    """Resolve a local :class:`User` for an externally-authenticated identity
    (OIDC / SAML / email link / ...), creating a passwordless one if needed.

    No password is set - ``hashed_password`` stays ``NULL``. Password sign-in is
    simply unavailable for the account until the user sets one from their profile
    (``set_user_password_api`` treats a null hash as a first-time set, so no
    "current password" is asked for).
    """
    from grunt.auth.doctypes.User.user import create_user, get_user_by_email

    user = await get_user_by_email(email)
    if user is not None:
        return user

    # The User controller needs a non-empty first *and* last name. External
    # identities often carry only a single-word name (or none at all) - fall
    # back to the email local part so provisioning never fails on that.
    local = email.split("@", 1)[0]
    parts = (full_name or "").split(maxsplit=1)
    first = parts[0] if parts else local
    last = parts[1] if len(parts) > 1 else local
    return await create_user(email, "", first, last, None)
