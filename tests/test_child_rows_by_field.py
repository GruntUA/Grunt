"""The rows of a child table belong to one field of one document: a child
DocType may serve two table fields of a parent, and two parent DocTypes -
loading, saving and aggregating one field never touches the others' rows."""

import pytest

import grunt
from grunt.api.v1.meta import save_doctype

_LINE = {
    "name": "CrLine",
    "label": "Cr Line",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "item", "label": "Item", "fieldtype": "Data"},
        {"fieldname": "qty", "label": "Qty", "fieldtype": "Int"},
    ],
}


def _parent(name: str) -> dict:
    return {
        "name": name,
        "label": name,
        "module": "core",
        "autoname": "field:code",
        "fields": [
            {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": 1},
            {"fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "CrLine"},
            {"fieldname": "extras", "label": "Extras", "fieldtype": "Table", "options": "CrLine"},
            {
                "fieldname": "lines_qty",
                "label": "Lines qty",
                "fieldtype": "Int",
                "aggregate_function": "sum",
                "aggregate_table": "lines",
                "aggregate_field": "qty",
            },
            {
                "fieldname": "extras_count",
                "label": "Extras count",
                "fieldtype": "Int",
                "aggregate_function": "count",
                "aggregate_table": "extras",
            },
        ],
        "permissions": [
            {"role": "System Manager", "actions": ["read", "write", "create", "delete"]}
        ],
    }


@pytest.fixture
async def doctypes(ctx):
    await save_doctype(doctype_data={**_LINE, "__is_new": True})
    for name in ("CrOrder", "CrQuote"):
        await save_doctype(doctype_data={**_parent(name), "__is_new": True})
    await ctx.db._session().commit()


def _rows(rows) -> list[tuple]:
    return [(r["item"], r["qty"]) for r in rows]


@pytest.mark.asyncio
async def test_two_fields_of_one_child_doctype_keep_their_rows(doctypes):
    await grunt.new_doc(
        "CrOrder",
        {
            "code": "A",
            "lines": [{"item": "x", "qty": 1}, {"item": "y", "qty": 2}],
            "extras": [{"item": "gift", "qty": 1}],
        },
    )
    doc = await grunt.get_doc("CrOrder", "A")
    assert _rows(doc.lines) == [("x", 1), ("y", 2)]
    assert _rows(doc.extras) == [("gift", 1)]
    assert doc.lines_qty == 3
    assert doc.extras_count == 1

    # Saving one field leaves the other's rows alone.
    await grunt.save_doc("CrOrder", "A", {"extras": [{"item": "card", "qty": 5}]})
    doc = await grunt.get_doc("CrOrder", "A")
    assert _rows(doc.lines) == [("x", 1), ("y", 2)]
    assert _rows(doc.extras) == [("card", 5)]
    assert doc.lines_qty == 3


@pytest.mark.asyncio
async def test_parents_of_two_doctypes_with_one_name_keep_their_rows(doctypes):
    await grunt.new_doc("CrOrder", {"code": "A", "lines": [{"item": "order", "qty": 1}]})
    await grunt.new_doc("CrQuote", {"code": "A", "lines": [{"item": "quote", "qty": 7}]})

    order = await grunt.get_doc("CrOrder", "A")
    quote = await grunt.get_doc("CrQuote", "A")
    assert _rows(order.lines) == [("order", 1)]
    assert _rows(quote.lines) == [("quote", 7)]
    assert order.lines_qty == 1 and quote.lines_qty == 7


def test_a_child_row_name_fits_the_name_column():
    from grunt.document.relations import child_row_name

    assert child_row_name("CrOrder", "A", "lines", 0) == "CrOrder-A-lines-0"
    long = child_row_name("CrOrder", "x" * 300, "lines", 12)
    assert len(long) <= 255 and long.endswith("-12")
    assert long != child_row_name("CrQuote", "x" * 300, "lines", 12)
