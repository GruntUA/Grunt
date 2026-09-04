"""The one place that turns an authenticated :class:`User` into a token payload.

Every sign-in path — password (``login_api``), MFA second step
(``mfa_login_api``), OIDC callback, WebAuthn assertion, any future provider —
ends here so the response shape, the MFA gate and session tracking stay in a
single implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


async def issue_login(
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    honor_mfa: bool = True,
) -> dict[str, Any]:
    """Return the standard auth payload for *user*.

    When ``honor_mfa`` and the user has MFA enabled, this returns an
    ``mfa_required`` challenge instead of real tokens — the caller must then
    complete ``mfa_login_api``. Pass ``honor_mfa=False`` from the MFA step
    itself (the factor has already been proven).
    """
    from grunt.api.messages import throw
    from grunt.auth.doctypes.User.user import _auth_user_dump, _track_login_session
    from grunt.auth.service import (
        create_access_token,
        create_mfa_token,
        create_refresh_token,
        session_ttl_minutes,
    )

    state = getattr(user, "signup_state", None) or "approved"
    if state == "rejected":
        throw("Заявку на реєстрацію відхилено адміністратором.", "UNAUTHORIZED")
    if state == "pending":
        # Not an error — the frontend shows a "waiting for approval" notice.
        return {
            "access_token": None,
            "refresh_token": None,
            "mfa_token": None,
            "token_type": "bearer",
            "user": _auth_user_dump(user),
            "mfa_required": False,
            "approval_pending": True,
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
    ttl = await session_ttl_minutes()
    access_token = create_access_token(user, ttl)
    refresh_token = await create_refresh_token(user.id, ttl)
    await _track_login_session(user.id, ip_address, user_agent)

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

    No password is set — ``hashed_password`` stays ``NULL``. Password sign-in is
    simply unavailable for the account until the user sets one from their profile
    (``set_user_password_api`` treats a null hash as a first-time set, so no
    "current password" is asked for).
    """
    from grunt.auth.doctypes.User.user import create_user, get_user_by_email

    user = await get_user_by_email(email)
    if user is not None:
        return user

    # The User controller needs a non-empty first *and* last name. External
    # identities often carry only a single-word name (or none at all) — fall
    # back to the email local part so provisioning never fails on that.
    local = email.split("@", 1)[0]
    parts = (full_name or "").split(maxsplit=1)
    first = parts[0] if parts else local
    last = parts[1] if len(parts) > 1 else local
    return await create_user(email, "", first, last, None)
