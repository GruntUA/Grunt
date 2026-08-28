"""Password strength policy, driven by ``SystemSettings``.

Call :func:`enforce_password_policy` on every path where a user sets or changes
their own password (registration, reset, admin-set, generic User form). The
low-level ``create_user()`` is deliberately *not* guarded so that first-admin
bootstrap (``grunt site create`` / setup wizard) is never blocked.
"""

from __future__ import annotations

import grunt
from grunt.site.settings import get_setting


async def enforce_password_policy(password: str) -> None:
    """Raise a VALIDATION_ERROR listing every unmet requirement, or return.

    All rules come from ``SystemSettings``. Defaults mirror the field defaults
    in ``SystemSettings.json`` (min length 8; require upper/lower/digit; symbols
    optional).
    """
    min_length = int(await get_setting("password_min_length", 8) or 0)
    require_upper = bool(await get_setting("password_require_uppercase", True))
    require_lower = bool(await get_setting("password_require_lowercase", True))
    require_digit = bool(await get_setting("password_require_numbers", True))
    require_symbol = bool(await get_setting("password_require_symbols", False))

    password = password or ""
    problems: list[str] = []

    if len(password) < min_length:
        problems.append(f"містити щонайменше {min_length} символів")
    if require_upper and not any(c.isupper() for c in password):
        problems.append("містити велику літеру")
    if require_lower and not any(c.islower() for c in password):
        problems.append("містити малу літеру")
    if require_digit and not any(c.isdigit() for c in password):
        problems.append("містити цифру")
    if require_symbol and not any(not c.isalnum() for c in password):
        problems.append("містити спеціальний символ")

    if problems:
        grunt.throw("Пароль повинен " + "; ".join(problems) + ".", "VALIDATION_ERROR")
