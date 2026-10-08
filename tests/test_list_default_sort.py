"""DocType ``sort_field``/``sort_order``: the list order when a request sends none."""

import pytest

pytestmark = pytest.mark.asyncio


SORTED_DT = {
    "name": "SortedItem",
    "label": "Sorted Item",
    "module": "core",
    "sort_field": "rank",
    "sort_order": "asc",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "in_list_view": True},
        {"fieldname": "rank", "label": "Rank", "fieldtype": "Int"},
    ],
    "permissions": [{"role": "All", "read": True}],
}


@pytest.fixture
async def sorted_items(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**SORTED_DT, "__is_new": True})
    for title, rank in (("b", 2), ("c", 3), ("a", 1)):
        await ctx.new_doc("SortedItem", {"title": title, "rank": rank})
    await ctx.db._session().commit()


async def _titles(client, headers, **params) -> list[str]:
    r = await client.get("/api/v1/docs/SortedItem", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return [row["title"] for row in r.json()["data"]]


async def test_list_uses_doctype_default_sort(client, auth_headers, sorted_items):
    assert await _titles(client, auth_headers) == ["a", "b", "c"]
    assert await _titles(client, auth_headers, sort_order="desc") == ["c", "b", "a"]


async def test_explicit_sort_wins(client, auth_headers, sorted_items):
    assert await _titles(client, auth_headers, sort_by="rank", sort_order="desc") == ["c", "b", "a"]
    assert await _titles(client, auth_headers, sort_by="modified_at") == ["a", "c", "b"]


async def test_rpc_get_list_uses_default_sort(ctx, sorted_items):
    from grunt.api.v1.documents import get_list

    rows = (await get_list("SortedItem", fields=["title"]))["data"]
    assert [r["title"] for r in rows] == ["a", "b", "c"]
