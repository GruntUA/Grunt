"""System Manager "view as another user" (impersonation).

A System Manager opens a short-lived session that authenticates as a target
user — same roles, same permissions — to verify what that user can and
cannot see. The session is a bare access token with no refresh token: it
cannot be renewed and expires on its own after
:data:`IMPERSONATION_TTL_MINUTES`. Nothing is written to the target's
``User`` row, so their own live session is untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.i18n import _
from grunt.log import log
from grunt.permissions.roles import user_has_roles

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


#: How long an impersonation access token stays valid.
IMPERSONATION_TTL_MINUTES = 30


async def start_impersonation(actor: User, target_user_id: str) -> dict[str, Any]:
    """Mint an impersonation session for *actor* (a System Manager) as *target_user_id*.

    Returns the same shape as a login payload minus the refresh token, plus an
    ``impersonated_by`` block naming *actor*.
    """
    from grunt.api.messages import throw
    from grunt.auth.doctypes.User.user import _auth_user_dump, get_user_by_id
    from grunt.auth.service import create_access_token

    if not user_has_roles(actor, ["System Manager"]):
        throw(_("System Manager rights are required."), "PERMISSION_DENIED")

    target = await get_user_by_id(target_user_id)
    if target is None:
        throw(_("User not found."), "NOT_FOUND")
    if target.id == actor.id:
        throw(_("You cannot impersonate your own account."), "VALIDATION_ERROR")
    if user_has_roles(target, ["System Manager"]):
        throw(_("You cannot impersonate another administrator."), "PERMISSION_DENIED")
    if not target.is_active:
        throw(_("The account is disabled."), "VALIDATION_ERROR")

    log.warning(
        "auth.impersonation.start",
        actor=actor.email,
        actor_id=actor.id,
        target=target.email,
        target_id=target.id,
    )

    token = create_access_token(target, IMPERSONATION_TTL_MINUTES, impersonator=actor)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": IMPERSONATION_TTL_MINUTES,
        "user": _auth_user_dump(target),
        "impersonated_by": {"id": actor.id, "email": actor.email, "full_name": actor.full_name},
    }
