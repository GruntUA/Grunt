"""DocType definitions are rows of the DocType table: the JSON ``definition``
plus its scalar properties in columns, which the DocType list queries like
any regular table."""

from __future__ import annotations

import pytest

from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.metadata import store
from grunt.metadata.doctype import DocType
from grunt.metadata.field import DocField
from grunt.metadata.registry import doctype_registry


def _doctype(name: str, **kw) -> DocType:
    return DocType(
        name=name,
        label=kw.pop("label", name),
        module="test",
        fields=[DocField(fieldname="title", label="Title", fieldtype="Data")],
        **kw,
    )


@pytest.mark.asyncio
async def test_register_writes_definition_and_columns(ctx, db_session, engine):
    await doctype_registry.register(_doctype("StoreItem", label="Store item"), db_session, engine)

    row = await store.get_row(db_session, "StoreItem")
    assert row is not None
    assert row["label"] == "Store item"
    assert row["module"] == "test"
    assert row["is_child"] is False
    assert row["owner"] == SYSTEM_USER.email
    assert row["definition"]["fields"][0]["fieldname"] == "title"


@pytest.mark.asyncio
async def test_update_refreshes_columns_and_delete_removes_row(ctx, db_session, engine):
    await doctype_registry.register(_doctype("StoreEdit"), db_session, engine)

    await doctype_registry.update(_doctype("StoreEdit", label="Renamed"), db_session, engine)
    row = await store.get_row(db_session, "StoreEdit")
    assert row is not None
    assert row["label"] == "Renamed"
    assert row["definition"]["label"] == "Renamed"

    await doctype_registry.delete("StoreEdit", db_session)
    assert not await store.exists(db_session, "StoreEdit")


@pytest.mark.asyncio
async def test_doctype_list_filters_and_searches_the_table(ctx, db_session, engine):
    await doctype_registry.register(_doctype("StoreParent", label="Warehouse"), db_session, engine)
    await doctype_registry.register(_doctype("StoreRow", is_child=True), db_session, engine)

    children = await ctx.get_list("DocType", filters={"is_child": 1}, fields=["name"])
    assert [r["name"] for r in children] == ["StoreRow"]

    found = await ctx.get_list("DocType", search="wareh", fields=["name", "label"])
    assert [r["name"] for r in found] == ["StoreParent"]


@pytest.mark.asyncio
async def test_doctype_form_reads_the_definition(ctx, db_session, engine):
    await doctype_registry.register(_doctype("StoreForm"), db_session, engine)

    doc = await ctx.get_doc("DocType", "StoreForm")
    assert doc["label"] == "StoreForm"
    assert doc["table_name"] == "grunt_test_store_form"
    assert [f["fieldname"] for f in doc["fields"]] == ["title"]
