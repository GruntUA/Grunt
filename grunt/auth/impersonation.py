"""Superadmin "view as another user" (impersonation).

A superadmin opens a short-lived session that authenticates as a target user
— same roles, same permissions — to verify what that user can and cannot see.
The session is a bare access token with no refresh token: it cannot be renewed
and expires on its own after :data:`IMPERSONATION_TTL_MINUTES`. Nothing is
written to the target's ``User`` row, so their own live session is untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.log import log

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


#: How long an impersonation access token stays valid.
IMPERSONATION_TTL_MINUTES = 30


async def start_impersonation(actor: User, target_user_id: str) -> dict[str, Any]:
    """Mint an impersonation session for *actor* (a superadmin) as *target_user_id*.

    Returns the same shape as a login payload minus the refresh token, plus an
    ``impersonated_by`` block naming *actor*.
    """
    from grunt.api.messages import throw
    from grunt.auth.doctypes.User.user import _auth_user_dump, get_user_by_id
    from grunt.auth.service import create_access_token

    if not actor.is_superadmin:
        throw("Потрібні права суперадміністратора.", "PERMISSION_DENIED")

    target = await get_user_by_id(target_user_id)
    if target is None:
        throw("Користувача не знайдено.", "NOT_FOUND")
    if target.id == actor.id:
        throw("Не можна увійти під власним обліковим записом.", "VALIDATION_ERROR")
    if target.is_superadmin:
        throw("Не можна увійти під іншим суперадміністратором.", "PERMISSION_DENIED")
    if not target.is_active:
        throw("Обліковий запис вимкнено.", "VALIDATION_ERROR")

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
