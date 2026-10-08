"""Letterheads on printed documents, and the ``qr`` print filter."""

from __future__ import annotations

import pytest

from grunt.print.filters import qr
from grunt.print.renderer import apply_letter_head, render_print_html

MEMO = {
    "name": "Memo",
    "label": "Memo",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True}
    ],
}

BODY = "<html><body><p>Body {{ doc.title }}</p></body></html>"


def test_qr_filter():
    img = str(qr("https://example.com/doc/42"))
    assert img.startswith('<img src="data:image/svg+xml')
    assert "width:30mm" in img
    assert "20mm" in str(qr("x", "20mm"))
    assert str(qr("")) == "" and str(qr(None)) == ""


def test_apply_letter_head_wraps_the_body():
    lh = {"header": "<b>HEAD</b>", "footer": "<i>FOOT</i>"}
    html = apply_letter_head('<html><body class="a"><p>x</p></body></html>', lh)
    assert html == (
        '<html><body class="a"><div class="letter-head"><b>HEAD</b></div><p>x</p>'
        '<div class="letter-foot"><i>FOOT</i></div></body></html>'
    )
    # No footer -> nothing added at the end; no <body> -> header goes first.
    assert apply_letter_head("<p>x</p>", {"header": "H", "footer": ""}).startswith(
        '<div class="letter-head">H</div>'
    )


@pytest.fixture
async def memo(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**MEMO, "__is_new": True})
    doc = await ctx.new_doc("Memo", {"title": "Hello"})
    await ctx.db._session().commit()
    return doc


async def _letter_head(ctx, title, **values):
    return await ctx.new_doc(
        "LetterHead",
        {"title": title, "header": f"<h1>{title} {{{{ doc.title }}}}</h1>", **values},
    )


async def _format(ctx, name, template=BODY, **values):
    return await ctx.new_doc(
        "PrintFormat",
        {
            "name": name,
            "ref_doctype": "Memo",
            "template_type": "html",
            "template": template,
            **values,
        },
    )


@pytest.mark.asyncio
async def test_default_letter_head_is_inserted(ctx, memo):
    await _letter_head(ctx, "City Council", is_default=True, footer="<small>Kyiv</small>")
    await _format(ctx, "memo-plain", is_default=True)

    html = await render_print_html("Memo", memo)
    assert html.index("<h1>City Council Hello</h1>") < html.index("<p>Body Hello</p>")
    assert html.index("<p>Body Hello</p>") < html.index("<small>Kyiv</small>")

    # Also on the standard template, when no print format exists for a DocType.
    await ctx.delete_doc("PrintFormat", "memo-plain")
    assert "<h1>City Council Hello</h1>" in await render_print_html("Memo", memo)


@pytest.mark.asyncio
async def test_template_places_the_letter_head_itself(ctx, memo):
    await _letter_head(ctx, "Council", is_default=True)
    await _format(
        ctx,
        "memo-placed",
        template="<body><main>{{ letter_head.header }}</main><p>Body</p></body>",
    )
    html = await render_print_html("Memo", memo, "memo-placed")
    assert "<main><h1>Council Hello</h1></main>" in html
    assert html.count("Council Hello") == 1


@pytest.mark.asyncio
async def test_choice_opt_out_and_disabled(ctx, memo):
    await _letter_head(ctx, "Default", is_default=True)
    await _letter_head(ctx, "Finance")
    await _letter_head(ctx, "Old", disabled=True)
    await _format(ctx, "memo-finance", letter_head="Finance")
    await _format(ctx, "memo-bare", no_letter_head=True)
    await _format(ctx, "memo-old", letter_head="Old")

    finance = await render_print_html("Memo", memo, "memo-finance")
    assert "Finance Hello" in finance and "Default Hello" not in finance
    assert "letter-head" not in await render_print_html("Memo", memo, "memo-bare")
    assert "letter-head" not in await render_print_html("Memo", memo, "memo-old")


@pytest.mark.asyncio
async def test_single_default_and_embedded_logo(ctx, memo):
    from grunt.storage import files

    png = b"\x89PNG\r\n\x1a\nfake-logo"
    stored = await files.store(png, "logo.png", "image/png")
    logo_url = files.CONTENT_URL.format(stored["name"])

    await _letter_head(ctx, "First", is_default=True)
    await _letter_head(
        ctx,
        "Second",
        is_default=True,
        logo=logo_url,
        header='<img src="{{ letter_head.logo }}">',
    )
    defaults = await ctx.db.get_all("LetterHead", filters={"is_default": True}, fields=["name"])
    assert [r["name"] for r in defaults] == ["Second"]

    html = await render_print_html("Memo", memo)
    assert '<img src="data:image/png;base64,' in html
    assert "get_content" not in html
