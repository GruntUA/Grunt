"""Password policy enforcement driven by SystemSettings."""

from __future__ import annotations

import pytest

from grunt.api.messages import ApplicationError
from grunt.auth.password_policy import enforce_password_policy
from grunt.site.settings import clear_settings_cache


async def _configure(ctx, **values) -> None:
    await ctx.db.set_value("SystemSettings", "SystemSettings", values)
    await ctx.db._session().commit()
    clear_settings_cache()


@pytest.mark.asyncio
async def test_min_length_enforced(ctx):
    await _configure(
        ctx,
        password_min_length=10,
        password_require_uppercase=False,
        password_require_lowercase=False,
        password_require_numbers=False,
        password_require_symbols=False,
    )

    with pytest.raises(ApplicationError) as excinfo:
        await enforce_password_policy("short123")
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert "10" in excinfo.value.message

    await enforce_password_policy("longenough123")  # no raise


@pytest.mark.asyncio
async def test_character_classes_enforced(ctx):
    await _configure(
        ctx,
        password_min_length=4,
        password_require_uppercase=True,
        password_require_lowercase=True,
        password_require_numbers=True,
        password_require_symbols=True,
    )

    with pytest.raises(ApplicationError) as excinfo:
        await enforce_password_policy("alllowercase")
    msg = excinfo.value.message
    # one combined message lists every unmet requirement
    assert "велику літеру" in msg
    assert "цифру" in msg
    assert "спеціальний символ" in msg
    assert "малу літеру" not in msg  # this one *is* satisfied

    await enforce_password_policy("Aa1!")  # satisfies all four


@pytest.mark.asyncio
async def test_disabled_requirements_are_skipped(ctx):
    await _configure(
        ctx,
        password_min_length=6,
        password_require_uppercase=False,
        password_require_lowercase=False,
        password_require_numbers=False,
        password_require_symbols=False,
    )
    # all-lowercase, no digits — fine when nothing but length is required
    await enforce_password_policy("abcdef")


@pytest.mark.asyncio
async def test_defaults_used_when_setting_missing(ctx):
    # Only length set; the require_* NULLs must fall back to their field
    # defaults (upper/lower/digit required, symbols optional).
    await _configure(
        ctx,
        password_min_length=8,
        password_require_uppercase=None,
        password_require_lowercase=None,
        password_require_numbers=None,
        password_require_symbols=None,
    )

    with pytest.raises(ApplicationError):
        await enforce_password_policy("alllowercaseletters")

    await enforce_password_policy("Str0ngPass")  # upper + lower + digit, 10 chars
