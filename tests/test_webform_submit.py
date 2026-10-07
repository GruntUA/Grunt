"""Regression tests for WebFormService.submit().

submit() used to wrap the create call in `grunt.context(session, user=None)`,
which made write_guard's require_user() raise RuntimeError unconditionally —
every submission (guest or authenticated) crashed before a document was ever
created. Fixed by running anonymous submissions as a synthetic, non-admin
Guest identity (so the target DocType's own create-permission rules still
apply) and authenticated submissions under the caller's real context.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.support import make_user

TARGET_OPEN = {
    "name": "WebFormTargetOpen",
    "label": "Web Form Target Open",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [{"role": "All", "read": True, "write": True, "create": True}],
}

TARGET_WITH_EMAIL = {
    "name": "WebFormTargetWithEmail",
    "label": "Web Form Target With Email",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "Text"},
        {
            "fieldname": "email",
            "label": "Email",
            "fieldtype": "Text",
            "validator": "email",
        },
    ],
    "permissions": [{"role": "All", "read": True, "write": True, "create": True}],
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
            "ref_doctype": target_doctype_name,
            "fields": [{"fieldname": "title"}],
            "is_published": True,
            "login_required": False,
        },
    )
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_submit_anonymous_open_doctype(ctx):
    """Target grants create to role "All" — guest can submit."""
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
    import grunt
    from grunt.api.v1.meta import save_doctype
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


async def _create_webform_login_required(ctx, target_doctype_name: str, route: str):
    await ctx.new_doc(
        "WebForm",
        {
            "title": "Test Form",
            "route": route,
            "ref_doctype": target_doctype_name,
            "fields": [{"fieldname": "title"}],
            "is_published": True,
            "login_required": True,
        },
    )
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_api_submit_form_rejects_anonymous_when_login_required(ctx, db_session, engine):
    """api.v1.webform.submit_form (not the service directly) for a guest request.

    Regression: submit_form used to read the current user through a helper
    that fell back to a synthetic "system" user for unauthenticated requests — so
    user_email was always truthy and `login_required` could never actually
    block an anonymous submission. Simulates the dispatcher's own guest
    context (user=None) rather than calling the service layer directly.
    """
    import grunt
    from grunt.api.v1.meta import save_doctype
    from grunt.api.v1.webform import submit_form

    await save_doctype(doctype_data={**TARGET_OPEN, "__is_new": True})
    await ctx.db._session().commit()
    await _create_webform_login_required(ctx, "WebFormTargetOpen", "login-required-form")

    async with grunt.context(db_session, engine, None):
        with pytest.raises(Exception) as exc_info:  # noqa: B017 - ApplicationError
            await submit_form(route="login-required-form", data={"title": "Hello"})
        assert "авторизація" in str(exc_info.value) or "SUBMISSION_ERROR" in str(
            getattr(exc_info.value, "code", "")
        )


@pytest.mark.asyncio
async def test_api_submit_form_allows_authenticated_when_login_required(ctx, db_session, engine):
    """Same login_required form, but an authenticated caller — must succeed."""
    import grunt
    from grunt.api.v1.meta import save_doctype
    from grunt.api.v1.webform import submit_form

    await save_doctype(doctype_data={**TARGET_OPEN, "__is_new": True})
    await ctx.db._session().commit()
    await _create_webform_login_required(ctx, "WebFormTargetOpen", "login-required-form-2")

    alice = make_user("alice@example.com", roles=["Employee"])
    async with grunt.context(db_session, engine, alice):
        result = await submit_form(route="login-required-form-2", data={"title": "Hello"})

    doc = await ctx.get_doc("WebFormTargetOpen", result["id"])
    assert doc["owner"] == "alice@example.com"


@pytest.mark.asyncio
async def test_get_form_fields_preserves_builder_order_and_label_override(ctx):
    """WebFormField.idx (not the target DocType's own field order) drives the
    form's field order, and a per-form label override wins over the target's.
    """
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_WITH_EMAIL, "__is_new": True})
    await ctx.db._session().commit()

    await ctx.new_doc(
        "WebForm",
        {
            "title": "Ordered Form",
            "route": "ordered-form",
            "ref_doctype": "WebFormTargetWithEmail",
            "is_published": True,
            "fields": [
                {"fieldname": "notes"},
                {"fieldname": "title", "label": "Заголовок звернення"},
                {"fieldname": "email"},
            ],
        },
    )
    await ctx.db._session().commit()

    fields = await web_form_service.get_form_fields("ordered-form")
    assert [f["fieldname"] for f in fields] == ["notes", "title", "email"]
    assert fields[1]["label"] == "Заголовок звернення"
    # fieldtype/validator always come live from the target DocType, not the
    # WebFormField row (which didn't specify them at all here).
    assert fields[2]["validator"] == "email"


@pytest.mark.asyncio
async def test_get_form_fields_includes_layout_markers(ctx):
    """Tab/Section/Column rows pass through as layout markers, not fields."""
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_WITH_EMAIL, "__is_new": True})
    await ctx.db._session().commit()

    await ctx.new_doc(
        "WebForm",
        {
            "title": "Sectioned Form",
            "route": "sectioned-form",
            "ref_doctype": "WebFormTargetWithEmail",
            "is_published": True,
            "fields": [
                {"fieldname": "sec_contact", "fieldtype": "Section", "label": "Контакти"},
                {"fieldname": "title"},
            ],
        },
    )
    await ctx.db._session().commit()

    fields = await web_form_service.get_form_fields("sectioned-form")
    assert fields[0]["fieldtype"] == "Section"
    assert fields[0]["label"] == "Контакти"
    assert fields[1]["fieldname"] == "title"


@pytest.mark.asyncio
async def test_required_override_forces_required(ctx):
    """A field the target DocType leaves optional can be forced required just
    for this form via WebFormField.required.
    """
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service
    from grunt.webform.service import WebFormError

    await save_doctype(doctype_data={**TARGET_WITH_EMAIL, "__is_new": True})
    await ctx.db._session().commit()

    await ctx.new_doc(
        "WebForm",
        {
            "title": "Required Override Form",
            "route": "required-override-form",
            "ref_doctype": "WebFormTargetWithEmail",
            "is_published": True,
            "fields": [
                {"fieldname": "title"},
                {"fieldname": "notes", "required": True},
            ],
        },
    )
    await ctx.db._session().commit()

    with pytest.raises(WebFormError, match="обов'язковим"):
        await web_form_service.submit(
            route="required-override-form", data={"title": "Hello"}, user_email=None
        )


@pytest.mark.asyncio
async def test_submit_queues_confirmation_email_to_submitter_and_notify_list(ctx):
    """A successful submission with confirmation_template set queues one email
    to the submitter's own email field and one to each notify_emails address.
    """
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_WITH_EMAIL, "__is_new": True})
    await ctx.db._session().commit()

    await ctx.new_doc(
        "EmailTemplate",
        {
            "name": "webform-confirmation",
            "label": "Webform confirmation",
            "is_active": True,
            "subject": "Дякуємо, {title}!",
            "body": "Ваше звернення {doc_id} прийнято.",
        },
    )
    await ctx.db._session().commit()

    await ctx.new_doc(
        "WebForm",
        {
            "title": "Email Form",
            "route": "email-form",
            "ref_doctype": "WebFormTargetWithEmail",
            "is_published": True,
            "confirmation_template": "webform-confirmation",
            "notify_emails": "staff@example.com,\nsecond@example.com",
            "fields": [{"fieldname": "title"}, {"fieldname": "email"}],
        },
    )
    await ctx.db._session().commit()

    with patch("grunt.email.templates.queue", new=AsyncMock(return_value="q1")) as mock_queue:
        result = await web_form_service.submit(
            route="email-form",
            data={"title": "Hello", "email": "submitter@example.com"},
            user_email=None,
        )

    assert result["id"]
    sent_to = {call.kwargs["to"] for call in mock_queue.await_args_list}
    assert sent_to == {"submitter@example.com", "staff@example.com", "second@example.com"}
    for call in mock_queue.await_args_list:
        assert call.kwargs["name"] == "webform-confirmation"


@pytest.mark.asyncio
async def test_submit_notify_failure_does_not_fail_submission(ctx):
    """A broken confirmation_template (e.g. deleted) must not take down the
    submission — the document is already created by the time email fires.
    """
    from grunt.api.v1.meta import save_doctype
    from grunt.webform import web_form_service

    await save_doctype(doctype_data={**TARGET_WITH_EMAIL, "__is_new": True})
    await ctx.db._session().commit()

    await ctx.new_doc(
        "WebForm",
        {
            "title": "Broken Email Form",
            "route": "broken-email-form",
            "ref_doctype": "WebFormTargetWithEmail",
            "is_published": True,
            "confirmation_template": "does-not-exist",
            "fields": [{"fieldname": "title"}, {"fieldname": "email"}],
        },
    )
    await ctx.db._session().commit()

    result = await web_form_service.submit(
        route="broken-email-form",
        data={"title": "Hello", "email": "submitter@example.com"},
        user_email=None,
    )
    assert result["id"]
