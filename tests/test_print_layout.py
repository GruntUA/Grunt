"""The standard print layout: the form's layout, values formatted on the server."""

import pytest

from grunt.print.layout import PrintField, PrintTable, build_print_layout
from grunt.print.renderer import render_print_html

_CUSTOMER = {
    "name": "PlCustomer",
    "label": "Customer",
    "module": "core",
    "title_field": "customer_name",
    "fields": [{"fieldname": "customer_name", "label": "Customer name", "fieldtype": "Data"}],
}

_ITEM = {
    "name": "PlItem",
    "label": "Item",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "item", "label": "Item", "fieldtype": "Data", "in_list_view": True},
        {"fieldname": "qty", "label": "Qty", "fieldtype": "Float", "in_list_view": True},
        {
            "fieldname": "amount",
            "label": "Amount",
            "fieldtype": "Currency",
            "options": "UAH",
            "in_list_view": True,
        },
        {"fieldname": "unused", "label": "Unused", "fieldtype": "Data", "in_list_view": True},
        {"fieldname": "note", "label": "Note", "fieldtype": "Data"},
    ],
}

_ORDER = {
    "name": "PlOrder",
    "label": "Order",
    "module": "core",
    "title_field": "subject",
    "fields": [
        {"fieldname": "tab_main", "label": "Order sheet", "fieldtype": "Tab"},
        {"fieldname": "subject", "label": "Subject", "fieldtype": "Data"},
        {
            "fieldname": "customer",
            "label": "Customer",
            "fieldtype": "Link",
            "options": "PlCustomer",
        },
        {"fieldname": "order_date", "label": "Date", "fieldtype": "Date"},
        {"fieldname": "col_b", "fieldtype": "Column"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Open\nDone"},
        {
            "fieldname": "total",
            "label": "Total",
            "fieldtype": "Currency",
            "options": "UAH",
        },
        {"fieldname": "urgent", "label": "Urgent", "fieldtype": "Check"},
        {
            "fieldname": "discount",
            "label": "Discount",
            "fieldtype": "Int",
            "print_hide_if_no_value": True,
        },
        {"fieldname": "internal", "label": "Internal", "fieldtype": "Data", "hidden": True},
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "print_hide": True},
        {"fieldname": "pin", "label": "Pin", "fieldtype": "Password"},
        {"fieldname": "empty", "label": "Empty", "fieldtype": "Data"},
        {"fieldname": "sec_items", "label": "Items", "fieldtype": "Section"},
        {"fieldname": "items", "label": "Lines", "fieldtype": "Table", "options": "PlItem"},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "RichText"},
        {"fieldname": "tab_extra", "label": "Extra", "fieldtype": "Tab"},
        {"fieldname": "sec_extra", "label": "Nothing here", "fieldtype": "Section"},
        {"fieldname": "remark", "label": "Remark", "fieldtype": "Data"},
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "write", "create", "delete"]}],
}


@pytest.fixture
async def order(ctx):
    from grunt.api.v1.meta import save_doctype

    for dt in (_CUSTOMER, _ITEM, _ORDER):
        await save_doctype(doctype_data={**dt, "__is_new": True})
    customer = await ctx.new_doc("PlCustomer", {"customer_name": "Acme Ltd"})
    doc = await ctx.new_doc(
        "PlOrder",
        {
            "subject": "Spare parts",
            "customer": customer["name"],
            "order_date": "2026-03-15",
            "status": "Open",
            "total": 12345.5,
            "urgent": True,
            "discount": 0,
            "internal": "staff only",
            "code": "X-1",
            "pin": "1234",
            "notes": "<p>Deliver <b>fast</b></p><script>alert(1)</script>",
            "items": [
                {"item": "Bolt", "qty": 3, "amount": 1.5, "note": "n"},
                {"item": "Nut", "qty": 2.25, "amount": 0.75},
            ],
        },
    )
    await ctx.db._session().commit()
    return doc


def _fields(layout):
    return {
        item.fieldname: item for section in layout for column in section.columns for item in column
    }


@pytest.mark.asyncio
async def test_layout_follows_the_form(ctx, order):
    layout = await build_print_layout("PlOrder", order)

    # The "Extra" tab has nothing to print - dropped with its section.
    assert [(s.tab_label, s.label) for s in layout] == [("Order sheet", ""), ("", "Items")]
    first = layout[0]
    assert [[i.fieldname for i in col] for col in first.columns] == [
        ["subject", "customer", "order_date"],
        ["status", "total", "urgent"],
    ]
    # Hidden, print_hide, secret, empty and a zero print_hide_if_no_value - not printed.
    printed = _fields(layout)
    for name in ("internal", "code", "pin", "empty", "discount", "remark"):
        assert name not in printed


@pytest.mark.asyncio
async def test_values_are_formatted(ctx, order):
    fields = _fields(await build_print_layout("PlOrder", order))

    assert fields["customer"].value == "Acme Ltd"  # the title, not the id
    assert fields["order_date"].value == "15.03.2026"
    assert fields["total"].value == "12 345,50 ₴"
    assert fields["urgent"].value == "✓"

    notes = fields["notes"]
    assert isinstance(notes, PrintField) and notes.wide
    assert "<b>fast</b>" in notes.value
    assert "<script>" not in notes.value


@pytest.mark.asyncio
async def test_child_table(ctx, order):
    table = _fields(await build_print_layout("PlOrder", order))["items"]

    assert isinstance(table, PrintTable)
    assert table.label == "Lines"
    # in_list_view columns; "unused" is empty in every row - dropped.
    assert table.columns == [("Item", False), ("Qty", True), ("Amount", True)]
    assert table.rows == [["Bolt", "3", "1,50 ₴"], ["Nut", "2,25", "0,75 ₴"]]


@pytest.mark.asyncio
async def test_value_markup_is_escaped(ctx, order):
    order["subject"] = "<img src=x onerror=alert(1)>"
    order["items"][0]["item"] = "<script>alert(2)</script>"
    html = await render_print_html("PlOrder", order)
    assert "<img src=x" not in html
    assert "<script>alert(2)</script>" not in html
    assert "&lt;script&gt;alert(2)&lt;/script&gt;" in html


@pytest.mark.asyncio
async def test_standard_print(ctx, order):
    html = await render_print_html("PlOrder", order)
    assert "<h1>Spare parts</h1>" in html
    assert "Acme Ltd" in html
    assert '<div class="print-section-heading">Items</div>' in html
    assert "staff only" not in html


@pytest.mark.asyncio
async def test_print_format_reuses_the_layout(ctx, order):
    template = (
        '{% from "print_macros.html" import render_layout %}'
        "<html><body><h1>Custom</h1>{{ render_layout(layout) }}</body></html>"
    )
    await ctx.new_doc(
        "PrintFormat",
        {
            "name": "pl-custom",
            "ref_doctype": "PlOrder",
            "template_type": "html",
            "template": template,
            "is_default": True,
        },
    )
    html = await render_print_html("PlOrder", order)
    assert "<h1>Custom</h1>" in html
    assert "Acme Ltd" in html
