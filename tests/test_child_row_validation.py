"""Child-table rows are validated against the child DocType on save, each
error reported on the table field with the row number."""

import pytest
from fastapi import HTTPException

_PARENT = {
    "name": "RvOrder",
    "label": "Rv Order",
    "module": "core",
    "autoname": "field:code",
    "fields": [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True},
        {"fieldname": "items", "label": "Items", "fieldtype": "Table", "options": "RvOrderItem"},
    ],
}

_CHILD = {
    "name": "RvOrderItem",
    "label": "Rv Order Item",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "item", "label": "Item", "fieldtype": "Data", "required": True},
        {"fieldname": "qty", "label": "Qty", "fieldtype": "Int", "min_value": 1},
    ],
}


@pytest.fixture
async def order_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_CHILD, "__is_new": True})
    await save_doctype(doctype_data={**_PARENT, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_invalid_rows_are_rejected_with_their_row_number(ctx, order_doctype):
    from grunt.i18n import use_language

    with use_language("en"), pytest.raises(HTTPException) as exc:
        await ctx.new_doc("RvOrder", {"code": "a", "items": [{"item": "x", "qty": 1}, {"qty": 0}]})
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert all(e.startswith("items: Row 2: ") for e in detail), detail
    assert len(detail) == 2  # Item is required, Qty below the minimum

    await ctx.new_doc("RvOrder", {"code": "a", "items": [{"item": "x", "qty": 1}]})
    with pytest.raises(HTTPException):
        await ctx.save_doc("RvOrder", "a", {"items": [{"item": "x", "qty": -1}]})
    await ctx.save_doc("RvOrder", "a", {"items": [{"item": "y", "qty": 3}]})


@pytest.mark.asyncio
async def test_layout_rows_of_a_doctype_need_no_label(ctx):
    await ctx.new_doc(
        "DocType",
        {
            "name": "RvLayout",
            "label": "Rv Layout",
            "module": "core",
            "fields": [
                {"fieldname": "tab", "fieldtype": "Tab"},
                {"fieldname": "title", "fieldtype": "Data", "label": "Title"},
                {"fieldname": "col", "fieldtype": "Column"},
                {"fieldname": "note", "fieldtype": "Data"},
            ],
        },
    )
