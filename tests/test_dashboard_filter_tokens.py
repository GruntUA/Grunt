"""Widget filters resolved at query time: ``@me`` and ``@<Singleton>.<field>``."""

import pytest

from grunt.api.v1.dashboard import _NO_MATCH, _resolve_context_tokens
from tests.support import make_user

pytestmark = pytest.mark.asyncio

SETTINGS_DT = {
    "name": "FtSettings",
    "label": "Ft Settings",
    "module": "core",
    "is_singleton": True,
    "fields": [
        {"fieldname": "current_period", "label": "Period", "fieldtype": "Text"},
        {"fieldname": "secret", "label": "Secret", "fieldtype": "Password"},
    ],
    "permissions": [{"role": "Reader", "read": True}],
}


@pytest.fixture
async def settings(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**SETTINGS_DT, "__is_new": True})
    await ctx.new_doc(
        "FtSettings", {"name": "FtSettings", "current_period": "2026-Q4", "secret": "s3cret"}
    )
    await ctx.db._session().commit()


async def _as(ctx, user, filters):
    async with ctx.context(ctx.get_session(), None, user):
        return await _resolve_context_tokens(filters)


async def test_setting_and_me_are_resolved(ctx, settings):
    reader = make_user("reader@test", ["Reader"])
    got = await _as(
        ctx,
        reader,
        {"period": "@FtSettings.current_period", "owner": "@me", "status": "Готово"},
    )
    assert got == {"period": "2026-Q4", "owner": "reader@test", "status": "Готово"}


async def test_password_and_unreadable_settings_match_nothing(ctx, settings):
    reader = make_user("reader@test", ["Reader"])
    assert await _as(ctx, reader, {"x": "@FtSettings.secret"}) == {"x": _NO_MATCH}
    stranger = make_user("stranger@test", ["Other"])
    assert await _as(ctx, stranger, {"x": "@FtSettings.current_period"}) == {"x": _NO_MATCH}
    # Not a singleton / unknown doctype / unknown field.
    assert await _as(ctx, reader, {"x": "@User.email"}) == {"x": _NO_MATCH}
    assert await _as(ctx, reader, {"x": "@Nope.field"}) == {"x": _NO_MATCH}
    assert await _as(ctx, reader, {"x": "@FtSettings.nope"}) == {"x": _NO_MATCH}
