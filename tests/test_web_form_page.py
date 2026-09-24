"""The public ``/form/{route}`` page is rendered server-side by the website
engine (``grunt/website/www/form/``), replacing the former ``PublicWebForm.vue``
SPA route. GET renders the form; POST runs the submission through the same
``grunt.webform.service`` the JSON API uses, as an anonymous guest.
"""

from __future__ import annotations

import pytest

TARGET = {
    "name": "WebFormPageTarget",
    "label": "Web Form Page Target",
    "module": "core",
    "fields": [
        {"fieldname": "full_name", "label": "Full name", "fieldtype": "Text", "required": True},
        {"fieldname": "note", "label": "Note", "fieldtype": "LongText"},
    ],
    # Guest create — anonymous SSR submissions run as the synthetic Guest user.
    "permissions": [{"role": "Guest", "read": True, "create": True}],
}


@pytest.fixture
async def _published_form(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**TARGET, "__is_new": True})
    await ctx.db._session().commit()

    await ctx.new_doc(
        "WebForm",
        {
            "title": "Contact us",
            "route": "contact-us",
            "doctype": "WebFormPageTarget",
            "fields": [{"fieldname": "full_name"}, {"fieldname": "note"}],
            "introduction": "Tell us what you need",
            "success_message": "We got it.",
            "is_published": True,
            "login_required": False,
        },
    )
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_form_page_renders_fields(ctx, _published_form, client):
    resp = await client.get("/form/contact-us")

    assert resp.status_code == 200
    body = resp.text
    assert "Contact us" in body
    assert "Tell us what you need" in body
    assert 'name="full_name"' in body
    assert 'name="note"' in body


@pytest.mark.asyncio
async def test_form_page_submits_as_guest(ctx, _published_form, client):
    resp = await client.post(
        "/form/contact-us",
        data={"full_name": "Ada Lovelace", "note": "hello"},
    )

    assert resp.status_code == 200
    assert "Дякуємо!" in resp.text
    assert "We got it." in resp.text

    rows = await ctx.db.get_all("WebFormPageTarget", filters={"full_name": "Ada Lovelace"})
    assert len(rows) == 1
    assert rows[0]["owner"] == "guest@grunt.local"


@pytest.mark.asyncio
async def test_form_page_reports_validation_error(ctx, _published_form, client):
    resp = await client.post("/form/contact-us", data={"full_name": "", "note": "x"})

    assert resp.status_code == 200
    body = resp.text
    # error banner is shown (message text is HTML-escaped by Jinja autoescape,
    # so match a fragment with no apostrophe)
    assert 'class="banner error"' in body
    assert "язковим" in body
    # the form is re-rendered (not the success state) with the note preserved
    assert "Дякуємо!" not in body
    assert ">x</textarea>" in body


@pytest.mark.asyncio
async def test_form_page_unknown_route(client):
    resp = await client.get("/form/no-such-form")

    assert resp.status_code == 200
    assert "Форму не знайдено" in resp.text


def test_prepare_fields_html_block_and_datalist():
    import importlib.util
    from pathlib import Path

    import grunt.website

    path = Path(grunt.website.__file__).parent / "www" / "form" / "{route}.py"
    spec = importlib.util.spec_from_file_location("form_route", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = mod._prepare_fields(
        [
            {"fieldname": "hint", "fieldtype": "HTML", "label": "Hint", "options": "<b>Увага</b>"},
            {"fieldname": "go", "fieldtype": "Button", "label": "Go"},
            {"fieldname": "position", "fieldtype": "Data", "label": "Posada", "options": "A\nB"},
            {"fieldname": "amount", "fieldtype": "Currency", "label": "Sum", "options": "currency"},
        ]
    )
    assert out[0] == {"kind": "html", "content": "<b>Увага</b>"}
    assert [f.get("fieldname") for f in out[1:]] == ["position", "amount"]
    assert out[1]["options"] == ["A", "B"]
    assert out[2]["options"] == [] and out[2]["number_step"] == "0.01"
