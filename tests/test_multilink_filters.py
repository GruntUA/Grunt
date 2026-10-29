"""Filters on MultiLink fields - list queries and grunt.db go through the junction table."""

import pytest


@pytest.fixture
async def tagged(ctx):
    """Three notes: one tagged red+blue, one blue, one untagged."""
    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": "FilterTag",
            "label": "Filter Tag",
            "module": "core",
            "autoname": "field:title",
            "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
            "__is_new": True,
        }
    )
    await save_doctype(
        doctype_data={
            "name": "FilterNote",
            "label": "Filter Note",
            "module": "core",
            "fields": [
                {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
                {
                    "fieldname": "tags",
                    "label": "Tags",
                    "fieldtype": "MultiLink",
                    "options": "FilterTag",
                },
            ],
            "__is_new": True,
        }
    )
    for tag in ("red", "blue", "green"):
        await ctx.new_doc("FilterTag", {"title": tag})
    for title, tags in (("both", ["red", "blue"]), ("blue", ["blue"]), ("none", [])):
        await ctx.new_doc("FilterNote", {"title": title, "tags": tags})
    await ctx.db._session().commit()
    return ctx


async def _titles(ctx, filters):
    rows = await ctx.db.get_all("FilterNote", filters=filters, fields=["title"], limit=None)
    return sorted(r["title"] for r in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"tags": "red"}, ["both"]),
        ({"tags__eq": "blue"}, ["blue", "both"]),
        ({"tags__in": "red,green"}, ["both"]),
        ({"tags__in": ["green"]}, []),
        ({"tags__ne": "red"}, ["blue", "none"]),
        ({"tags__nin": ["red", "blue"]}, ["none"]),
        ({"tags__is": "set"}, ["blue", "both"]),
        ({"tags__is": "not set"}, ["none"]),
        ({"tags__isnull": True}, ["none"]),
        ({"tags__isnull": False}, ["blue", "both"]),
        ({"tags": "blue", "title__ne": "both"}, ["blue"]),
        # Unsupported operators are skipped, as for unknown columns.
        ({"tags__like": "re"}, ["blue", "both", "none"]),
    ],
)
async def test_db_filters(tagged, filters, expected):
    assert await _titles(tagged, filters) == expected


@pytest.mark.asyncio
async def test_list_and_count(tagged):
    page = await tagged.get_list("FilterNote", filters={"tags": "blue"}, fields=["title"])
    data = page.to_dict()
    assert sorted(r["title"] for r in data["data"]) == ["blue", "both"]
    assert data["meta"]["total"] == 2
    assert await tagged.db.count("FilterNote", {"tags__is": "not set"}) == 1


@pytest.mark.asyncio
async def test_get_all_returns_multilink_values(tagged):
    rows = await tagged.db.get_all(
        "FilterNote", fields=["title", "tags"], limit=None, order_by="title", order="asc"
    )
    assert rows == [
        {"title": "blue", "tags": ["blue"]},
        {"title": "both", "tags": ["red", "blue"]},  # in idx order
        {"title": "none", "tags": []},
    ]
    with_name = await tagged.db.get_all(
        "FilterNote", filters={"title": "blue"}, fields=["name", "tags"]
    )
    assert set(with_name[0]) == {"name", "tags"}


@pytest.mark.asyncio
async def test_set_value_replaces_multilink(tagged):
    name = await tagged.db.get_value("FilterNote", {"title": "none"}, "name")
    await tagged.db.set_value("FilterNote", name, {"tags": ["green", "red"], "title": "now"})
    rows = await tagged.db.get_all(
        "FilterNote", filters={"tags": "green"}, fields=["title", "tags"]
    )
    assert rows == [{"title": "now", "tags": ["green", "red"]}]
    await tagged.db.set_value("FilterNote", name, "tags", [])
    assert await tagged.db.count("FilterNote", {"tags__is": "not set"}) == 1
