"""The public ``/share/{token}`` page is rendered server-side by the website
engine (``grunt/website/www/share/``), which replaced the former
``DocumentShareView.vue`` SPA route. Its controller reuses the guest-accessible
``grunt.api.v1.share.get_shared_document`` service.
"""

from __future__ import annotations

import pytest

SHARE_PAGE_DOCTYPE = {
    "name": "SharePageThing",
    "label": "Share Page Thing",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "Text"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True},
    ],
}


@pytest.fixture
async def _share_page_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**SHARE_PAGE_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_share_page_renders_document(ctx, _share_page_doctype, client):
    thing = await ctx.new_doc(
        "SharePageThing", {"title": "Quarterly report", "notes": "line 1\nline 2"}
    )
    share = await ctx.new_doc(
        "DocumentShare",
        {"doctype_name": "SharePageThing", "doc_id": thing["name"], "is_active": True},
    )
    await ctx.db._session().commit()

    resp = await client.get(f"/share/{share['token']}")

    assert resp.status_code == 200
    body = resp.text
    assert "Share Page Thing" in body  # doctype label
    assert "Quarterly report" in body  # a field value
    assert "Дані документа" in body  # template chrome


@pytest.mark.asyncio
async def test_share_page_shows_friendly_error_for_unknown_token(client):
    resp = await client.get("/share/definitely-not-a-real-token")

    assert resp.status_code == 200
    assert "Зверніться до власника документа" in resp.text
