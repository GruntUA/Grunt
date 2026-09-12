"""Document Connections service — grouped counts + previews behind the
"Зв'язки" panel.

Covers the two link shapes and the rule that the ``links`` table is
authoritative: a DocType with no declared rows shows no connection chips.
"""

from __future__ import annotations

import pytest

ASSET_DT = {
    "name": "ConnAsset",
    "label": "Conn Asset",
    "module": "core",
    "title_field": "title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
    ],
}

ORDER_DT = {
    "name": "ConnOrder",
    "label": "Conn Order",
    "module": "core",
    "title_field": "title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {"fieldname": "asset", "label": "Asset", "fieldtype": "Link", "options": "ConnAsset"},
    ],
}


@pytest.fixture
async def conn_doctypes(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**ASSET_DT, "__is_new": True})
    await save_doctype(doctype_data={**ORDER_DT, "__is_new": True})
    await ctx.db._session().commit()

    asset = await ctx.new_doc("ConnAsset", {"title": "Excavator"})
    o1 = await ctx.new_doc("ConnOrder", {"title": "Order 1", "asset": asset["name"]})
    await ctx.new_doc("ConnOrder", {"title": "Order 2", "asset": asset["name"]})
    await ctx.new_doc("ConnOrder", {"title": "Unrelated", "asset": None})
    await ctx.db._session().commit()
    return {"asset": asset, "o1": o1}


@pytest.mark.asyncio
async def test_no_connections_without_declared_links(ctx, conn_doctypes):
    """A DocType with no declared `links` shows no chips — nothing is derived."""
    from grunt.document.connections import get_connections

    res = await get_connections("ConnAsset", conn_doctypes["asset"]["name"])
    links = [link for g in res["groups"] for link in g["links"]]
    assert links == []


def test_incomplete_and_null_link_rows_are_tolerated():
    """A row with no link_doctype (nulls from the editor) is dropped, not an error."""
    from grunt.metadata.doctype import DocType

    dt = DocType(
        name="X",
        label="X",
        module="core",
        links=[
            {"link_doctype": None, "link_fieldname": "asset", "group": None, "label": None},
            {"link_doctype": "ConnOrder", "link_fieldname": "asset", "group": None},
        ],
    )
    dumped = dt.model_dump()["links"]
    assert len(dumped) == 1
    assert dumped[0]["link_doctype"] == "ConnOrder"
    assert dumped[0]["group"] == ""
    assert dumped[0]["label"] == ""


@pytest.mark.asyncio
async def test_declared_links_are_used_verbatim(ctx, conn_doctypes):
    """An explicit `links` row is used verbatim (label override, grouping)."""
    from grunt.api.v1.meta import get_doctype, save_doctype
    from grunt.document.connections import get_connections

    data = await get_doctype("ConnAsset")
    data["links"] = [
        {
            "link_doctype": "ConnOrder",
            "link_fieldname": "asset",
            "group": "Логістика",
            "label": "Ордери",
        }
    ]
    await save_doctype(doctype_data=data)
    await ctx.db._session().commit()

    res = await get_connections("ConnAsset", conn_doctypes["asset"]["name"])
    assert [g["name"] for g in res["groups"]] == ["Логістика"]
    link = res["groups"][0]["links"][0]
    assert link["label"] == "Ордери"
    assert link["count"] == 2


@pytest.mark.asyncio
async def test_hidden_link_is_skipped(ctx, conn_doctypes):
    from grunt.api.v1.meta import get_doctype, save_doctype
    from grunt.document.connections import get_connections

    data = await get_doctype("ConnAsset")
    data["links"] = [{"link_doctype": "ConnOrder", "link_fieldname": "asset", "hidden": True}]
    await save_doctype(doctype_data=data)
    await ctx.db._session().commit()

    res = await get_connections("ConnAsset", conn_doctypes["asset"]["name"])
    # declared-but-hidden → suppressed, and no fallback to derivation
    links = [link for g in res["groups"] for link in g["links"]]
    assert not any(link["link_doctype"] == "ConnOrder" for link in links)
