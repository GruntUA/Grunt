"""Regression tests for WebFormService.submit().

submit() used to wrap the create call in `grunt.context(session, user=None)`,
which made write_guard's require_user() raise RuntimeError unconditionally —
every submission (guest or authenticated) crashed before a document was ever
created. Fixed by running anonymous submissions as a synthetic, non-superadmin
Guest identity (so the target DocType's own create-permission rules still
apply) and authenticated submissions under the caller's real context.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

TARGET_OPEN = {
    "name": "WebFormTargetOpen",
    "label": "Web Form Target Open",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
}

TARGET_GUARDED = {
    "name": "WebFormTargetGuarded",
    "label": "Web Form Target Guarded",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [{"role": "Admin", "read": True, "create": True}],
}

TARGET_GUEST_ALLOWED = {
    "name": "WebFormTargetGuestOk",
    "label": "Web Form Target Guest Ok",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [{"role": "Guest", "read": True, "create": True}],
}


async def _create_webform(ctx, target_doctype_name: str, route: str):
    await ctx.new_doc(
        "WebForm",
        {
            "title": "Test Form",
            "route": route,
            "doctype": target_doctype_name,
            "fields": [{"fieldname": "title"}],
            "is_published": True,
            "login_required": False,
        },
    )
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_submit_anonymous_open_doctype(ctx):
    """No permissions defined on the target = open (dev mode) — guest can submit."""
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_OPEN, "__is_new": True})
    await ctx.db._session().commit()
    await _create_webform(ctx, "WebFormTargetOpen", "open-form")

    result = await web_form_service.submit(
        route="open-form", data={"title": "Hello"}, user_email=None
    )
    assert result["id"]

    doc = await ctx.get_doc("WebFormTargetOpen", result["id"])
    assert doc["owner"] == "guest@grunt.local"


@pytest.mark.asyncio
async def test_submit_anonymous_denied_without_guest_permission(ctx):
    """Target restricts create to Admin only — anonymous submit must be denied,
    not silently succeed as some elevated identity.
    """
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_GUARDED, "__is_new": True})
    await ctx.db._session().commit()
    await _create_webform(ctx, "WebFormTargetGuarded", "guarded-form")

    with pytest.raises(HTTPException) as exc_info:
        await web_form_service.submit(
            route="guarded-form",
            data={"title": "Hello"},
            user_email=None,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_submit_anonymous_allowed_with_guest_permission(ctx):
    """Target explicitly grants the Guest role create — anonymous submit works."""
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_GUEST_ALLOWED, "__is_new": True})
    await ctx.db._session().commit()
    await _create_webform(ctx, "WebFormTargetGuestOk", "guest-ok-form")

    result = await web_form_service.submit(
        route="guest-ok-form",
        data={"title": "Hello"},
        user_email=None,
    )
    assert result["id"]


@pytest.mark.asyncio
async def test_submit_authenticated_sets_real_owner(ctx, db_session, engine):
    """Authenticated submission runs under the caller's own identity and
    attributes the document to them, not to the synthetic Guest user.
    """
    from grunt.api.v1.meta import save_doctype
    from grunt.app import grunt
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_OPEN, "__is_new": True})
    await ctx.db._session().commit()
    await _create_webform(ctx, "WebFormTargetOpen", "open-form-auth")

    alice = make_user("alice@example.com", roles=["Employee"])
    async with grunt.context(db_session, engine, alice):
        result = await web_form_service.submit(
            route="open-form-auth",
            data={"title": "Hello"},
            user_email="alice@example.com",
        )

    doc = await ctx.get_doc("WebFormTargetOpen", result["id"])
    assert doc["owner"] == "alice@example.com"
