"""Password strength policy, driven by ``SystemSettings``.

Call :func:`enforce_password_policy` on every path where a user sets or changes
their own password (registration, reset, admin-set, generic User form). The
low-level ``create_user()`` is deliberately *not* guarded so that first-admin
bootstrap (``grunt site create`` / setup wizard) is never blocked.
"""

from __future__ import annotations

import grunt
from grunt.i18n import _
from grunt.site.settings import get_setting


async def get_password_policy() -> dict[str, int | bool]:
    """The active password rules, straight from ``SystemSettings``.

    Defaults mirror the field defaults in ``SystemSettings.json`` (min length 8;
    require upper/lower/digit; symbols optional).
    """
    return {
        "min_length": int(await get_setting("password_min_length", 8) or 0),
        "require_uppercase": bool(await get_setting("password_require_uppercase", True)),
        "require_lowercase": bool(await get_setting("password_require_lowercase", True)),
        "require_numbers": bool(await get_setting("password_require_numbers", True)),
        "require_symbols": bool(await get_setting("password_require_symbols", False)),
    }


@grunt.whitelist(allow_guest=True)
async def password_policy_api() -> dict[str, int | bool]:
    """Expose :func:`get_password_policy` to the frontend (live strength hints)."""
    return await get_password_policy()


async def enforce_password_policy(password: str) -> None:
    """Raise a VALIDATION_ERROR listing every unmet requirement, or return."""
    policy = await get_password_policy()
    min_length = policy["min_length"]
    require_upper = policy["require_uppercase"]
    require_lower = policy["require_lowercase"]
    require_digit = policy["require_numbers"]
    require_symbol = policy["require_symbols"]

    password = password or ""
    problems: list[str] = []

    if len(password) < min_length:
        problems.append(_("be at least %(count)s characters long") % {"count": min_length})
    if require_upper and not any(c.isupper() for c in password):
        problems.append(_("contain an uppercase letter"))
    if require_lower and not any(c.islower() for c in password):
        problems.append(_("contain a lowercase letter"))
    if require_digit and not any(c.isdigit() for c in password):
        problems.append(_("contain a digit"))
    if require_symbol and not any(not c.isalnum() for c in password):
        problems.append(_("contain a special character"))

    if problems:
        grunt.throw(
            _("The password must %(requirements)s.") % {"requirements": "; ".join(problems)},
            "VALIDATION_ERROR",
        )
