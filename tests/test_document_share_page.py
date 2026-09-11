"""The public ``/share/{token}`` page is rendered server-side by the website
engine (``grunt/website/www/share/``), which replaced the former
``DocumentShareView.vue`` SPA route. Its controller reuses the guest-accessible
``grunt.api.v1.share.get_shared_document`` service.
"""

from __future__ import annotations

import pytest

SHARE_PAGE_OWNER_DOCTYPE = {
    "name": "SharePageOwner",
    "label": "Share Page Owner",
    "module": "core",
    "title_field": "full_name",
    "fields": [
        {"fieldname": "full_name", "label": "Full Name", "fieldtype": "Text"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True},
    ],
}

SHARE_PAGE_DOCTYPE = {
    "name": "SharePageThing",
    "label": "Share Page Thing",
    "module": "core",
    "fields": [
        {"fieldname": "main_tab", "label": "Overview", "fieldtype": "Tab"},
        {"fieldname": "sec_a", "label": "Summary", "fieldtype": "Section"},
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "owner_ref", "label": "Owner", "fieldtype": "Link", "options": "SharePageOwner"},
        {"fieldname": "col_b", "fieldtype": "Column"},
        {"fieldname": "photo", "label": "Photo", "fieldtype": "Image"},
        {"fieldname": "details_tab", "label": "Details", "fieldtype": "Tab"},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "Text"},
        {"fieldname": "secret", "label": "Secret", "fieldtype": "Text", "hidden": True},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True},
    ],
}


@pytest.fixture
async def _share_page_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**SHARE_PAGE_OWNER_DOCTYPE, "__is_new": True})
    await save_doctype(doctype_data={**SHARE_PAGE_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_share_page_renders_document(ctx, _share_page_doctype, client):
    owner = await ctx.new_doc("SharePageOwner", {"full_name": "Jane Doe"})
    thing = await ctx.new_doc(
        "SharePageThing",
        {
            "title": "Quarterly report",
            "notes": "line 1\nline 2",
            "photo": "/api/v1/files/cover.png",
            "owner_ref": owner["name"],
            "secret": "classified",
        },
    )
    share = await ctx.new_doc(
        "DocumentShare",
        {"doctype_name": "SharePageThing", "doc_id": thing["name"], "is_active": True},
    )
    await ctx.db._session().commit()

    resp = await client.get(f"/share/{share['token']}")

    assert resp.status_code == 200
    body = resp.text
    assert "Share Page Thing" in body  # doctype label / kicker
    assert "Quarterly report" in body  # a field value
    assert "Про документ" in body  # sidebar heading
    # the target DocType's own layout is reproduced: tab + section labels
    assert 'for="tab-0"' in body and "Overview" in body and "Details" in body
    assert "Summary" in body  # section heading
    # an Image field renders as a picture, not its raw path
    assert '<img src="/api/v1/files/cover.png"' in body
    # a Link field shows the target's title, not its raw document id
    assert "Jane Doe" in body
    assert owner["name"] not in body
    # hidden fields never reach the public page
    assert "classified" not in body


@pytest.mark.asyncio
async def test_share_page_shows_friendly_error_for_unknown_token(client):
    resp = await client.get("/share/definitely-not-a-real-token")

    assert resp.status_code == 200
    assert "Зверніться до власника документа" in resp.text
